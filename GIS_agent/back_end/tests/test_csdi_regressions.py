"""Regression checks for the four-source stability audit."""
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import patch
from test_csdi import response
from tools import init_map_state
from agent import _normalize_map_arguments, _update_web_layer_stack, _verified_csdi_summary
from csdi_tools import csdi_map, csdi_download
import csdi_sources as sources


class CsdiRegressionTests(unittest.TestCase):
    def test_successful_fallback_route_is_reused(self):
        with patch.object(sources, '_transport', threading.local()), \
                patch.object(sources.time, 'sleep'), \
                patch.object(sources, '_request_once', side_effect=[sources.requests.Timeout('direct'), b'ok', b'next']) as fetch:
            sources._request(sources.CATALOG_URL, {})
            sources._request(sources.CATALOG_URL, {})
            self.assertEqual([call.kwargs['direct'] for call in fetch.call_args_list], [True, False, False])

    def test_model_false_success_cannot_override_actual_layers(self):
        import agent
        state = {'temporary_datasets': {key: {} for key in ['csdi_a', 'csdi_b', 'csdi_c', 'csdi_d']},
                 'web_layers': {'csdi_a': {'id': 'csdi_a', 'kind': 'point', 'geojson': {'features': []}}}}
        session = {'map_state': state, 'messages': [], 'temporary_datasets': state['temporary_datasets']}
        answer = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='All four layers are displayed.', tool_calls=[]))])
        with patch.object(agent.client.chat.completions, 'create', return_value=answer):
            events = list(agent._run_locked_session('Show all four datasets on the map.', 'test', session))
        self.assertEqual(events[-1]['status'], 'failed')
        self.assertEqual(events[-1]['error_code'], 'INCOMPLETE_MAP_LAYERS')
        self.assertNotIn('All four layers are displayed', events[-1]['log'])

    def test_mixed_replace_then_overlay_keeps_four_layers(self):
        state = init_map_state()
        prompt = 'Restore the four-source point map: first replace_existing=true, then replace_existing=false.'
        ids = ['csdi_fitness_rooms', 'csdi_ambulance_depots', 'csdi_test_a', 'csdi_test_b']
        source = sources.SOURCES['csdi_fitness_rooms']
        with patch.dict(sources.SOURCES, {key: {**source, 'category': key} for key in ids}), \
                patch.object(sources, '_request', side_effect=lambda url, params: response(params)):
            for i, key in enumerate(ids):
                args = _normalize_map_arguments('csdi_map', {'dataset_id': key, 'replace_existing': i == 0}, prompt)
                result = csdi_map(state, **args)
                self.assertTrue(result['ok'], result)
                _update_web_layer_stack(state, 'csdi_map', result['data'])
            self.assertEqual(len(state['web_layers']), 4)
            colors = [next(iter(layer['analysis']['category_colors'].values())) for layer in state['web_layers'].values()]
            self.assertEqual(len(set(colors)), 4)
            before = dict(state['csdi_layer_colors'])
            for key in reversed(ids):
                self.assertTrue(csdi_map(state, key, replace_existing=False)['ok'])
            self.assertEqual(before, state['csdi_layer_colors'])
            result = csdi_map(state, ids[0], color='#123456')
            self.assertTrue(result['ok'])
            self.assertEqual(state['csdi_layer_colors'][ids[0]], '#123456')

    def test_final_summary_distinguishes_cached_and_rendered(self):
        state = {'temporary_datasets': {'csdi_a': {}, 'csdi_b': {}, 'csdi_c': {}, 'csdi_d': {}},
                 'web_layers': {'csdi_a': {'id': 'csdi_a', 'geojson': {'features': []}}}}
        text, missing = _verified_csdi_summary(state, 'Show all four datasets on the map.')
        self.assertEqual(len(missing), 3)
        self.assertIn('Current map: 1 layers.', text)
        self.assertIn('Cached datasets: 4.', text)
        _, missing = _verified_csdi_summary(state, 'Download all four datasets.')
        self.assertFalse(missing)

    def test_timeout_is_not_reported_as_incompatible(self):
        entry = {'id': 'csdi_auto_timeout_test', 'dataset': 'timeout_test'}
        with patch.object(sources, 'official_catalog', return_value=[entry]), \
                patch.object(sources, '_request', side_effect=sources.requests.Timeout('offline')):
            result = csdi_download({}, entry['id'])
            self.assertEqual(result['code'], 'CSDI_NETWORK_ERROR')

    def test_capabilities_reused_without_redownload(self):
        entry = {'id': 'csdi_auto_cache_test', 'dataset': 'cache_test'}
        xml = b'<WFS_Capabilities xmlns="http://www.opengis.net/wfs/2.0"><FeatureType><Name>csdi:test</Name></FeatureType></WFS_Capabilities>'
        with patch.object(sources, '_capabilities_cache', {}), \
                patch.object(sources, 'official_catalog', return_value=[entry]), \
                patch.object(sources, '_request', return_value=xml) as fetch:
            self.assertEqual(sources.resolve_source(entry['id'])['layer'], 'csdi:test')
            self.assertEqual(sources.resolve_source(entry['id'])['layer'], 'csdi:test')
            self.assertEqual(fetch.call_count, 1)
