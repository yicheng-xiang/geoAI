from io import BytesIO
import os
import pathlib
import sys
import unittest

from openpyxl import Workbook


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_KEY", "test-key")

from agent import SESSION_STORE
from server import app


def _xlsx_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    stream.seek(0)
    return stream


class UploadEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        SESSION_STORE.clear("upload-browser-a")
        SESSION_STORE.clear("upload-browser-b")

    def test_upload_is_registered_only_in_the_requested_session(self):
        response = self.client.post(
            "/api/upload_dataset",
            data={
                "session_id": "upload-browser-a",
                "file": (
                    _xlsx_bytes([
                        ["Name", "Latitude", "Longitude"],
                        ["Clinic A", 22.30, 114.17],
                    ]),
                    "clinics.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["dataset_id"], "session_upload")
        self.assertEqual(payload["row_count"], 1)
        self.assertIsNotNone(
            SESSION_STORE.get_or_create("upload-browser-a")["uploaded_dataset"]
        )
        self.assertIsNone(
            SESSION_STORE.get_or_create("upload-browser-b")["uploaded_dataset"]
        )

        restored_response = self.client.get(
            "/api/session_state?session_id=upload-browser-a"
        )
        self.addCleanup(restored_response.close)
        restored = restored_response.get_json()
        self.assertEqual(restored_response.status_code, 200)
        self.assertEqual(restored["uploaded_dataset"]["filename"], "clinics.xlsx")
        self.assertEqual(restored["uploaded_dataset"]["row_count"], 1)
        self.assertNotIn("dataframe", restored["uploaded_dataset"])

    def test_request_size_limit_uses_the_standard_failure_contract(self):
        original_limit = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 128
        self.addCleanup(app.config.__setitem__, "MAX_CONTENT_LENGTH", original_limit)
        response = self.client.post(
            "/api/upload_dataset",
            data={
                "session_id": "upload-browser-a",
                "file": (BytesIO(b"x" * 256), "large.xlsx"),
            },
            content_type="multipart/form-data",
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 413)
        payload = response.get_json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_code"], "UPLOAD_REQUEST_TOO_LARGE")

    def test_replacing_an_upload_invalidates_the_previous_map(self):
        session = SESSION_STORE.get_or_create("upload-browser-a")
        session["map_state"] = {
            "fig": None,
            "layers": {"facility_points": [object()]},
        }
        session["messages"] = [{"role": "system", "content": "test"}]

        response = self.client.post(
            "/api/upload_dataset",
            data={
                "session_id": "upload-browser-a",
                "file": (
                    _xlsx_bytes([
                        ["Name", "Latitude", "Longitude"],
                        ["Replacement", 22.31, 114.18],
                    ]),
                    "replacement.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        updated = SESSION_STORE.get_or_create("upload-browser-a")
        self.assertIsNone(updated["map_state"])
        self.assertEqual(updated["messages"], [{"role": "system", "content": "test"}])
        self.assertEqual(
            updated["uploaded_dataset"]["dataframe"]["NAME"].tolist(),
            ["Replacement"],
        )


if __name__ == "__main__":
    unittest.main()
