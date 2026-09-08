"""Upstream HTTP-200 error pages must not be mistaken for WFS data."""
import threading
import unittest
from unittest.mock import patch

from test_csdi import response
import csdi_sources as sources
from csdi_tools import csdi_download, csdi_map, csdi_nearby
from tools import init_map_state

HTML = b'<!DOCTYPE html><html><body>ArcGIS Web Adaptor: Could not access any server machines.</body></html>'
CAPS = b'<WFS_Capabilities><FeatureTypeList><FeatureType><Name>csdi:test</Name></FeatureType></FeatureTypeList></WFS_Capabilities>'
ENTRY = {'id': 'csdi_auto_response_test', 'dataset': 'response_test',
         'title': 'Badminton Courts', 'category': 'Badminton Courts', 'scope': 'test'}


class CsdiResponseTests(unittest.TestCase):
    def test_html_retry_can_recover_and_reuses_successful_route(self):
        with patch.object(sources, '_transport', threading.local()), \
                patch.object(sources.time, 'sleep'), \
                patch.object(sources, '_request_once', side_effect=[HTML, CAPS, CAPS]) as fetch:
            params = {'request': 'GetCapabilities'}
            self.assertEqual(sources._request(sources.CATALOG_URL, params), CAPS)
            sources._request(sources.CATALOG_URL, params)
            self.assertEqual([c.kwargs['direct'] for c in fetch.call_args_list], [True, False, False])

    def test_html_retries_are_bounded_for_capabilities_hits_and_pages(self):
        for params in [{'request': 'GetCapabilities'},
                       {'request': 'GetFeature', 'resultType': 'hits'},
                       {'request': 'GetFeature', 'outputFormat': 'GeoJSON'}]:
            with self.subTest(params=params), patch.object(sources.time, 'sleep'), \
                    patch.object(sources, '_request_once', return_value=HTML) as fetch:
                with self.assertRaises(sources.CsdiServiceUnavailable):
                    sources._request('official-test', params)
                self.assertEqual(fetch.call_count, 3)

    def test_capabilities_html_is_not_multilayer_or_cached(self):
        with patch.object(sources, '_capabilities_cache', {}), \
                patch.object(sources, 'official_catalog', return_value=[ENTRY]), \
                patch.object(sources, '_request', return_value=HTML):
            result = csdi_map(init_map_state(), ENTRY['id'])
            self.assertFalse(result['ok'])
            self.assertEqual(result['code'], 'CSDI_SERVICE_UNAVAILABLE')
            self.assertNotIn('unambiguous', result['message'])
            self.assertEqual(sources._capabilities_cache, {})

    def test_cross_dataset_html_has_actionable_error_without_keyerror(self):
        state = init_map_state()
        with patch.object(sources, '_request', return_value=HTML):
            result = csdi_nearby(state, 'Tung Cheong Street Sports Centre')
        self.assertEqual(result['code'], 'CSDI_SERVICE_UNAVAILABLE')
        self.assertNotIn('numberMatched', result['message'])
        self.assertEqual(state['temporary_datasets'], {})

    def test_missing_unknown_and_invalid_counts_fail_closed(self):
        for attr in ['', 'numberMatched="unknown"', 'numberMatched="NaN"',
                     'numberMatched="-1"', 'numberMatched="1.5"']:
            with self.subTest(attr=attr):
                with self.assertRaisesRegex(ValueError, 'no valid numberMatched'):
                    sources._hit_count(f'<FeatureCollection {attr}/>'.encode())

    def test_ogc_exception_is_not_a_dataset_or_count(self):
        for parser in [sources._hit_count, sources._feature_page]:
            with self.assertRaisesRegex(ValueError, 'OGC exception'):
                parser(b'<ExceptionReport><Exception>Invalid parameter</Exception></ExceptionReport>')

    def test_invalid_capabilities_do_not_claim_multiple_layers(self):
        with self.assertRaisesRegex(ValueError, 'did not return WFS_Capabilities'):
            sources._parse_xml(b'<Other/>', 'WFS_Capabilities')

    def test_invalid_pages_are_not_imported(self):
        for payload in [b'{}', b'[]', b'not JSON', b'{"type":"FeatureCollection"}',
                        b'{"type":"FeatureCollection","features":[null]}']:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                sources._feature_page(payload)

    def test_refresh_error_preserves_all_snapshots(self):
        state = init_map_state()
        with patch.object(sources, '_request', side_effect=lambda url, params: response(params)):
            first = sources.download_dataset(state, 'csdi_fitness_rooms')
            second = sources.download_dataset(state, 'csdi_ambulance_depots')
        for replies in [[HTML], [response({'resultType': 'hits'}), HTML]]:
            with patch.object(sources, '_request', side_effect=replies):
                result = csdi_download(state, 'csdi_fitness_rooms', refresh=True)
                self.assertEqual(result['code'], 'CSDI_SERVICE_UNAVAILABLE')
            self.assertIs(state['temporary_datasets']['csdi_fitness_rooms'], first)
            self.assertIs(state['temporary_datasets']['csdi_ambulance_depots'], second)

    def test_healthy_download_still_succeeds_after_error(self):
        state = init_map_state()
        with patch.object(sources, '_request', return_value=HTML):
            self.assertFalse(csdi_download(state, 'csdi_fitness_rooms')['ok'])
        with patch.object(sources, '_request', side_effect=lambda url, params: response(params)):
            self.assertTrue(csdi_download(state, 'csdi_fitness_rooms')['ok'])
        self.assertEqual(state['temporary_datasets']['csdi_fitness_rooms']['row_count'], 1)
