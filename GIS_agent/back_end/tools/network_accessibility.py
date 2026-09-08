"""Outbound driving coverage with edge snapping and partial-edge cutoffs."""
import heapq
import itertools
import math
import json
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString
from shapely.ops import substring
from shapely.strtree import STRtree
from shapely import union_all, buffer as buffer_geometries
from buffer_analysis import _filter_facilities, _name_column
from point_datasets import load_point_dataset, resolve_point_columns, PointDatasetError
from data_quality import validate_and_clean_point_table
from road_network import load_network
from tool_results import tool_error, tool_success


def directed_lines(graph):
    """Orient OSM geometry from u toward v; never manufacture missing length."""
    lines, keys = [], []
    for u, v, k, data in graph.edges(keys=True, data=True):
        start = Point(graph.nodes[u]['x'], graph.nodes[u]['y'])
        end = Point(graph.nodes[v]['x'], graph.nodes[v]['y'])
        line = data.get('geometry', LineString([start, end]))
        if line.geom_type != 'LineString' or line.is_empty or line.length <= 0:
            continue
        if Point(line.coords[-1]).distance(start) < Point(line.coords[0]).distance(start):
            line = LineString(list(line.coords)[::-1])
        lines.append(line)
        keys.append((u, v, k))
    return keys, lines


def reachable_segments(graph, origins, cutoff_s, speed_kmh, max_snap_m=100):
    """Multi-source directed Dijkstra with costs from edge-interior origins.

    Access connectors use the same scenario speed. Only coincident reverse
    edges are seeded, never other parallel carriageways or nearby flyovers.
    """
    keys, lines = directed_lines(graph)
    if not lines:
        raise ValueError('The driving network contains no usable road geometries.')
    tree = STRtree(lines)
    speed = speed_kmh / 3.6
    adjacency = {}
    for key, line in zip(keys, lines):
        adjacency.setdefault(key[0], []).append((key[1], line.length / speed))
    distances, heap, serial = {}, [], itertools.count()
    parts, reports = [], []
    def seed(node, cost):
        if cost <= cutoff_s and cost < distances.get(node, math.inf):
            distances[node] = cost
            heapq.heappush(heap, (cost, next(serial), node))
    for point in origins:
        index = int(tree.nearest(point))
        base = lines[index]
        snap_distance = point.distance(base)
        report = {'snap_distance_m': round(snap_distance, 3),
                  'status': 'matched' if snap_distance <= max_snap_m else 'excluded_too_far'}
        reports.append(report)
        if snap_distance > max_snap_m:
            continue
        connector_s = snap_distance / speed
        report['connector_seconds'] = round(connector_s, 3)
        report['edge'] = [str(x) for x in keys[index]]
        # Include reverse direction only for the very same physical geometry.
        candidates = tree.query(base.envelope)
        u, v, _ = keys[index]
        for candidate in candidates:
            i = int(candidate)
            a, b, _ = keys[i]
            line = lines[i]
            if i != index and not ({a, b} == {u, v} and line.equals(base)):
                continue
            offset = line.project(point)
            if offset <= 0.01:
                seed(a, connector_s)
            remaining = max(0, (cutoff_s - connector_s) * speed)
            finish = min(line.length, offset + remaining)
            if finish > offset:
                parts.append(substring(line, offset, finish))
            seed(b, connector_s + (line.length - offset) / speed)
    while heap:
        cost, _, node = heapq.heappop(heap)
        if cost != distances[node]:
            continue
        for target, duration in adjacency.get(node, []):
            seed(target, cost + duration)
    for (u, _, _), line in zip(keys, lines):
        remaining = (cutoff_s - distances.get(u, math.inf)) * speed
        if remaining > 0:
            parts.append(substring(line, 0, min(line.length, remaining)))
    return parts, reports, len(distances), len(keys)


def collection(rows):
    return json.loads(gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:2326')
                      .to_crs('EPSG:4326').to_json())


def network_service_area(state, time_minutes=5, speed_kmh=30,
                         dataset_id='all_facilities', facility_types=None,
                         facility_name=None, replace_existing=True):
    try:
        minutes, speed = float(time_minutes), float(speed_kmh)
        if not (math.isfinite(minutes) and 0 < minutes <= 30 and math.isfinite(speed) and 1 <= speed <= 100):
            raise ValueError()
    except (TypeError, ValueError):
        return tool_error('INVALID_NETWORK_PARAMETERS', 'Time must be in (0, 30] minutes and speed in [1, 100] km/h.')
    try:
        dataset, frame = load_point_dataset(state, dataset_id)
        lat, lon, category = resolve_point_columns(frame)
        cleaned, quality = validate_and_clean_point_table(frame, lat, lon, category,
            source_crs=dataset['crs'], study_bounds=state['gdf'].to_crs(dataset['crs']).total_bounds)
        filtered, error = _filter_facilities(cleaned, category, facility_types or [], dataset_id == 'session_upload')
        if error:
            return tool_error(*error)
        name = _name_column(filtered)
        if facility_name:
            if not name:
                return tool_error('MISSING_NAME_FIELD', 'This dataset has no facility names.')
            filtered = filtered[filtered[name].astype(str).str.contains(str(facility_name), case=False, regex=False)]
        if filtered.empty:
            return tool_error('NO_MATCHED_FACILITIES', 'No facilities matched the selected name and category.')
        if len(filtered) > 200:
            return tool_error('TOO_MANY_NETWORK_ORIGINS', 'Select at most 200 facilities per network analysis.')
        points = gpd.GeoDataFrame(filtered.copy(), geometry=gpd.points_from_xy(filtered[lon], filtered[lat]), crs=dataset['crs']).to_crs('EPSG:2326')
        graph, provenance = load_network()
        parts, reports, nodes, usable_edges = reachable_segments(graph, list(points.geometry), minutes * 60, speed)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)
    except (ImportError, ValueError, OSError) as exc:
        return tool_error('NETWORK_UNAVAILABLE', str(exc))
    matched = sum(row['status'] == 'matched' for row in reports)
    if not parts:
        return tool_error('NO_REACHABLE_ROADS', 'No reachable roads; check facility snap distances and time budget.', {'quality': {'origins': reports}})
    # Centimetre precision removes near-identical reversed-road coordinates.
    roads = union_all(parts, grid_size=0.01)
    # Cartographic corridor, not a population/land coverage estimate.
    # Buffer short segments separately: buffering a whole noded city network
    # creates an expensive global self-intersection operation in GEOS.
    corridors = buffer_geometries(parts, 30, quad_segs=4)
    batches = [union_all(corridors[i:i + 256], grid_size=0.1)
               for i in range(0, len(corridors), 256)]
    area = union_all(batches, grid_size=0.1).simplify(2, preserve_topology=True)
    analysis = {'method': 'network_service_area', 'dataset_id': dataset_id,
        'facility_types': facility_types or [], 'facility_name': facility_name,
        'time_minutes': minutes, 'speed_kmh': speed, 'speed_model': 'constant_scenario',
        'travel_direction': 'outbound', 'travel_mode': 'driving',
        'max_snap_distance_m': 100, 'corridor_width_m': 30,
        'road_precision_m': 0.01, 'corridor_precision_m': 0.1,
        'analysis_crs': 'EPSG:2326', 'output_crs': 'EPSG:4326',
        'matched_origins': matched, 'excluded_origins': len(reports) - matched,
        'replace_existing': bool(replace_existing), 'network': provenance,
        'limitations': ['Estimated driving time only; no traffic, turn restrictions/penalties, dispatch delay or vehicle availability.',
                       'Service polygon is an approximate 30 m road corridor, not population coverage.']}
    if dataset_id == 'session_upload':
        analysis.update(source_filename=dataset.get('filename'), source_sha256=dataset.get('sha256'))
    area_json = collection([{'NAME': f'{minutes:g}-minute estimated driving service area', 'coverage': 'Approximate service area', 'geometry': area}])
    road_json = collection([{'NAME': 'Reachable road segments', 'coverage': 'Reachable roads', 'geometry': roads}])
    origin_rows, statistics = [], []
    for (_, row), report in zip(points.iterrows(), reports):
        label = str(row[name]) if name else 'Facility'
        statistics.append({'name': label, **report})
        origin_rows.append({'NAME': label, 'FACILITY_TYPE': 'Matched origin' if report['status'] == 'matched' else 'Unmatched origin',
                            **report, 'geometry': row.geometry})
    origin_json = collection(origin_rows)
    layers = [
        {'id': 'network_area', 'kind': 'polygon', 'geojson': area_json, 'analysis': {**analysis, 'column': 'coverage',
            'category_colors': {'Approximate service area': '#60a5fa'},
            'polygon_style': {'fill_opacity': 0.18, 'stroke_width_px': 0, 'stroke_opacity': 0}}},
        {'id': 'network_roads', 'kind': 'line', 'geojson': road_json, 'analysis': {**analysis, 'column': 'coverage',
            'category_colors': {'Reachable roads': '#287e9c'},
            'polygon_style': {'fill_opacity': 0, 'stroke_color': '#287e9c', 'stroke_width_px': 1.5, 'stroke_opacity': 0.8}}},
        {'id': 'network_origins', 'kind': 'point', 'geojson': origin_json, 'analysis': {**analysis,
            'category_colors': {'Matched origin': '#3b9ab2', 'Unmatched origin': '#9ca3af'},
            'point_style': {'symbol': 'location', 'stroke_color': '#ffffff'}}}]
    result = {'analysis': analysis, 'statistics': statistics,
        'summary': {'matched_origins': matched, 'excluded_origins': len(reports) - matched,
                    'reachable_road_km': round(roads.length / 1000, 3), 'reachable_nodes': nodes},
        'quality': {'points': quality, 'origins': reports, 'usable_edges': usable_edges,
                    'weak_components': nx.number_weakly_connected_components(graph)},
        'geojson': {'type': 'FeatureCollection', 'features': area_json['features'] + road_json['features'] + origin_json['features']},
        'visualization_layers': layers}
    state['last_analysis'] = result
    return tool_success(f'Estimated {minutes:g}-minute driving coverage generated from {matched} facilities; '
        f'{len(reports) - matched} origins excluded. Constant speed {speed:g} km/h; approximate road corridor, not emergency response time.', data=result)
