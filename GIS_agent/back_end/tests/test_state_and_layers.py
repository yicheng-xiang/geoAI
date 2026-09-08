import pathlib
import sys
import unittest

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from session_store import SessionStore
from agent_schemas.tools_definition import MAP_TOOLS
from data_catalog import DATA_ROOT, get_tabular_dataset
from color_palettes import literal_color, sample_palette
from tool_results import normalize_tool_result, tool_error, tool_success


class SessionStoreTests(unittest.TestCase):
    def test_sessions_are_isolated_and_clear_is_scoped(self):
        store = SessionStore()
        first = store.get_or_create("browser-a")
        second = store.get_or_create("browser-b")
        first["messages"].append("private-a")
        first["uploaded_dataset"] = {"id": "session_upload"}

        self.assertIsNot(first, second)
        self.assertIsNot(first["lock"], second["lock"])
        self.assertEqual(second["messages"], [])
        self.assertIsNone(second["uploaded_dataset"])
        self.assertTrue(store.clear("browser-a"))
        self.assertFalse(store.contains("browser-a"))
        self.assertTrue(store.contains("browser-b"))
        self.assertEqual(len(store), 1)

    def test_same_session_reuses_state(self):
        store = SessionStore()
        self.assertIs(store.get_or_create("same"), store.get_or_create("same"))


class ColorPaletteTests(unittest.TestCase):
    def test_palettes_are_deterministic_css_colors(self):
        self.assertEqual(sample_palette("Blues", 4), sample_palette("Blues", 4))
        self.assertEqual(len(set(sample_palette("Blues", 4))), 4)
        self.assertTrue(all(color.startswith("#") for color in sample_palette("Set1", 12)))
        self.assertEqual(literal_color("blue"), "#0000ff")
        self.assertEqual(literal_color("#AbC"), "#aabbcc")


class ToolResultTests(unittest.TestCase):
    def test_result_contract_and_legacy_failure_detection(self):
        self.assertTrue(tool_success("done")["ok"])
        self.assertFalse(tool_error("BROKEN", "failed")["ok"])
        normalized = normalize_tool_result("Error: no matching data")
        self.assertFalse(normalized["ok"])
        self.assertEqual(normalized["code"], "LEGACY_TOOL_ERROR")


class DatasetAccessTests(unittest.TestCase):
    def test_only_registered_dataset_ids_are_accepted(self):
        dataset = get_tabular_dataset("all_facilities")
        self.assertEqual(dataset["id"], "all_facilities")
        self.assertIn(DATA_ROOT, pathlib.Path(dataset["path"]).parents)

        for unsafe_name in ["AllTogether.csv", "../secret.csv", r"C:\secret.csv"]:
            with self.assertRaises(KeyError):
                get_tabular_dataset(unsafe_name)

    def test_tool_schema_exposes_metric_and_registered_dataset_id(self):
        schemas = {tool["function"]["name"]: tool["function"] for tool in MAP_TOOLS}
        aggregate = schemas["aggregate_points_to_districts"]["parameters"]
        self.assertEqual(
            aggregate["properties"]["dataset_id"]["enum"],
            ["all_facilities", "session_upload"],
        )
        self.assertEqual(
            aggregate["properties"]["metric"]["enum"],
            ["count", "density_per_km2"],
        )
        buffer_parameters = schemas["buffer_facility_coverage"]["parameters"]
        self.assertEqual(
            buffer_parameters["properties"]["dataset_id"]["enum"],
            ["all_facilities", "session_upload"],
        )
        self.assertEqual(buffer_parameters["properties"]["radius_m"]["maximum"], 50000)
        self.assertIn("location_query", buffer_parameters["properties"])
        self.assertNotIn("latitude", buffer_parameters["required"])
        self.assertNotIn("longitude", buffer_parameters["required"])
        self.assertNotIn("path", buffer_parameters["properties"])
        for tool_name in (
            "draw_choropleth",
            "add_points_layer",
            "aggregate_points_to_districts",
            "buffer_facility_coverage",
        ):
            replace_schema = schemas[tool_name]["parameters"]["properties"]["replace_existing"]
            self.assertEqual(replace_schema["type"], "boolean")


if __name__ == "__main__":
    unittest.main()
