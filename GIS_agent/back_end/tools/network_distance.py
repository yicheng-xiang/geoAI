"""Named-place, outbound shortest road distance; separate walk/drive networks."""
from copy import deepcopy
import math
from uuid import uuid4
import geopandas as gpd
from shapely.geometry import Point, shape
from buffer_analysis import buffer_facility_coverage
from network_targets import target_travel_times
from road_network import load_network
from tool_results import tool_error, tool_success


def network_distance_query(state, location_query, travel_mode, distance_m,
                           dataset_id='all_facilities', facility_types=None, replace_existing=True):
    try:
        limit = float(distance_m)
        if travel_mode not in ('walk', 'drive') or not math.isfinite(limit) or not 0 < limit <= 50000:
            return tool_error('INVALID_NETWORK_DISTANCE', 'Specify walk or drive and a distance in metres (0–50,000).')
        graph, provenance = load_network(travel_mode)
    except (ValueError, TypeError) as exc:
        return tool_error('NETWORK_DISTANCE_UNAVAILABLE', str(exc))
    # Euclidean prefilter is only a candidate bound. It is never the answer or
    # a displayed service area. Work in a copy until all network work succeeds.
    result = buffer_facility_coverage(dict(state), location_query=location_query, radius_m=limit,
        dataset_id=dataset_id, facility_types=facility_types, replace_existing=replace_existing)
    if not result['ok']:
        return result
    data = deepcopy(result['data'])
    analysis = data['analysis']
    features = [f for l in data['visualization_layers'] if l['analysis']['visual_role'] == 'matched_facilities'
                for f in l['geojson']['features']]
    center = analysis['center']
    points = gpd.GeoSeries([Point(center['longitude'], center['latitude']),
                          *[shape(f['geometry']) for f in features]], crs=4326).to_crs(2326)
    try:
        origin_report, reports = target_travel_times(graph, points.iloc[0], list(points.iloc[1:]), distance_m=limit, include_routes=True)
    except ValueError as exc:
        return tool_error('NETWORK_DISTANCE_FAILED', str(exc))
    matched, statistics, routes = [], [], []
    for feature, stat, report in zip(features, data['statistics'], reports):
        sid = uuid4().hex
        route = report.pop('route_geometry', None)
        # Straight-line distance from the candidate phase must not masquerade
        # as the shortest road distance in maps, tables or exports.
        feature['properties'].pop('distance_m', None)
        stat.pop('distance_m', None)
        feature['properties'].update(source_feature_id=sid, **report)
        statistics.append({**stat, **report, 'source_feature_id': sid})
        if report['status'] == 'within_distance':
            matched.append(feature)
            if route:
                geometry = gpd.GeoSeries([shape(route)], crs=2326).to_crs(4326).iloc[0]
                routes.append({'type': 'Feature', 'geometry': geometry.__geo_interface__, 'properties': {
                    'NAME': stat['name'], 'FACILITY_TYPE': stat['facility_type'],
                    'target_source_feature_id': sid, 'network_distance_m': report['network_distance_m'],
                    'analysis_role': 'shortest_route'}})
    analysis.pop('radius_m', None)
    analysis.update(method='network_distance', travel_mode=travel_mode, distance_m=limit,
        matched_count=len(matched), route_count=len(routes), target_category=', '.join(facility_types or []) or dataset_id,
        spatial_predicate='outbound_shortest_network_distance_lte_limit', network=provenance,
        access_distance_included=True, max_snap_m=100,
        limitation='Shortest road routes include straight-line access connectors; no verified entrances or live restrictions. No service-area polygon is generated.')
    layers = [l for l in data['visualization_layers'] if l['analysis']['visual_role'] != 'buffer_area']
    target = next((l for l in layers if l['analysis']['visual_role'] == 'matched_facilities'), None)
    if target is None:
        target = {'id': 'network_distance_targets', 'kind': 'point', 'geojson': {}, 'analysis': {'visual_role': 'matched_facilities'}}
        layers.insert(0, target)
    target['geojson'] = {'type': 'FeatureCollection', 'features': matched}
    palette = ['#d97772', '#4c86b5', '#8b6ca8', '#389d87', '#c58b36']
    categories = sorted({s['facility_type'] for s in statistics})
    colors = {category: palette[i % len(palette)] for i, category in enumerate(categories)}
    target['analysis']['category_colors'] = colors
    layers.insert(0, {'id': 'network_distance_routes', 'kind': 'line',
        'geojson': {'type': 'FeatureCollection', 'features': routes},
        'analysis': {'visual_role': 'shortest_routes', 'category_colors': colors}})
    for layer in layers:
        layer['analysis'].pop('radius_m', None)
        layer['analysis'].update(analysis)
    data.update(analysis=analysis, statistics=statistics, visualization_layers=layers,
        geojson={'type': 'FeatureCollection', 'features': [f for l in layers for f in l['geojson']['features']]},
        summary={'matched_count': len(matched), 'route_count': len(routes), 'candidate_count': len(features), 'distance_m': limit, 'travel_mode': travel_mode})
    data['quality']['origin_snapping'] = origin_report
    data['quality']['network_candidates'] = reports
    for key in ('matched_to_buffer', 'outside_buffer'):
        data['quality']['points'].pop(key, None)
    state['last_analysis'] = data
    return tool_success(f'{len(matched)} facilities within {limit:g} m {travel_mode} network distance of {analysis["location_name"]}; {len(routes)} shortest-route features generated. Only matched facilities are displayed; no service-area polygon. Access distances included.' ,
                        code='NETWORK_DISTANCE_COMPLETED', data=data)
