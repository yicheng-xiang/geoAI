from io import BytesIO
import pathlib
import sys
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd
from openpyxl import Workbook


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from point_datasets import PointDatasetError, load_point_dataset
from upload_service import (
    MAX_STRING_LENGTH,
    MAX_UPLOAD_FACILITY_TYPES,
    UploadDatasetError,
    parse_excel_upload,
    public_upload_summary,
)


class FakeFileStorage:
    def __init__(self, stream, filename):
        self.stream = stream
        self.filename = filename


def workbook_upload(filename="points.xlsx", extra_entries=None):
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook />")
        for name, content in extra_entries or []:
            archive.writestr(name, content)
    stream.seek(0)
    return FakeFileStorage(stream=stream, filename=filename)


def real_workbook_upload(rows, filename="points.xlsx"):
    workbook = Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return FakeFileStorage(stream=stream, filename=filename)


class ExcelUploadTests(unittest.TestCase):
    def test_real_xlsx_first_sheet_is_parsed(self):
        dataset = parse_excel_upload(real_workbook_upload([
            ["Name", "Latitude", "Longitude", "FacilityType"],
            ["Clinic A", 22.30, 114.17, "Clinic"],
            ["Clinic B", 22.35, 114.20, "Clinic"],
        ]))
        self.assertEqual(len(dataset["dataframe"]), 2)
        self.assertEqual(dataset["columns"]["facility_type"], "FacilityType")
        self.assertEqual(set(dataset["dataframe"]["FACILITY_TYPE"]), {"Clinic"})

    @patch("upload_service.pd.read_excel")
    def test_valid_upload_is_normalized_and_public_summary_excludes_dataframe(self, read_excel):
        read_excel.return_value = pd.DataFrame({
            "Name": ["Alpha", "Beta"],
            "Latitude": [22.30, 22.35],
            "Longitude": [114.17, 114.20],
        })

        dataset = parse_excel_upload(workbook_upload())

        self.assertEqual(dataset["id"], "session_upload")
        self.assertEqual(list(dataset["dataframe"].columns), [
            "NAME", "LATITUDE", "LONGITUDE", "FACILITY_TYPE",
        ])
        self.assertEqual(set(dataset["dataframe"]["FACILITY_TYPE"]), {"Uploaded Facility"})
        self.assertEqual(len(dataset["sha256"]), 64)
        summary = public_upload_summary(dataset)
        self.assertEqual(summary["row_count"], 2)
        self.assertNotIn("dataframe", summary)

    def test_legacy_excel_and_non_excel_extensions_are_rejected(self):
        for filename in ("points.xls", "points.csv", "points.xlsm"):
            with self.subTest(filename=filename):
                with self.assertRaises(UploadDatasetError) as context:
                    parse_excel_upload(FakeFileStorage(stream=BytesIO(b"content"), filename=filename))
                self.assertEqual(context.exception.code, "UNSUPPORTED_FILE_TYPE")

    def test_zip_path_traversal_is_rejected_before_excel_parser(self):
        with self.assertRaises(UploadDatasetError) as context:
            parse_excel_upload(workbook_upload(extra_entries=[("../payload", "unsafe")]))
        self.assertEqual(context.exception.code, "UNSAFE_EXCEL_ARCHIVE")

    @patch("upload_service.pd.read_excel")
    def test_required_columns_are_enforced(self, read_excel):
        read_excel.return_value = pd.DataFrame({
            "Name": ["Alpha"],
            "Latitude": [22.3],
        })
        with self.assertRaises(UploadDatasetError) as context:
            parse_excel_upload(workbook_upload())
        self.assertEqual(context.exception.code, "MISSING_UPLOAD_COLUMNS")

    @patch("upload_service.pd.read_excel")
    def test_invalid_rows_are_excluded_and_long_text_is_rejected(self, read_excel):
        read_excel.return_value = pd.DataFrame({
            "Name": ["Alpha", "", "Bad coordinate"],
            "Latitude": [22.3, 22.4, 95],
            "Longitude": [114.1, 114.2, 114.3],
        })
        dataset = parse_excel_upload(workbook_upload())
        self.assertEqual(len(dataset["dataframe"]), 1)
        self.assertEqual(dataset["quality"]["null_names"], 1)
        self.assertEqual(dataset["quality"]["invalid_coordinate_range"], 1)

        read_excel.return_value = pd.DataFrame({
            "Name": ["x" * (MAX_STRING_LENGTH + 1)],
            "Latitude": [22.3],
            "Longitude": [114.1],
        })
        with self.assertRaises(UploadDatasetError) as context:
            parse_excel_upload(workbook_upload())
        self.assertEqual(context.exception.code, "UPLOAD_VALUE_TOO_LONG")

    @patch("upload_service.pd.read_excel")
    def test_blank_optional_facility_types_use_the_default_category(self, read_excel):
        read_excel.return_value = pd.DataFrame({
            "Name": ["Alpha", "Beta", "Gamma"],
            "Latitude": [22.30, 22.31, 22.32],
            "Longitude": [114.17, 114.18, 114.19],
            "FacilityType": ["Clinic", None, "  "],
        })

        dataset = parse_excel_upload(workbook_upload())

        self.assertEqual(len(dataset["dataframe"]), 3)
        self.assertEqual(
            dataset["dataframe"]["FACILITY_TYPE"].tolist(),
            ["Clinic", "Uploaded Facility", "Uploaded Facility"],
        )

    @patch("upload_service.pd.read_excel")
    def test_points_outside_hong_kong_are_reported_and_excluded(self, read_excel):
        read_excel.return_value = pd.DataFrame({
            "Name": ["Hong Kong", "London"],
            "Latitude": [22.30, 51.5072],
            "Longitude": [114.17, -0.1276],
        })

        dataset = parse_excel_upload(workbook_upload())

        self.assertEqual(dataset["quality"]["valid_records"], 1)
        self.assertEqual(dataset["quality"]["outside_study_bounds"], 1)
        self.assertEqual(dataset["dataframe"]["NAME"].tolist(), ["Hong Kong"])

    @patch("upload_service.pd.read_excel")
    def test_excessive_facility_type_cardinality_is_rejected(self, read_excel):
        count = MAX_UPLOAD_FACILITY_TYPES + 1
        read_excel.return_value = pd.DataFrame({
            "Name": [f"Point {index}" for index in range(count)],
            "Latitude": [22.30] * count,
            "Longitude": [114.17] * count,
            "FacilityType": [f"Type {index}" for index in range(count)],
        })

        with self.assertRaises(UploadDatasetError) as context:
            parse_excel_upload(workbook_upload())
        self.assertEqual(context.exception.code, "TOO_MANY_FACILITY_TYPES")


class SessionPointDatasetTests(unittest.TestCase):
    def test_uploaded_data_is_resolved_only_from_current_state(self):
        uploaded = {
            "id": "session_upload",
            "filename": "points.xlsx",
            "kind": "excel",
            "crs": "EPSG:4326",
            "columns": {},
            "quality": {},
            "sha256": "abc",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "dataframe": pd.DataFrame({
                "NAME": ["A"],
                "LATITUDE": [22.3],
                "LONGITUDE": [114.1],
                "FACILITY_TYPE": ["Uploaded Facility"],
            }),
        }
        metadata, dataframe = load_point_dataset({"uploaded_dataset": uploaded}, "session_upload")
        self.assertEqual(metadata["sha256"], "abc")
        self.assertEqual(dataframe.loc[0, "NAME"], "A")
        dataframe.loc[0, "NAME"] = "changed"
        self.assertEqual(uploaded["dataframe"].loc[0, "NAME"], "A")

        with self.assertRaises(PointDatasetError) as context:
            load_point_dataset({}, "session_upload")
        self.assertEqual(context.exception.code, "SESSION_UPLOAD_NOT_FOUND")

        for unsafe_id in ("../points.xlsx", r"C:\points.xlsx", "points.xlsx"):
            with self.assertRaises(PointDatasetError) as context:
                load_point_dataset({}, unsafe_id)
            self.assertEqual(context.exception.code, "UNREGISTERED_DATASET")


if __name__ == "__main__":
    unittest.main()
