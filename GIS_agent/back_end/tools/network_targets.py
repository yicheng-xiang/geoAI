"""Directed origin-to-facility travel times, with edge-interior access nodes."""
import math
import networkx as nx
from shapely.strtree import STRtree
from shapely.geometry import LineString, mapping
from shapely.ops import substring
from network_accessibility import directed_lines


def target_travel_times(graph, origin, targets, minutes=5, speed_kmh=30, max_snap_m=100, *, distance_m=None, include_routes=False):
    keys, lines = directed_lines(graph)
    if not lines:
        raise ValueError('No usable roads in the selected network.')
    tree = STRtree(lines)
    # Distance mode uses metre edge costs, not a fabricated driving duration.
    speed = 1.0 if distance_m is not None else speed_kmh / 3.6
    network = nx.MultiDiGraph()
    splits = {}
    reports = []
    for number, point in enumerate([origin, *targets]):
        nearest = int(tree.nearest(point))
        base = lines[nearest]
        snap = point.distance(base)
        reports.append({'snap_distance_m': round(snap, 3), 'status': 'matched' if snap <= max_snap_m else 'excluded_too_far'})
        if snap > max_snap_m:
            if number == 0:
                raise ValueError(f'Origin is {snap:.1f} m from the selected network; maximum is {max_snap_m} m.')
            continue
        u, v, _ = keys[nearest]
        for candidate in tree.query(base.envelope):
            i = int(candidate)
            a, b, _ = keys[i]
            if i != nearest and not ({a, b} == {u, v} and lines[i].equals(base)):
                continue
            offset = float(lines[i].project(point))
            vertex = ('edge', i, offset)
            if offset <= 1e-8:
                network.add_edge(vertex, ('node', a), weight=0)
            if abs(offset - lines[i].length) <= 1e-8:
                network.add_edge(('node', b), vertex, weight=0)
            splits.setdefault(i, {})[offset] = vertex
            terminal = ('facility', number)
            if number == 0:
                network.add_edge(terminal, vertex, weight=snap / speed,
                                 connector=[tuple(point.coords[0]), tuple(lines[i].interpolate(offset).coords[0])])
            else:
                network.add_edge(vertex, terminal, weight=snap / speed,
                                 connector=[tuple(lines[i].interpolate(offset).coords[0]), tuple(point.coords[0])])
    for i, ((u, v, _), line) in enumerate(zip(keys, lines)):
        previous, position = ('node', u), 0.0
        for offset, vertex in sorted(splits.get(i, {}).items()):
            network.add_edge(previous, vertex, weight=max(0, offset - position) / speed, segment=(i, position, offset))
            previous, position = vertex, offset
        network.add_edge(previous, ('node', v), weight=max(0, line.length - position) / speed, segment=(i, position, line.length))
    cutoff = distance_m if distance_m is not None else minutes * 60
    if include_routes:
        distances, paths = nx.single_source_dijkstra(network, ('facility', 0), cutoff=cutoff, weight='weight')
    else:
        distances = nx.single_source_dijkstra_path_length(network, ('facility', 0), cutoff=cutoff, weight='weight')
    for number, report in enumerate(reports[1:], 1):
        duration = distances.get(('facility', number), math.inf)
        report['network_distance_m' if distance_m is not None else 'travel_seconds'] = round(duration, 3) if math.isfinite(duration) else None
        if report['status'] == 'matched':
            report['status'] = ('within_distance' if math.isfinite(duration) else 'not_reachable_within_distance') if distance_m is not None else ('within_time' if math.isfinite(duration) else 'not_reachable_within_time')
        if include_routes and math.isfinite(duration):
            path = paths[('facility', number)]
            coordinates = []
            for a, b in zip(path, path[1:]):
                edge = min(network[a][b].values(), key=lambda e: e['weight'])
                coords = edge.get('connector', [])
                if 'segment' in edge:
                    i, start, end = edge['segment']
                    coords = list(substring(lines[i], start, end).coords)
                for coord in coords:
                    if not coordinates or coordinates[-1] != tuple(coord):
                        coordinates.append(tuple(coord))
            if len(coordinates) >= 2:
                report['route_geometry'] = mapping(LineString(coordinates))
    return reports[0], reports[1:]
