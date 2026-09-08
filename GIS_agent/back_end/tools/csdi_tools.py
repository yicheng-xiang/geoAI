"""Natural-language tools combining independently registered CSDI snapshots."""
import math
import hashlib
import requests
import geopandas as gpd
import pandas as pd
from csdi_sources import catalog, download_dataset, public_datasets, CsdiServiceUnavailable
from layer_styles import add_points_layer
from buffer_analysis import buffer_facility_coverage
from network_accessibility import network_service_area, collection
from network_targets import target_travel_times
from road_network import load_network
from tool_results import tool_success, tool_error


def csdi_catalog(state, query=''):
    try:
        entries = catalog(query)
    except Exception as exc:
        return tool_error('CSDI_CATALOG_FAILED', str(exc))
    return tool_success(str(entries) + ' Temporary snapshots: ' + str(public_datasets(state)),
                        data={'catalog': entries, 'temporary_datasets': public_datasets(state)})


def csdi_download(state, dataset_id, refresh=False):
    try:
        dataset = download_dataset(state, dataset_id, refresh)
        return tool_success(f"{dataset['title']}: {dataset['row_count']} records ready as {dataset_id}. "
                            f"{dataset['scope']}", data={'temporary_datasets': public_datasets(state)})
    except Exception as exc:
        code = ('CSDI_SERVICE_UNAVAILABLE' if isinstance(exc, CsdiServiceUnavailable)
                else 'CSDI_NETWORK_ERROR' if isinstance(exc, requests.RequestException)
                else 'CSDI_DOWNLOAD_FAILED')
        return tool_error(code, str(exc))


def _provenance(dataset):
    return {k: dataset[k] for k in ['id', 'source_url', 'source_dataset_id', 'sha256', 'downloaded_at', 'scope']}


def csdi_map(state, dataset_id, replace_existing=True, color=None):
    fetched = csdi_download(state, dataset_id)
    if not fetched['ok']:
        return fetched
    dataset = state['temporary_datasets'][dataset_id]
    colors = state.setdefault('csdi_layer_colors', {})
    if color is not None:
        from color_palettes import literal_color
        color = literal_color(color)
        if color is None:
            return tool_error('INVALID_COLOR', 'Use a valid CSS hex color or supported named color.')
    if dataset_id not in colors:
        palette = ['#2563eb', '#d97706', '#0d9488', '#9333ea', '#dc2626', '#475569', '#be185d', '#65a30d']
        start = int(hashlib.sha256(dataset_id.encode()).hexdigest()[:8], 16) % len(palette)
        choices = palette[start:] + palette[:start]
        colors[dataset_id] = next((value for value in choices if value not in colors.values()), choices[0])
    color = color or colors[dataset_id]
    result = add_points_layer(state, dataset_id=dataset_id, facility_types=[dataset['category']],
                              replace_existing=replace_existing, cmap=color)
    if result['ok']:
        colors[dataset_id] = color
        result['data']['analysis']['sources'] = [_provenance(dataset)]
        result['data']['visualization_layers'] = [{'id': dataset_id, 'kind': 'point',
            'geojson': result['data']['geojson'], 'analysis': result['data']['analysis']}]
        result['data']['temporary_datasets'] = public_datasets(state)
        result['message'] += ' ' + dataset['scope']
    return result


def csdi_nearby(state, origin_name, origin_dataset_id='csdi_fitness_rooms',
                target_dataset_id='csdi_ambulance_depots', mode='buffer', radius_m=500,
                time_minutes=5, speed_kmh=30):
    """Named origin must resolve uniquely; no guessed or averaged coordinates."""
    try:
        radius, minutes, speed = float(radius_m), float(time_minutes), float(speed_kmh)
        if mode not in ('buffer', 'driving') or not all(map(math.isfinite, [radius, minutes, speed])):
            raise ValueError('Choose buffer or driving and finite numeric parameters.')
        if not (0 < radius <= 50000 and 0 < minutes <= 30 and 1 <= speed <= 100):
            raise ValueError('Radius: (0, 50000] m; time: (0, 30] min; speed: [1, 100] km/h.')
        for dataset_id in (origin_dataset_id, target_dataset_id):
            fetched = csdi_download(state, dataset_id)
            if not fetched['ok']:
                return fetched
        source = state['temporary_datasets'][origin_dataset_id]
        target = state['temporary_datasets'][target_dataset_id]
        frame = source['dataframe']
        query = str(origin_name).strip().casefold()
        if not query:
            raise ValueError('Specify a named origin facility.')
        # Search English names or original multilingual properties; prefer an exact name.
        exact = frame[frame.NAME.str.casefold().eq(query)]
        chosen = exact if len(exact) else frame[
            frame.NAME.str.casefold().str.contains(query, regex=False) |
            frame.source_properties.str.casefold().str.contains(query, regex=False)]
        if len(chosen) != 1:
            candidates = chosen.NAME.head(12).tolist() if len(chosen) else frame.NAME.head(12).tolist()
            return tool_error('AMBIGUOUS_ORIGIN' if len(chosen) else 'ORIGIN_NOT_FOUND',
                              f'Please specify one facility. Candidates: {candidates}')
        row = chosen.iloc[0]
        sources = [_provenance(source), _provenance(target)]
        if mode == 'buffer':
            result = buffer_facility_coverage(state, latitude=row.Latitude, longitude=row.Longitude,
                radius_m=radius, dataset_id=target_dataset_id, facility_types=[target['category']], location_name=row.NAME)
        else:
            graph, _ = load_network()
            origin_points = gpd.GeoSeries(gpd.points_from_xy(chosen.Longitude, chosen.Latitude), crs=4326).to_crs(2326)
            targets = target['dataframe']
            target_points = gpd.GeoSeries(gpd.points_from_xy(targets.Longitude, targets.Latitude), crs=4326).to_crs(2326)
            origin_quality, reports = target_travel_times(graph, origin_points.iloc[0], list(target_points), minutes, speed)
            # Reuse the existing road/corridor map pipeline without replacing any session dataset.
            working = dict(state)
            working['uploaded_dataset'] = {'id': 'session_upload', 'crs': 'EPSG:4326',
                'dataframe': pd.DataFrame([row.to_dict()])}
            result = network_service_area(working, minutes, speed, dataset_id='session_upload')
            if not result['ok']:
                return result
            data = result['data']
            statistics, matched_rows = [], []
            for (_, facility), point, report in zip(targets.iterrows(), target_points, reports):
                statistics.append({'name': facility.NAME, 'source_feature_id': facility.source_feature_id, **report})
                if report['status'] == 'within_time':
                    matched_rows.append({'NAME': facility.NAME, 'FACILITY_TYPE': target['category'],
                                         **report, 'geometry': point})
            matched_json = collection(matched_rows) if matched_rows else {'type': 'FeatureCollection', 'features': []}
            data['statistics'] = statistics
            data['summary']['matched_facilities'] = len(matched_rows)
            data['quality']['target_snapping'] = reports
            data['quality']['origin_snapping'] = origin_quality
            data['analysis'].update(dataset_id=target_dataset_id, origin_dataset_id=origin_dataset_id,
                facility_name=row.NAME, matched_facilities=len(matched_rows), target_category=target['category'])
            for layer in data['visualization_layers']:
                layer['analysis'].update(data['analysis'])
            data['visualization_layers'].append({'id': 'network_targets', 'kind': 'point', 'geojson': matched_json,
                'analysis': {**data['analysis'], 'visual_role': 'network_targets', 'category_colors': {target['category']: '#d97757'},
                             'point_style': {'symbol': 'facility', 'stroke_color': '#ffffff'}}})
            data['geojson']['features'].extend(matched_json['features'])
            result['message'] = (f"{len(matched_rows)} {target['category']} facilities reachable FROM {row.NAME} "
                f"within {minutes:g} minutes at {speed:g} km/h. Directed outbound travel; both access connectors "
                'included. Not emergency response time. Unreachable/over-budget targets are reported separately.')
        if result['ok']:
            data = result['data']
            data['analysis'].update(sources=sources, origin_dataset_id=origin_dataset_id, origin_name=row.NAME)
            for layer in data.get('visualization_layers', []):
                layer['analysis']['sources'] = sources
            data['temporary_datasets'] = public_datasets(state)
            state['last_analysis'] = data
        return result
    except Exception as exc:
        return tool_error('CSDI_ANALYSIS_FAILED', str(exc))
