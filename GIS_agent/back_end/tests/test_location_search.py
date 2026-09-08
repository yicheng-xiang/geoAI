import pathlib
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import location_search
from location_search import LocationSearchError, search_hong_kong_location


class LocationSearchTests(unittest.TestCase):
    def setUp(self):
        location_search._CACHE.clear()

    def test_polyu_z_core_alias_resolves_official_block_z(self):
        candidates = [{
            "nameEN": "The Hong Kong Polytechnic University Block Z",
            "nameZH": "香港理工大學Z座",
            "addressEN": "181 Chatham Road South",
            "addressZH": "漆咸道南181號",
            "districtEN": "Yau Tsim Mong District",
            "districtZH": "油尖旺區",
            "x": 836530.0,
            "y": 818611.0,
        }]
        with patch("location_search._fetch_location_results", return_value=candidates) as fetch:
            result = search_hong_kong_location("香港理工大学 Z Core")

        fetch.assert_called_once_with("Hong Kong Polytechnic University Block Z", 10.0)
        self.assertEqual(result["name"], candidates[0]["nameEN"])
        self.assertAlmostEqual(result["longitude"], 114.1794171, places=5)
        self.assertAlmostEqual(result["latitude"], 22.3064592, places=5)
        self.assertEqual(result["source_crs"], "EPSG:2326")
        self.assertFalse(result["cache_hit"])

    def test_repeated_location_uses_cache_without_another_api_call(self):
        candidate = {
            "nameEN": "Test Place", "nameZH": "", "addressEN": "", "addressZH": "",
            "districtEN": "Kowloon City District", "districtZH": "",
            "x": 836530.0, "y": 818611.0,
        }
        with patch("location_search._fetch_location_results", return_value=[candidate]) as fetch:
            first = search_hong_kong_location("Test Place")
            second = search_hong_kong_location("Test Place")

        self.assertEqual(fetch.call_count, 1)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])

    def test_no_valid_candidate_returns_a_clear_error(self):
        with patch("location_search._fetch_location_results", return_value=[]):
            with self.assertRaises(LocationSearchError) as context:
                search_hong_kong_location("Missing place")
        self.assertEqual(context.exception.code, "LOCATION_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
