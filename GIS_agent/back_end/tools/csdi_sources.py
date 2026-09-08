"""Bounded WFS downloads into a session-owned, in-memory dataset store.

No local catalogue files are changed. Only registered or official catalogue
services are reachable; model arguments cannot supply URLs or file paths.
"""
import hashlib
import json
import math
import re
import time
import threading
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import pandas as pd
import requests

SOURCES = {
    'csdi_fitness_rooms': {
        'title': 'Public Fitness Rooms (LCSD)', 'category': 'Fitness Room',
        'dataset': 'lcsd_rcd_1629267205215_5008', 'layer': 'csdi:FITNESS',
        'keywords': 'gym fitness rooms 健身房 健身室 康文署',
        'scope': 'LCSD public fitness rooms; not all commercial gyms.',
    },
    'csdi_ambulance_depots': {
        'title': 'Ambulance Depots (FSD)', 'category': 'Ambulance Depot',
        'dataset': 'hkfsd_rcd_1634799003993_7633', 'layer': 'csdi:AmbDepots',
        'keywords': 'ambulance depot rescue 救护站 救護站',
        'scope': 'Fire Services Department ambulance depots.',
    },
}
MAX_BYTES = 20 * 1024 * 1024
MAX_RECORDS = 10000
CATALOG_URL = 'https://portal.csdi.gov.hk/csdi-webpage/DatasetListJSON'
_catalog_cache = {'expires': 0, 'items': []}
_catalog_lock = threading.Lock()
_transport = threading.local()
_capabilities_cache = {}


class CsdiServiceUnavailable(requests.RequestException):
    """The upstream gateway returned an error page, even with HTTP 200."""


def _reject_error_page(content):
    head = content.lstrip()[:1024].lower()
    if b'<html' in head or b'<!doctype html' in head:
        raise CsdiServiceUnavailable(
            'Official CSDI WFS is temporarily unavailable: the server returned an HTML error page '
            'instead of spatial data. Please retry later. Existing snapshots are unchanged.')


def _parse_xml(content, expected_root):
    _reject_error_page(content)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError('Official WFS returned invalid XML; existing snapshots are unchanged.') from exc
    name = root.tag.split('}')[-1]
    if name.lower() == 'html':
        raise CsdiServiceUnavailable('Official CSDI WFS returned HTML instead of data. Please retry later; existing snapshots are unchanged.')
    if name in ('ExceptionReport', 'ServiceExceptionReport'):
        raise ValueError('Official WFS rejected the request with an OGC exception; no dataset was imported.')
    if name != expected_root:
        raise ValueError(f'Official WFS did not return {expected_root}; existing snapshots are unchanged.')
    return root


def _hit_count(content):
    root = _parse_xml(content, 'FeatureCollection')
    value = root.get('numberMatched')
    if value is None or not re.fullmatch(r'[0-9]+', value):
        raise ValueError('Official WFS returned no valid numberMatched count. Download completeness cannot be verified; existing snapshots are unchanged.')
    count = int(value)
    if not 0 < count <= MAX_RECORDS:
        raise ValueError('Unexpected WFS count; existing snapshot has been preserved.')
    return count


def _feature_page(content):
    _reject_error_page(content)
    if content.lstrip().startswith(b'<'):
        _parse_xml(content, 'FeatureCollection')
        raise ValueError('Official WFS returned XML instead of requested GeoJSON.')
    try:
        page = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Official WFS returned invalid GeoJSON; existing snapshots are unchanged.') from exc
    if not isinstance(page, dict) or page.get('type') != 'FeatureCollection' \
            or not isinstance(page.get('features'), list) \
            or not all(isinstance(feature, dict) for feature in page['features']):
        raise ValueError('WFS did not return GeoJSON features.')
    return page


def _validate_response(content, params):
    """Validate before treating a route as healthy or parsing result fields."""
    operation = params.get('request')
    if operation == 'GetCapabilities':
        _parse_xml(content, 'WFS_Capabilities')
    elif operation == 'GetFeature':
        if params.get('resultType') == 'hits':
            _hit_count(content)
        else:
            _feature_page(content)


def official_catalog():
    """Public metadata only; facility snapshots remain session-owned."""
    with _catalog_lock:
        if time.monotonic() < _catalog_cache['expires']:
            return _catalog_cache['items']
        try:
            payload = json.loads(_request(CATALOG_URL, {}))
        except requests.RequestException as exc:
            # An expired successful catalogue is useful during an outage, but
            # must never be presented as a freshly fetched catalogue.
            if _catalog_cache['items']:
                items = [{**item, 'catalog_stale': True,
                          'scope': item['scope'].split(' Warning: cached catalogue;')[0] +
                                   ' Warning: cached catalogue; live refresh unavailable.'}
                         for item in _catalog_cache['items']]
                _catalog_cache.update(items=items, expires=time.monotonic() + 60)
                return items
            raise ValueError('Official CSDI catalogue could not be reached after 3 attempts. '
                             'No cached catalogue is available. Please retry shortly; '
                             'existing facility snapshots are unchanged.') from exc
        records = payload.get('archivedDatasetVersionList')
        if not isinstance(records, list) or not records:
            raise ValueError('Official CSDI catalogue is unavailable. Try again later.')
        items = []
        for row in records:
            dataset = row.get('asdpId', '')
            if not re.fullmatch(r'[A-Za-z0-9_]{1,160}', dataset) or not row.get('name'):
                continue
            items.append({'id': 'csdi_auto_' + dataset, 'dataset': dataset,
                          'title': row['name'], 'category': row['name'],
                          'keywords': ' '.join(str(row.get(k) or '') for k in
                                              ['nameTC', 'nameSC', 'organization']),
                          'scope': str(row.get('organization') or 'CSDI') +
                                   '; WFS and point compatibility checked on download.',
                          'discovered': True})
        _catalog_cache.update(items=items, expires=time.monotonic() + 900)
        return items


def resolve_source(dataset_id):
    if dataset_id in SOURCES:
        return SOURCES[dataset_id]
    if not isinstance(dataset_id, str) or not re.fullmatch(r'csdi_auto_[A-Za-z0-9_]{1,160}', dataset_id):
        raise ValueError('Unregistered CSDI dataset. Search the official catalogue first.')
    source = next((dict(x) for x in official_catalog() if x['id'] == dataset_id), None)
    if source is None:
        raise ValueError('Dataset is not present in the official CSDI catalogue.')
    url = service_url(source)
    cached = _capabilities_cache.get(dataset_id)
    if cached and time.monotonic() < cached['expires']:
        source['layer'] = cached['layer']
        return source
    try:
        root = _parse_xml(_request(url, {'service': 'WFS', 'version': '2.0.0',
                                          'request': 'GetCapabilities'}), 'WFS_Capabilities')
        layers = [node.text for node in root.findall('.//{*}FeatureType/{*}Name') if node.text]
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise requests.Timeout('Official WFS connection timed out after retries. This does not mean the dataset is unsupported; retry later. Existing snapshots are unchanged.') from exc
    except requests.HTTPError as exc:
        raise requests.HTTPError('Official WFS returned an HTTP error; source compatibility is not confirmed.', response=exc.response) from exc
    except ET.ParseError as exc:
        raise ValueError('The service did not return valid WFS capabilities XML.') from exc
    if len(layers) != 1:
        raise ValueError('WFS must expose one unambiguous layer; this source requires a dedicated adapter.')
    source['layer'] = layers[0]
    _capabilities_cache[dataset_id] = {'layer': layers[0], 'expires': time.monotonic() + 900}
    return source


def service_url(source):
    return f"https://portal.csdi.gov.hk/server/services/common/{source['dataset']}/MapServer/WFSServer"


def catalog(query=''):
    terms = str(query).lower().split()
    entries = [{'id': key, **value} for key, value in SOURCES.items()]
    if terms:
        known = {x['dataset'] for x in entries}
        entries += [x for x in official_catalog() if x['dataset'] not in known]
    return [value for value in entries
            if all(term in (value['title'] + ' ' + value['keywords']).lower() for term in terms)]


def public_datasets(state):
    return [{k: v for k, v in dataset.items() if k != 'dataframe'}
            for dataset in state.get('temporary_datasets', {}).values()]


def _request(url, params):
    # Prefer direct access to this public HK service. Proxy configuration is
    # still available as fallback, and no global environment is modified.
    preference = getattr(_transport, 'preference', None)
    first = preference[0] if preference and time.monotonic() < preference[1] else True
    for attempt, direct in enumerate((first, not first, first)):
        try:
            result = _request_once(url, params, direct=direct)
            _validate_response(result, params)
            if url.startswith('https://portal.csdi.gov.hk/'):
                _transport.preference = (direct, time.monotonic() + 120)
            return result
        except (requests.ConnectionError, requests.Timeout, CsdiServiceUnavailable):
            if attempt == 2:
                raise
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code not in (429, 502, 503, 504) or attempt == 2:
                raise
        time.sleep(0.5 * (2 ** attempt))


def _request_once(url, params, direct=False):
    # System/application proxy settings and TLS verification are unchanged.
    # Per-thread pools avoid repeated TLS handshakes without sharing mutable
    # requests Sessions between Flask workers. Direct/proxy pools are separate.
    pools = getattr(_transport, 'pools', None)
    if pools is None:
        pools = _transport.pools = {}
    if direct not in pools:
        pools[direct] = requests.Session()
        pools[direct].trust_env = not direct
    return _read_response(pools[direct], url, params)


def _read_response(session, url, params):
    with session.get(url, params=params, timeout=(30, 45), stream=True,
                      allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Unexpected WFS response; redirects are not accepted.')
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError('WFS response exceeds the download size limit.')
        return bytes(content)


def normalize_features(features, source):
    rows, excluded = [], []
    ids = set()
    for index, feature in enumerate(features):
        props = feature.get('properties') or {}
        normalized = {str(k).lower(): v for k, v in props.items()}
        geometry = feature.get('geometry') or {}
        coordinates = geometry.get('coordinates') or []
        try:
            if geometry.get('type') != 'Point' or len(coordinates) < 2:
                raise ValueError('Missing point geometry')
            lon, lat = map(float, coordinates[:2])
            if not (math.isfinite(lon) and math.isfinite(lat) and 113.7 <= lon <= 114.6 and 22 <= lat <= 22.7):
                raise ValueError('Invalid Hong Kong WGS84 point')
            name = next((normalized[k] for k in ['name_eng', 'name_en', 'nameen', 'name_e', 'ename', 'name']
                         if normalized.get(k)), None)
            if not name:
                raise ValueError('Missing supported English name field')
            identity = str(props.get('GmlID') or feature.get('id') or props.get('OBJECTID') or '')
            if not identity or identity in ids:
                raise ValueError('Missing or duplicate WFS feature ID; incomplete paging is possible')
            ids.add(identity)
            rows.append({'NAME': ' '.join(str(name).split()), 'Latitude': lat, 'Longitude': lon,
                         'FACILITY_TYPE': source['category'], 'source_feature_id': identity,
                         'source_properties': json.dumps(props, ensure_ascii=False)})
        except (ValueError, TypeError) as exc:
            excluded.append({'record': index, 'reason': str(exc)})
    return pd.DataFrame(rows), excluded


def download_dataset(state, dataset_id, refresh=False):
    store = state.setdefault('temporary_datasets', {})
    if dataset_id in store and not refresh:
        return store[dataset_id]
    source = resolve_source(dataset_id)
    url = service_url(source)
    base = {'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': source['layer']}
    # hits must be XML: this service returns an empty response with GeoJSON hits.
    total = _hit_count(_request(url, {**base, 'resultType': 'hits'}))
    features = []
    for start in range(0, total, 1000):
        page = _feature_page(_request(url, {**base, 'outputFormat': 'GeoJSON', 'srsName': 'EPSG:4326',
                                         'count': 1000, 'startIndex': start}))
        if page.get('type') != 'FeatureCollection':
            raise ValueError('WFS did not return GeoJSON features.')
        crs = page.get('crs', {}).get('properties', {}).get('name', 'EPSG:4326')
        if crs not in ('EPSG:4326', 'urn:ogc:def:crs:EPSG::4326', 'urn:ogc:def:crs:OGC:1.3:CRS84'):
            raise ValueError('Unexpected WFS output CRS.')
        features.extend(page['features'])
    if len(features) != total:
        raise ValueError('Incomplete WFS download; existing snapshot has been preserved.')
    frame, excluded = normalize_features(features, source)
    if excluded or frame.empty:
        raise ValueError(f'WFS validation failed for {len(excluded)} records: {excluded[:3]}')
    canonical = json.dumps(features, sort_keys=True, ensure_ascii=False).encode('utf-8')
    dataset = {'id': dataset_id, 'title': source['title'], 'crs': 'EPSG:4326',
               'category': source['category'], 'scope': source['scope'], 'row_count': len(frame),
               'source_url': url, 'source_dataset_id': source['dataset'],
               'downloaded_at': datetime.now(timezone.utc).isoformat(),
               'sha256': hashlib.sha256(canonical).hexdigest(),
               'quality': {'valid_records': len(frame), 'excluded_records': 0,
                           'coordinate_source': 'WFS geometry; original attributes retained'},
               'dataframe': frame}
    # Commit only a fully downloaded and validated snapshot.
    store[dataset_id] = dataset
    return dataset
