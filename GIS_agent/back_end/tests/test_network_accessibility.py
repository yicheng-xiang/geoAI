import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import networkx as nx
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from network_accessibility import reachable_segments, network_service_area


def road_graph(reverse=False):
    graph = nx.MultiDiGraph(crs='EPSG:2326')
    for n, x in enumerate([0, 100, 200]):
        graph.add_node(n, x=x, y=0)
    graph.add_edge(0, 1, geometry=LineString([(0, 0), (100, 0)]))
    graph.add_edge(1, 2, geometry=LineString([(100, 0), (200, 0)]))
    if reverse:
        graph.add_edge(1, 0, geometry=LineString([(0, 0), (100, 0)]))
    return graph


class NetworkTests(unittest.TestCase):
    def test_mid_edge_one_way_partial_cutoff(self):
        parts, reports, _, _ = reachable_segments(road_graph(), [Point(50, 0)], 75, 3.6)
        result = unary_union(parts)
        self.assertEqual(result.bounds, (50., 0., 125., 0.))
        self.assertEqual(reports[0]['status'], 'matched')

    def test_bidirectional_and_reversed_geometry(self):
        parts, _, _, _ = reachable_segments(road_graph(True), [Point(50, 0)], 25, 3.6)
        self.assertEqual(unary_union(parts).bounds, (25., 0., 75., 0.))

    def test_connector_time_deducted(self):
        parts, _, _, _ = reachable_segments(road_graph(), [Point(50, 10)], 25, 3.6)
        self.assertEqual(unary_union(parts).bounds, (50., 0., 65., 0.))

    def test_far_origin_excluded(self):
        parts, reports, _, _ = reachable_segments(road_graph(), [Point(50, 101)], 300, 30)
        self.assertEqual(parts, [])
        self.assertEqual(reports[0]['status'], 'excluded_too_far')

    def test_disconnected_component_not_joined(self):
        graph = road_graph()
        graph.add_node(3, x=0, y=10)
        graph.add_node(4, x=200, y=10)
        graph.add_edge(3, 4, geometry=LineString([(0, 10), (200, 10)]))
        parts, _, _, _ = reachable_segments(graph, [Point(50, 0)], 300, 30)
        self.assertEqual(unary_union(parts).bounds[3], 0)

    def test_multiple_origins_and_monotonic_time(self):
        graph = road_graph(True)
        short, _, _, _ = reachable_segments(graph, [Point(25, 0), Point(125, 0)], 10, 3.6)
        long, _, _, _ = reachable_segments(graph, [Point(25, 0), Point(125, 0)], 30, 3.6)
        self.assertTrue(unary_union(long).covers(unary_union(short)))

    def test_invalid_parameters_never_load_network(self):
        with patch('network_accessibility.load_network') as load:
            for value in [0, -1, 31, float('nan'), 'bad']:
                self.assertFalse(network_service_area({}, time_minutes=value)['ok'])
            load.assert_not_called()

    def test_path_rejected(self):
        result = network_service_area({}, dataset_id='../secret.csv')
        self.assertEqual(result['code'], 'UNREGISTERED_DATASET')

    def test_structured_layers_and_named_origin(self):
        state = {'gdf': gpd.GeoDataFrame(geometry=[Point(114.1, 22.3).buffer(0.1)], crs=4326)}
        frame = pd.DataFrame({'Name': ['Depot A', 'Depot B'], 'Latitude': [22.3, 22.3],
                              'Longitude': [114.1, 114.11], 'FacilityType': ['Ambulance Depot'] * 2})
        point = gpd.GeoSeries([Point(114.1, 22.3)], crs=4326).to_crs(2326).iloc[0]
        graph = nx.MultiDiGraph(crs='EPSG:2326')
        graph.add_node(0, x=point.x - 50, y=point.y)
        graph.add_node(1, x=point.x + 500, y=point.y)
        graph.add_edge(0, 1)
        with patch('network_accessibility.load_point_dataset', return_value=({'crs': 'EPSG:4326'}, frame)), \
                patch('network_accessibility.load_network', return_value=(graph, {'sha256': 'test'})):
            result = network_service_area(state, facility_types=['Ambulance Depot'], facility_name='Depot A')
        self.assertTrue(result['ok'], result)
        data = result['data']
        self.assertEqual(data['summary']['matched_origins'], 1)
        self.assertEqual(data['statistics'][0]['name'], 'Depot A')
        self.assertEqual([layer['kind'] for layer in data['visualization_layers']], ['polygon', 'line', 'point'])
        self.assertEqual(data['analysis']['output_crs'], 'EPSG:4326')
        self.assertTrue(all(gpd.GeoDataFrame.from_features(layer['geojson']).is_valid.all()
                            for layer in data['visualization_layers']))
        self.assertIs(state['last_analysis'], data)


if __name__ == '__main__':
    unittest.main()
