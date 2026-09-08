"""Validate and normalize session-scoped Excel point uploads.

Uploaded workbooks are parsed from memory and reduced to a small canonical point
table.  No user supplied path is ever opened or retained.
"""

from datetime import datetime, timezone
import hashlib
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata
import zipfile

import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from data_quality import validate_and_clean_point_table


SESSION_UPLOAD_DATASET_ID = "session_upload"
ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_XLSX_BYTES = 50 * 1024 * 1024
MAX_XLSX_ENTRIES = 1_000
MAX_UPLOAD_ROWS = 10_000
MAX_UPLOAD_COLUMNS = 50
MAX_UPLOAD_CELLS = 200_000
MAX_STRING_LENGTH = 500
MAX_UPLOAD_FACILITY_TYPES = 20
OUTPUT_CRS = "EPSG:4326"
# Bounding box of the registered HKDistrict18 layer after conversion to EPSG:4326.
HONG_KONG_DISTRICT_BOUNDS_WGS84 = (
    113.83506660700004,
    22.153344109000045,
    114.44199325800002,
    22.56194934900003,
)


class UploadDatasetError(ValueError):
    """A safe, user-facing validation error for the upload endpoint."""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _normalized_column_name(value):
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"[\s_\-./()（）\[\]【】]+", "", text)


COLUMN_ALIASES = {
    "name": {
        "name", "facilityname", "sitename", "placename", "locationname",
        "名稱", "名称", "設施名稱", "设施名称", "地點名稱", "地点名称",
    },
    "latitude": {
        "latitude", "lat", "y", "ycoordinate", "ycoord", "緯度", "纬度",
        "wgs84latitude", "latitudewgs84",
    },
    "longitude": {
        "longitude", "long", "lon", "lng", "x", "xcoordinate", "xcoord",
        "經度", "经度", "wgs84longitude", "longitudewgs84",
    },
    "facility_type": {
        "type", "facilitytype", "category", "class", "facilitycategory",
        "類型", "类型", "設施類型", "设施类型", "分類", "分类",
    },
}


def _find_column(columns, role, required=True):
    aliases = COLUMN_ALIASES[role]
    candidates = []
    for column in columns:
        normalized = _normalized_column_name(column)
        if normalized in aliases:
            candidates.append(column)

    if len(candidates) > 1:
        raise UploadDatasetError(
            "AMBIGUOUS_UPLOAD_COLUMNS",
            f"Multiple columns match the required '{role}' field: "
            + ", ".join(str(column) for column in candidates),
            422,
        )
    if candidates:
        return candidates[0]
    if required:
        raise UploadDatasetError(
            "MISSING_UPLOAD_COLUMNS",
            f"The workbook must contain a recognizable {role} column.",
            422,
        )
    return None


def _validate_xlsx_container(content):
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise UploadDatasetError(
                    "EXCEL_ARCHIVE_TOO_LARGE",
                    "The workbook contains too many internal files.",
                    413,
                )
            uncompressed_size = sum(entry.file_size for entry in entries)
            if uncompressed_size > MAX_UNCOMPRESSED_XLSX_BYTES:
                raise UploadDatasetError(
                    "EXCEL_ARCHIVE_TOO_LARGE",
                    "The expanded workbook exceeds the 50 MB safety limit.",
                    413,
                )
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                archive_path = PurePosixPath(normalized_name)
                if archive_path.is_absolute() or ".." in archive_path.parts:
                    raise UploadDatasetError(
                        "UNSAFE_EXCEL_ARCHIVE",
                        "The workbook contains an unsafe internal path.",
                        422,
                    )
                if entry.flag_bits & 0x1:
                    raise UploadDatasetError(
                        "ENCRYPTED_EXCEL_FILE",
                        "Encrypted workbooks are not supported.",
                        422,
                    )
                if normalized_name.casefold().endswith("vbaproject.bin"):
                    raise UploadDatasetError(
                        "MACRO_ENABLED_WORKBOOK",
                        "Macro-enabled workbooks are not supported.",
                        422,
                    )
            if not any(entry.filename.replace("\\", "/") == "xl/workbook.xml" for entry in entries):
                raise UploadDatasetError(
                    "INVALID_EXCEL_FILE",
                    "The uploaded file is not a valid .xlsx workbook.",
                    422,
                )
    except zipfile.BadZipFile as exc:
        raise UploadDatasetError(
            "INVALID_EXCEL_FILE",
            "The uploaded file is not a valid .xlsx workbook.",
            422,
        ) from exc


def _read_excel(content, extension):
    _validate_xlsx_container(content)

    try:
        return pd.read_excel(
            BytesIO(content),
            sheet_name=0,
            engine="openpyxl",
            nrows=MAX_UPLOAD_ROWS + 1,
        )
    except ImportError as exc:
        raise UploadDatasetError(
            "EXCEL_ENGINE_UNAVAILABLE",
            f"The server cannot read {extension} files because its Excel engine is unavailable.",
            500,
        ) from exc
    except UploadDatasetError:
        raise
    except Exception as exc:
        raise UploadDatasetError(
            "INVALID_EXCEL_FILE",
            "The workbook could not be parsed. Check that it is not encrypted or corrupted.",
            422,
        ) from exc


def parse_excel_upload(file_storage):
    """Return a normalized in-memory dataset suitable for one browser session."""
    if file_storage is None:
        raise UploadDatasetError("MISSING_UPLOAD_FILE", "An Excel file is required.")

    original_name = str(file_storage.filename or "").strip()
    extension = Path(original_name).suffix.casefold()
    if extension not in ALLOWED_EXCEL_EXTENSIONS:
        raise UploadDatasetError(
            "UNSUPPORTED_FILE_TYPE",
            "Only .xlsx Excel files are accepted.",
            415,
        )

    content = file_storage.stream.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise UploadDatasetError("EMPTY_UPLOAD_FILE", "The uploaded Excel file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadDatasetError(
            "UPLOAD_FILE_TOO_LARGE",
            "The Excel file exceeds the 5 MB upload limit.",
            413,
        )

    dataframe = _read_excel(content, extension)
    dataframe = dataframe.dropna(how="all")
    if dataframe.empty:
        raise UploadDatasetError("EMPTY_DATASET", "The workbook's first sheet contains no records.", 422)
    if len(dataframe) > MAX_UPLOAD_ROWS:
        raise UploadDatasetError(
            "TOO_MANY_UPLOAD_ROWS",
            f"The workbook exceeds the {MAX_UPLOAD_ROWS:,}-row limit.",
            413,
        )
    if len(dataframe.columns) > MAX_UPLOAD_COLUMNS:
        raise UploadDatasetError(
            "TOO_MANY_UPLOAD_COLUMNS",
            f"The workbook exceeds the {MAX_UPLOAD_COLUMNS}-column limit.",
            413,
        )
    if dataframe.shape[0] * dataframe.shape[1] > MAX_UPLOAD_CELLS:
        raise UploadDatasetError(
            "TOO_MANY_UPLOAD_CELLS",
            f"The workbook exceeds the {MAX_UPLOAD_CELLS:,}-cell limit.",
            413,
        )

    string_columns = dataframe.select_dtypes(include=["object", "string"]).columns
    for column in string_columns:
        lengths = dataframe[column].dropna().astype(str).str.len()
        if not lengths.empty and int(lengths.max()) > MAX_STRING_LENGTH:
            raise UploadDatasetError(
                "UPLOAD_VALUE_TOO_LONG",
                f"Column '{column}' contains text longer than {MAX_STRING_LENGTH} characters.",
                422,
            )

    name_column = _find_column(dataframe.columns, "name")
    latitude_column = _find_column(dataframe.columns, "latitude")
    longitude_column = _find_column(dataframe.columns, "longitude")
    type_column = _find_column(dataframe.columns, "facility_type", required=False)

    selected_columns = [name_column, latitude_column, longitude_column]
    if len(set(selected_columns)) != len(selected_columns):
        raise UploadDatasetError(
            "AMBIGUOUS_UPLOAD_COLUMNS",
            "Name, latitude, and longitude must be separate columns.",
            422,
        )

    if type_column is None:
        facility_types = pd.Series("Uploaded Facility", index=dataframe.index)
    else:
        facility_types = dataframe[type_column].astype("string").str.strip()
        facility_types = facility_types.mask(
            facility_types.isna() | facility_types.eq(""),
            "Uploaded Facility",
        )

    canonical = pd.DataFrame({
        "NAME": dataframe[name_column],
        "LATITUDE": dataframe[latitude_column],
        "LONGITUDE": dataframe[longitude_column],
        "FACILITY_TYPE": facility_types,
    })
    cleaned, quality = validate_and_clean_point_table(
        canonical,
        "LATITUDE",
        "LONGITUDE",
        "FACILITY_TYPE",
        source_crs=OUTPUT_CRS,
        study_bounds=HONG_KONG_DISTRICT_BOUNDS_WGS84,
    )

    normalized_names = canonical["NAME"].astype("string").str.strip()
    valid_names = normalized_names.notna() & normalized_names.ne("")
    cleaned = cleaned.loc[cleaned.index.intersection(canonical.index[valid_names])].copy()
    cleaned["NAME"] = normalized_names.loc[cleaned.index].astype(str)
    quality["null_names"] = int((~valid_names).sum())
    quality["valid_records"] = int(len(cleaned))
    quality["excluded_records"] = int(len(canonical) - len(cleaned))
    quality["issues_detected"] = bool(quality["issues_detected"] or (~valid_names).any())
    quality["passed"] = bool(len(cleaned))

    if cleaned.empty:
        raise UploadDatasetError(
            "NO_VALID_POINT_RECORDS",
            "No valid named WGS 84 point records within Hong Kong remain after validation.",
            422,
        )

    facility_type_count = int(cleaned["FACILITY_TYPE"].nunique())
    if facility_type_count > MAX_UPLOAD_FACILITY_TYPES:
        raise UploadDatasetError(
            "TOO_MANY_FACILITY_TYPES",
            f"The workbook contains more than {MAX_UPLOAD_FACILITY_TYPES} facility types. "
            "Reduce or group the FacilityType values before uploading.",
            422,
        )
    quality["facility_type_count"] = facility_type_count

    basename = Path(original_name).name
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    safe_filename = safe_filename or f"upload{extension}"
    return {
        "id": SESSION_UPLOAD_DATASET_ID,
        "filename": safe_filename[:255],
        "kind": "excel",
        "crs": OUTPUT_CRS,
        "dataframe": cleaned.reset_index(drop=True),
        "columns": {
            "name": str(name_column),
            "latitude": str(latitude_column),
            "longitude": str(longitude_column),
            "facility_type": str(type_column) if type_column is not None else None,
        },
        "quality": quality,
        "sha256": hashlib.sha256(content).hexdigest(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def public_upload_summary(dataset):
    """Return only JSON-safe metadata; the DataFrame stays server-side."""
    return {
        "dataset_id": dataset["id"],
        "filename": dataset["filename"],
        "row_count": int(len(dataset["dataframe"])),
        "crs": dataset["crs"],
        "columns": dict(dataset["columns"]),
        "quality": dict(dataset["quality"]),
        "sha256": dataset["sha256"],
        "uploaded_at": dataset["uploaded_at"],
    }
