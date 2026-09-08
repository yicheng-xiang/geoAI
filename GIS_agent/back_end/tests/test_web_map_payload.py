import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

import agent
from agent import (
    _normalize_dataset_arguments,
    _normalize_map_arguments,
    _update_web_layer_stack,
    _web_map_payload,
)
from tools.map_elements import add_title


def result_data(geometry_type, method):
    coordinates = [114.1, 22.3] if geometry_type == "Point" else [
        [[114.0, 22.2], [114.2, 22.2], [114.2, 22.4], [114.0, 22.2]]
    ]
    return {
        "geojson": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"metric_value": 1},
                "geometry": {"type": geometry_type, "coordinates": coordinates},
            }],
        },
        "analysis": {"method": method},
        "statistics": [{"value": 1}],
        "quality": {"passed": True},
    }


class WebMapPayloadTests(unittest.TestCase):
    def test_title_change_is_returned_in_browser_map_payload(self):
        state = {
            "web_layers": {},
            "web_map": {"title": "Old title"},
        }

        result = add_title(state, text="HK fitness center distribution")

        self.assertTrue(result["ok"], result)
        self.assertEqual(
            _web_map_payload(state)["map_presentation"]["title"],
            "HK fitness center distribution",
        )

    def test_polygon_and_point_layers_are_returned_in_drawing_order(self):
        state = {"web_layers": {}, "web_map": {"title": "Test map"}}
        _update_web_layer_stack(state, "add_points_layer", result_data("Point", "facility_filter"))
        _update_web_layer_stack(state, "draw_choropleth", result_data("Polygon", "district_choropleth"))
        state["web_map"]["title"] = "Test map"

        payload = _web_map_payload(state)
        self.assertEqual([layer["kind"] for layer in payload["map_layers"]], ["polygon", "point"])
        self.assertEqual(payload["map_presentation"]["title"], "Test map")

    def test_new_thematic_result_replaces_previous_polygon_layer(self):
        state = {"web_layers": {}, "web_map": {"title": "Stale map title"}}
        _update_web_layer_stack(state, "draw_choropleth", result_data("Polygon", "district_choropleth"))
        _update_web_layer_stack(
            state,
            "aggregate_points_to_districts",
            result_data("Polygon", "point_in_polygon"),
        )

        payload = _web_map_payload(state)
        self.assertEqual(len(payload["map_layers"]), 1)
        self.assertEqual(payload["map_layers"][0]["analysis"]["method"], "point_in_polygon")
        self.assertIsNone(payload["map_presentation"]["title"])

    def test_geometry_switch_replaces_the_previous_web_layer(self):
        state = {"web_layers": {}, "web_map": {}}
        polygon = result_data("Polygon", "point_in_polygon")
        point = result_data("Point", "facility_filter")
        point["analysis"]["replace_existing"] = True

        _update_web_layer_stack(state, "aggregate_points_to_districts", polygon)
        _update_web_layer_stack(state, "add_points_layer", point)

        payload = _web_map_payload(state)
        self.assertEqual(len(payload["map_layers"]), 1)
        self.assertEqual(payload["map_layers"][0]["kind"], "point")

    def test_color_only_change_preserves_an_explicit_title(self):
        state = {
            "user_prompt": "Change the map and legend colors to blue.",
            "web_layers": {},
            "web_map": {"title": "HK fitness center distribution"},
        }
        colored_polygon = result_data("Polygon", "point_in_polygon")
        colored_polygon["analysis"].update({
            "colormap": "Blues",
            "palette": ["#9ecae1", "#08519c"],
        })

        _update_web_layer_stack(state, "aggregate_points_to_districts", colored_polygon)

        self.assertEqual(
            _web_map_payload(state)["map_presentation"]["title"],
            "HK fitness center distribution",
        )

    def test_buffer_result_registers_polygon_points_and_center_in_order(self):
        state = {"web_layers": {}, "web_map": {}}
        analysis = {
            "method": "buffer_coverage",
            "radius_m": 500,
            "replace_existing": True,
        }
        buffer_result = result_data("Polygon", "buffer_coverage")
        buffer_result["analysis"] = analysis
        buffer_result["visualization_layers"] = [
            {
                "id": "buffer_area",
                "kind": "polygon",
                "geojson": result_data("Polygon", "buffer_coverage")["geojson"],
                "analysis": {**analysis, "visual_role": "buffer_area"},
            },
            {
                "id": "buffer_facilities",
                "kind": "point",
                "geojson": result_data("Point", "buffer_coverage")["geojson"],
                "analysis": {**analysis, "visual_role": "matched_facilities"},
            },
            {
                "id": "buffer_center",
                "kind": "point",
                "geojson": result_data("Point", "buffer_coverage")["geojson"],
                "analysis": {**analysis, "visual_role": "buffer_center"},
            },
        ]

        _update_web_layer_stack(state, "buffer_facility_coverage", buffer_result)

        layers = _web_map_payload(state)["map_layers"]
        self.assertEqual(
            [layer["id"] for layer in layers],
            ["buffer_area", "buffer_facilities", "buffer_center"],
        )


class DatasetSelectionTests(unittest.TestCase):
    def test_builtin_request_cannot_inherit_stale_session_upload_selection(self):
        arguments = {"dataset_id": "session_upload", "facility_types": ["Ambulance Depot"]}
        normalized = _normalize_dataset_arguments(
            "aggregate_points_to_districts",
            arguments,
            "Count ambulance depots in each district.",
        )
        self.assertEqual(normalized["dataset_id"], "all_facilities")
        self.assertEqual(arguments["dataset_id"], "session_upload")

    def test_explicit_upload_reference_keeps_session_dataset(self):
        normalized = _normalize_dataset_arguments(
            "aggregate_points_to_districts",
            {"dataset_id": "session_upload", "facility_types": []},
            "Count the uploaded points by district.",
        )
        self.assertEqual(normalized["dataset_id"], "session_upload")

    def test_current_map_edit_can_reuse_registered_session_upload(self):
        normalized = _normalize_map_arguments(
            "add_points_layer",
            {"dataset_id": "all_facilities", "facility_types": []},
            "Change the current polygon map to a point map.",
            {"last_analysis": {"analysis": {"dataset_id": "session_upload"}}},
        )
        self.assertEqual(normalized["dataset_id"], "session_upload")
        self.assertTrue(normalized["replace_existing"])

    def test_explicit_overlay_does_not_force_geometry_replacement(self):
        normalized = _normalize_map_arguments(
            "add_points_layer",
            {
                "dataset_id": "all_facilities",
                "facility_types": ["Ambulance Depot"],
                "replace_existing": False,
            },
            "Add a point map overlay to the polygon map.",
        )
        self.assertFalse(normalized["replace_existing"])

    def test_explicit_per_call_buffer_overlay_is_preserved(self):
        arguments = {
            "dataset_id": "all_facilities",
            "facility_types": ["Ambulance Depot"],
            "latitude": 22.25,
            "longitude": 114.17,
            "radius_m": 500,
            "replace_existing": False,
        }
        replacement = _normalize_map_arguments(
            "buffer_facility_coverage", arguments, "Find facilities within 500 metres."
        )
        overlay = _normalize_map_arguments(
            "buffer_facility_coverage", arguments, "Overlay this 500 metre buffer on the map."
        )

        self.assertFalse(replacement["replace_existing"])
        self.assertFalse(overlay["replace_existing"])


class ModelFinalizationFallbackTests(unittest.TestCase):
    def test_completed_spatial_result_survives_a_later_model_rejection(self):
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="aggregate_points_to_districts",
                arguments='{"dataset_id":"session_upload","facility_types":[],"metric":"count"}',
            ),
        )
        first_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                tool_calls=[tool_call],
                content=None,
            ))],
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(side_effect=[first_response, RuntimeError("invalid_prompt")]),
                ),
            ),
        )
        spatial_result = result_data("Polygon", "point_in_polygon")
        session = {
            "map_state": {"web_layers": {}, "web_map": {}},
            "messages": [],
            "uploaded_dataset": None,
        }

        with (
            patch.object(agent, "client", fake_client),
            patch.dict(agent.AVAILABLE_TOOLS, {
                "aggregate_points_to_districts": lambda state, **kwargs: {
                    "ok": True,
                    "code": "SPATIAL_ANALYSIS_COMPLETED",
                    "message": "73 records matched.",
                    "data": spatial_result,
                },
            }),
        ):
            events = list(agent._run_locked_session(
                "Count the uploaded points by district.",
                "browser-a",
                session,
            ))

        self.assertEqual([event["status"] for event in events], ["processing", "completed"])
        self.assertEqual(events[-1]["warning_code"], "MODEL_FINALIZATION_FALLBACK")
        self.assertEqual(events[-1]["analysis"]["method"], "point_in_polygon")
        self.assertEqual(len(events[-1]["map_layers"]), 1)
        self.assertNotIn("error", events[-1])

    def test_initial_model_rejection_remains_a_failure(self):
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(side_effect=RuntimeError("invalid_prompt"))),
            ),
        )
        session = {
            "map_state": {"web_layers": {}, "web_map": {}},
            "messages": [],
            "uploaded_dataset": None,
        }
        with patch.object(agent, "client", fake_client):
            events = list(agent._run_locked_session("Make a map.", "browser-a", session))

        self.assertEqual(events[-1]["status"], "failed")
        self.assertEqual(events[-1]["error_code"], "MODEL_REQUEST_FAILED")


if __name__ == "__main__":
    unittest.main()
