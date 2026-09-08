import pathlib
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

try:
    import geopandas as gpd
    import pandas as pd

    from data_catalog import get_vector_path
    from buffer_analysis import buffer_facility_coverage
    from data_quality import validate_and_clean_point_table, validate_and_repair_polygon_dataset
    from layer_styles import add_points_layer, draw_choropleth
    from point_datasets import load_point_dataset, resolve_point_columns
    from spatial_aggregation import aggregate_points_to_districts

    GIS_DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:
    GIS_DEPENDENCIES_AVAILABLE = False


@unittest.skipUnless(GIS_DEPENDENCIES_AVAILABLE, "GeoPandas test dependencies are not installed")
class SpatialAnalysisTests(unittest.TestCase):
    def setUp(self):
        raw = gpd.read_file(get_vector_path("hong_kong_districts"))
        districts, quality = validate_and_repair_polygon_dataset(raw, "EPSG:4326")
        self.quality = quality
        self.state = {
            "gdf": districts.to_crs("EPSG:4326"),
            "web_layers": {},
            "web_map": {},
            "quality": {"districts": quality},
        }

    def test_real_boundary_quality_is_detected_and_repaired(self):
        self.assertEqual(self.quality["initial"]["invalid_geometry"], 1)
        self.assertEqual(self.quality["repaired_geometries"], 1)
        self.assertTrue(self.quality["passed"])

    def test_count_density_and_structured_output(self):
        count_result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="count",
        )
        self.assertTrue(count_result["ok"], count_result)
        count_data = count_result["data"]
        self.assertEqual(count_data["analysis"]["metric"], "count")
        self.assertEqual(count_data["analysis"]["classification"], "Equal interval")
        self.assertEqual(len(count_data["statistics"]), 18)
        self.assertEqual(len(count_data["geojson"]["features"]), 18)
        self.assertEqual(
            sum(row["count"] for row in count_data["statistics"]),
            count_data["quality"]["points"]["matched_to_district"],
        )
        density_result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="density_per_km2",
        )
        self.assertTrue(density_result["ok"], density_result)
        density_data = density_result["data"]
        self.assertEqual(density_data["analysis"]["area_crs"], "EPSG:2326")
        self.assertEqual(density_data["analysis"]["classification"], "Quantiles")
        self.assertTrue(all(row["area_km2"] > 0 for row in density_data["statistics"]))
        self.assertTrue(all(color.startswith("#") for color in density_data["analysis"]["palette"]))

    def test_metric_buffer_counts_facilities_and_returns_traceable_layers(self):
        _, facilities = load_point_dataset(self.state, "all_facilities")
        latitude, longitude, facility_type = resolve_point_columns(facilities)
        ambulance = facilities[
            facilities[facility_type].astype(str).str.contains(
                "Ambulance Depot", case=False, regex=False, na=False,
            )
        ].iloc[0]

        result = buffer_facility_coverage(
            self.state,
            latitude=ambulance[latitude],
            longitude=ambulance[longitude],
            radius_m=500,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            location_name="Test location",
        )

        self.assertTrue(result["ok"], result)
        data = result["data"]
        self.assertEqual(data["analysis"]["method"], "buffer_coverage")
        self.assertEqual(data["analysis"]["analysis_crs"], "EPSG:2326")
        self.assertEqual(data["summary"]["radius_m"], 500.0)
        self.assertGreaterEqual(data["summary"]["matched_count"], 1)
        self.assertEqual(data["summary"]["matched_count"], len(data["statistics"]))
        self.assertTrue(all(row["distance_m"] <= 500 for row in data["statistics"]))
        self.assertEqual(data["geojson"]["features"][0]["geometry"]["type"], "Polygon")
        self.assertEqual(data["visualization_layers"][0]["id"], "buffer_area")
        self.assertEqual(data["visualization_layers"][-1]["id"], "buffer_center")
        self.assertEqual(data["quality"]["points"]["matched_to_buffer"], len(data["statistics"]))

    def test_metric_buffer_rejects_invalid_center_and_radius(self):
        outside = buffer_facility_coverage(
            self.state,
            latitude=0,
            longitude=0,
            radius_m=500,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
        )
        invalid_radius = buffer_facility_coverage(
            self.state,
            latitude=22.3,
            longitude=114.1,
            radius_m=0,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
        )

        self.assertFalse(outside["ok"])
        self.assertEqual(outside["code"], "CENTER_OUTSIDE_STUDY_AREA")
        self.assertFalse(invalid_radius["ok"])
        self.assertEqual(invalid_radius["code"], "INVALID_BUFFER_RADIUS")

    def test_metric_buffer_can_resolve_an_official_place_name(self):
        official_match = {
            "name": "The Hong Kong Polytechnic University Block Z",
            "latitude": 22.30645922482651,
            "longitude": 114.1794170859327,
            "provider": "Lands Department Location Search API",
            "provider_url": "https://portal.csdi.gov.hk/csdi-webpage/apidoc/LocationSearchAPI",
            "source_crs": "EPSG:2326",
            "output_crs": "EPSG:4326",
            "candidate_count": 1,
            "selection_rank": 1,
        }
        with patch("buffer_analysis.search_hong_kong_location", return_value=official_match):
            result = buffer_facility_coverage(
                self.state,
                location_query="Hong Kong Polytechnic University Z Core",
                radius_m=2000,
                dataset_id="all_facilities",
                facility_types=["Primary School"],
            )

        self.assertTrue(result["ok"], result)
        analysis = result["data"]["analysis"]
        self.assertEqual(
            analysis["location_name"],
            "The Hong Kong Polytechnic University Block Z",
        )
        self.assertEqual(analysis["geocoding"]["provider"], official_match["provider"])
        self.assertEqual(
            result["data"]["quality"]["center"]["resolution"],
            "official_location_search",
        )

    def test_builtin_alias_list_matches_ambulance_depots(self):
        result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance", "Rescue", "Ambulance Depot", "Ambulance/Rescue"],
            metric="count",
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            sum(row["count"] for row in result["data"]["statistics"]),
            44,
        )

    def test_coordinate_quality_categories(self):
        sample = pd.DataFrame({
            "Latitude": ["22.3", None, "bad", "95", "22.9"],
            "Longitude": ["114.1", "114.1", "114.1", "114.1", "120"],
            "FACILITY_TYPE": ["A", "A", "A", "A", "A"],
        })
        cleaned, report = validate_and_clean_point_table(
            sample,
            "Latitude",
            "Longitude",
            "FACILITY_TYPE",
            study_bounds=[113.8, 22.1, 114.5, 22.6],
        )
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(report["null_coordinates"], 1)
        self.assertEqual(report["non_numeric_coordinates"], 1)
        self.assertEqual(report["invalid_coordinate_range"], 1)
        self.assertEqual(report["outside_study_bounds"], 1)

    def test_session_upload_can_be_aggregated_without_a_type_filter(self):
        representative_points = self.state["gdf"].geometry.representative_point().iloc[:2]
        self.state["uploaded_dataset"] = {
            "id": "session_upload",
            "filename": "sample.xlsx",
            "kind": "excel",
            "crs": "EPSG:4326",
            "columns": {
                "name": "Name",
                "latitude": "Latitude",
                "longitude": "Longitude",
                "facility_type": None,
            },
            "quality": {"passed": True, "valid_records": 2},
            "sha256": "test-sha256",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "dataframe": pd.DataFrame({
                "NAME": ["Uploaded A", "Uploaded B"],
                "LATITUDE": representative_points.y.to_list(),
                "LONGITUDE": representative_points.x.to_list(),
                "FACILITY_TYPE": ["Uploaded Facility", "Uploaded Facility"],
            }),
        }

        result = aggregate_points_to_districts(
            self.state,
            dataset_id="session_upload",
            facility_types=[],
            metric="count",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(sum(row["count"] for row in result["data"]["statistics"]), 2)
        self.assertEqual(result["data"]["analysis"]["source_sha256"], "test-sha256")
        self.assertEqual(result["data"]["quality"]["upload"]["valid_records"], 2)

    def test_73_uploaded_records_can_be_counted_by_district(self):
        representative_point = self.state["gdf"].geometry.representative_point().iloc[0]
        self.state["uploaded_dataset"] = {
            "id": "session_upload",
            "filename": "fitness_center.xlsx",
            "kind": "excel",
            "crs": "EPSG:4326",
            "columns": {},
            "quality": {"passed": True, "valid_records": 73},
            "sha256": "fitness-center-test",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "dataframe": pd.DataFrame({
                "NAME": [f"Fitness Center {index}" for index in range(73)],
                "LATITUDE": [representative_point.y] * 73,
                "LONGITUDE": [representative_point.x] * 73,
                "FACILITY_TYPE": ["Fitness Center"] * 73,
            }),
        }

        result = aggregate_points_to_districts(
            self.state,
            dataset_id="session_upload",
            facility_types=[],
            metric="count",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(sum(row["count"] for row in result["data"]["statistics"]), 73)
        self.assertEqual(result["data"]["quality"]["points"]["matched_to_district"], 73)

    def test_session_upload_can_be_drawn_without_a_type_filter(self):
        representative_points = self.state["gdf"].geometry.representative_point().iloc[:2]
        self.state["uploaded_dataset"] = {
            "id": "session_upload",
            "filename": "sample.xlsx",
            "kind": "excel",
            "crs": "EPSG:4326",
            "columns": {},
            "quality": {"passed": True, "valid_records": 2},
            "sha256": "point-layer-sha256",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "dataframe": pd.DataFrame({
                "NAME": ["Uploaded A", "Uploaded B"],
                "LATITUDE": representative_points.y.to_list(),
                "LONGITUDE": representative_points.x.to_list(),
                "FACILITY_TYPE": ["Uploaded Facility", "Uploaded Facility"],
            }),
        }

        result = add_points_layer(
            self.state,
            dataset_id="session_upload",
            facility_types=[],
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["data"]["geojson"]["features"]), 2)
        self.assertEqual(
            result["data"]["analysis"]["source_sha256"],
            "point-layer-sha256",
        )
        self.assertEqual(self.state["last_analysis"], result["data"])

    def test_polygon_and_point_maps_can_replace_each_other(self):
        polygon_result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="count",
            replace_existing=True,
        )
        self.assertTrue(polygon_result["ok"], polygon_result)
        point_result = add_points_layer(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            replace_existing=True,
        )
        self.assertTrue(point_result["ok"], point_result)
        self.assertTrue(point_result["data"]["analysis"]["replace_existing"])
        self.assertTrue(all(
            feature["geometry"]["type"] == "Point"
            for feature in point_result["data"]["geojson"]["features"]
        ))

        replacement_polygon = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="density_per_km2",
            replace_existing=True,
        )
        self.assertTrue(replacement_polygon["ok"], replacement_polygon)
        self.assertTrue(replacement_polygon["data"]["analysis"]["replace_existing"])
        self.assertTrue(all(
            "Polygon" in feature["geometry"]["type"]
            for feature in replacement_polygon["data"]["geojson"]["features"]
        ))

    def test_requested_colormap_is_exposed_for_web_map_and_legend(self):
        orange_result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="count",
            cmap="YlOrRd",
        )
        blue_result = aggregate_points_to_districts(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            metric="count",
            cmap="Blues",
        )

        self.assertTrue(orange_result["ok"], orange_result)
        self.assertTrue(blue_result["ok"], blue_result)
        orange_analysis = orange_result["data"]["analysis"]
        blue_analysis = blue_result["data"]["analysis"]
        self.assertEqual(orange_analysis["colormap"], "YlOrRd")
        self.assertEqual(blue_analysis["colormap"], "Blues")
        self.assertNotEqual(orange_analysis["palette"], blue_analysis["palette"])
        self.assertEqual(
            len(blue_analysis["palette"]),
            blue_analysis["classification_intervals"],
        )

        point_result = add_points_layer(
            self.state,
            dataset_id="all_facilities",
            facility_types=["Ambulance Depot"],
            cmap="blue",
        )
        self.assertTrue(point_result["ok"], point_result)
        self.assertEqual(
            set(point_result["data"]["analysis"]["category_colors"].values()),
            {"#0000ff"},
        )

        categorical_result = draw_choropleth(
            self.state,
            column="ENAME",
            cmap="Blues",
        )
        self.assertTrue(categorical_result["ok"], categorical_result)
        categorical_analysis = categorical_result["data"]["analysis"]
        self.assertEqual(categorical_analysis["colormap"], "Blues")
        self.assertEqual(
            set(categorical_analysis["category_colors"].values()),
            set(categorical_analysis["palette"]),
        )


if __name__ == "__main__":
    unittest.main()
