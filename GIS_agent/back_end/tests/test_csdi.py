import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import init_map_state
from csdi_sources import download_dataset, normalize_features, SOURCES
from csdi_tools import csdi_nearby
from network_targets import target_travel_times
from point_datasets import load_point_dataset, PointDatasetError
from session_store import SessionStore
import requests
from shapely.geometry import Point, LineString
import networkx as nx


def feature(name='Test Gym', identity=1):
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [114.1, 22.3]},
            'properties': {'OBJECTID': identity, 'Name_ENG': name, 'Latitude': 0, 'Longitude': 0}}


def response(params):
    if params.get('resultType') == 'hits':
        return b'<FeatureCollection numberMatched="1"/>'
    return json.dumps({'type': 'FeatureCollection', 'features': [feature()]}).encode()


class CsdiTests(unittest.TestCase):
    def test_dynamic_catalog_bilingual_and_cache_expiry(self):
        import csdi_sources as src
        payload = {'archivedDatasetVersionList': [
            {'asdpId': 'lcsd_test_123', 'name': 'Badminton Courts', 'nameTC': '羽毛球場', 'nameSC': '羽毛球场'},
            {'asdpId': '../unsafe', 'name': 'Unsafe'}]}
        with patch.object(src, '_catalog_cache', {'expires': 0, 'items': []}), \
                patch.object(src, '_request', return_value=json.dumps(payload).encode()) as fetch, \
                patch.object(src.time, 'monotonic', return_value=100) as clock:
            self.assertEqual(src.catalog('badminton')[0]['id'], 'csdi_auto_lcsd_test_123')
            self.assertEqual(len(src.catalog('羽毛球')), 1)
            self.assertEqual(len(src.official_catalog()), 1)
            self.assertEqual(fetch.call_count, 1)
            clock.return_value = 1001
            src.official_catalog()
            self.assertEqual(fetch.call_count, 2)

    def test_dynamic_wfs_layer_and_download(self):
        import csdi_sources as src
        entry = {'id': 'csdi_auto_lcsd_test', 'dataset': 'lcsd_test', 'title': 'Badminton Courts',
                 'category': 'Badminton Courts', 'scope': 'Test'}
        caps = b'<WFS_Capabilities xmlns="http://www.opengis.net/wfs/2.0"><FeatureTypeList><FeatureType><Name>csdi:actual_layer</Name></FeatureType></FeatureTypeList></WFS_Capabilities>'
        def fetch(url, params):
            self.assertTrue(url.startswith('https://portal.csdi.gov.hk/server/services/common/'))
            if params.get('request') == 'GetCapabilities':
                return caps
            self.assertEqual(params['typeNames'], 'csdi:actual_layer')
            return response(params)
        with patch.object(src, 'official_catalog', return_value=[entry]), patch.object(src, '_request', side_effect=fetch):
            state = {}
            result = src.download_dataset(state, entry['id'])
            self.assertEqual(result['row_count'], 1)
            self.assertEqual(result['category'], 'Badminton Courts')
            with self.assertRaises(ValueError):
                src.download_dataset({}, 'csdi_auto_invented')

    def test_dynamic_multilayer_and_catalog_failure(self):
        import csdi_sources as src
        from csdi_tools import csdi_catalog
        entry = {'id': 'csdi_auto_test', 'dataset': 'test'}
        caps = b'<WFS_Capabilities xmlns="http://www.opengis.net/wfs/2.0"><FeatureType><Name>a</Name></FeatureType><FeatureType><Name>b</Name></FeatureType></WFS_Capabilities>'
        with patch.object(src, 'official_catalog', return_value=[entry]), patch.object(src, '_request', return_value=caps):
            with self.assertRaisesRegex(ValueError, 'unambiguous'):
                src.resolve_source(entry['id'])
        with patch.object(src, 'official_catalog', side_effect=requests.Timeout('offline')):
            self.assertFalse(csdi_catalog({}, 'badminton')['ok'])

    def test_transport_fallback_is_bounded(self):
        from csdi_sources import _request
        with patch('csdi_sources._request_once', side_effect=[requests.Timeout('proxy timeout'), b'ok']) as fetch:
            self.assertEqual(_request('fixed-url', {}), b'ok')
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(fetch.call_args_list[0].kwargs['direct'])
            self.assertFalse(fetch.call_args_list[1].kwargs['direct'])

    def test_transport_exhausted_after_three_attempts(self):
        from csdi_sources import _request
        with patch('csdi_sources._request_once', side_effect=requests.Timeout('offline')) as fetch:
            with self.assertRaises(requests.Timeout):
                _request('fixed-url', {})
            self.assertEqual(fetch.call_count, 3)

    def test_stale_catalog_is_labelled_and_cold_failure_is_clear(self):
        import csdi_sources as src
        cache = {'expires': 0, 'items': [{'id': 'test', 'scope': 'Official metadata'}]}
        with patch.object(src, '_catalog_cache', cache), patch.object(src, '_request', side_effect=requests.Timeout('offline')):
            self.assertTrue(src.official_catalog()[0]['catalog_stale'])
            self.assertIn('cached catalogue', src.official_catalog()[0]['scope'])
        with patch.object(src, '_catalog_cache', {'expires': 0, 'items': []}), patch.object(src, '_request', side_effect=requests.Timeout('offline')):
            with self.assertRaisesRegex(ValueError, 'No cached catalogue'):
                src.official_catalog()
    def test_geometry_not_attribute_coordinates(self):
        frame, errors = normalize_features([feature()], SOURCES['csdi_fitness_rooms'])
        self.assertFalse(errors)
        self.assertEqual(frame.iloc[0].Latitude, 22.3)
        self.assertIn('"Latitude": 0', frame.iloc[0].source_properties)

    def test_lcsd_nameen_field(self):
        f = feature()
        f['properties']['NameEN'] = f['properties'].pop('Name_ENG')
        frame, errors = normalize_features([f], SOURCES['csdi_fitness_rooms'])
        self.assertFalse(errors)
        self.assertEqual(frame.iloc[0].NAME, 'Test Gym')

    def test_http_session_api(self):
        from server import app
        from agent import SESSION_STORE
        client = app.test_client()
        session_id = 'csdi-api-unit-test'
        try:
            with patch('csdi_sources._request', side_effect=lambda url, params: response(params)):
                result = client.post('/api/csdi', json={'session_id': session_id, 'dataset_id': 'csdi_fitness_rooms'})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json['ok'])
            self.assertEqual(len(client.get('/api/csdi', query_string={'session_id': session_id}).json['temporary_datasets']), 1)
            self.assertEqual(client.post('/api/csdi', json={'dataset_id': 'csdi_fitness_rooms'}).status_code, 400)
        finally:
            SESSION_STORE.clear(session_id)

    def test_multiple_snapshots_and_session_isolation(self):
        a, b = {}, {}
        with patch('csdi_sources._request', side_effect=lambda url, params: response(params)):
            download_dataset(a, 'csdi_fitness_rooms')
            download_dataset(a, 'csdi_ambulance_depots')
        self.assertEqual(len(a['temporary_datasets']), 2)
        with self.assertRaises(PointDatasetError):
            load_point_dataset(b, 'csdi_fitness_rooms')
        _, copy = load_point_dataset(a, 'csdi_fitness_rooms')
        copy.loc[0, 'NAME'] = 'Changed'
        self.assertEqual(a['temporary_datasets']['csdi_fitness_rooms']['dataframe'].iloc[0].NAME, 'Test Gym')

    def test_refresh_failure_keeps_valid_snapshot(self):
        state = {}
        with patch('csdi_sources._request', side_effect=lambda url, params: response(params)):
            before = download_dataset(state, 'csdi_fitness_rooms')
        with patch('csdi_sources._request', return_value=b'<FeatureCollection numberMatched="0"/>'):
            with self.assertRaises(ValueError):
                download_dataset(state, 'csdi_fitness_rooms', refresh=True)
        self.assertIs(before, state['temporary_datasets']['csdi_fitness_rooms'])

    def test_arbitrary_url_never_requested(self):
        with patch('csdi_sources._request') as request:
            with self.assertRaises(ValueError):
                download_dataset({}, 'http://localhost/secret')
            request.assert_not_called()

    def test_incomplete_paging_rejected(self):
        with patch('csdi_sources._request', side_effect=[b'<FeatureCollection numberMatched="2"/>', response({})]):
            with self.assertRaises(ValueError):
                download_dataset({}, 'csdi_fitness_rooms')

    def test_duplicate_id_rejected(self):
        _, errors = normalize_features([feature(), feature()], SOURCES['csdi_fitness_rooms'])
        self.assertEqual(len(errors), 1)

    def test_clear_removes_temporary_store(self):
        sessions = SessionStore()
        sessions.get_or_create('A')['temporary_datasets'] = {'test': {}}
        sessions.clear('A')
        self.assertNotIn('temporary_datasets', sessions.get_or_create('A'))

    def test_cross_dataset_buffer_and_ambiguous_name(self):
        state = init_map_state()
        with patch('csdi_sources._request', side_effect=lambda url, params: response(params)):
            result = csdi_nearby(state, 'Test Gym')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['data']['analysis']['matched_count'], 1)
        self.assertEqual(len(result['data']['analysis']['sources']), 2)
        frame = state['temporary_datasets']['csdi_fitness_rooms']['dataframe']
        frame.loc[1] = frame.iloc[0]
        self.assertEqual(csdi_nearby(state, 'Test Gym')['code'], 'AMBIGUOUS_ORIGIN')


class DirectedTargetsTests(unittest.TestCase):
    def graph(self, reverse=False):
        graph = nx.MultiDiGraph()
        graph.add_node(0, x=0, y=0)
        graph.add_node(1, x=100, y=0)
        graph.add_edge(0, 1, geometry=LineString([(0, 0), (100, 0)]))
        if reverse:
            graph.add_edge(1, 0, geometry=LineString([(100, 0), (0, 0)]))
        return graph

    def test_one_way_same_edge_and_budget(self):
        _, rows = target_travel_times(self.graph(), Point(50, 0), [Point(25, 0), Point(75, 0), Point(90, 0)], .5, 3.6)
        self.assertEqual([x['status'] for x in rows], ['not_reachable_within_time', 'within_time', 'not_reachable_within_time'])
        self.assertEqual(rows[1]['travel_seconds'], 25)

    def test_two_way_and_connectors(self):
        _, rows = target_travel_times(self.graph(True), Point(50, 10), [Point(25, 10)], 1, 3.6)
        self.assertEqual(rows[0]['travel_seconds'], 45)

    def test_far_target_excluded(self):
        _, rows = target_travel_times(self.graph(), Point(50, 0), [Point(75, 101)])
        self.assertEqual(rows[0]['status'], 'excluded_too_far')

    def test_junction_endpoint(self):
        _, rows = target_travel_times(self.graph(), Point(0, 0), [Point(100, 0)], 2, 3.6)
        self.assertEqual(rows[0]['travel_seconds'], 100)
