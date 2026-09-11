"""Prepare a reusable driving network once, outside interactive requests."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import osmnx as ox
from tools.road_network import NETWORK_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--mode', choices=['drive', 'walk'], default='drive')
    parser.add_argument('--cache-folder', help='Optional administrator-supplied OSMnx HTTP cache folder')
    args = parser.parse_args()
    network_path = NETWORK_PATH if args.mode == 'drive' else NETWORK_PATH.with_name('hong_kong_walk.graphml')
    if network_path.exists() and not args.refresh:
        print(f'Network already prepared: {network_path}')
        return
    NETWORK_PATH.parent.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = args.cache_folder or str(NETWORK_PATH.parent / 'http_cache')
    ox.settings.use_cache = True
    ox.settings.requests_timeout = 180
    ox.settings.log_console = True
    graph = ox.graph_from_place('Hong Kong', network_type=args.mode, retain_all=True)
    graph.graph['prepared_at'] = datetime.now(timezone.utc).isoformat()
    temporary = network_path.with_suffix('.tmp.graphml')
    ox.save_graphml(graph, temporary)
    os.replace(temporary, network_path)
    print(f'Prepared {len(graph)} nodes and {graph.number_of_edges()} directed edges: {network_path}')


if __name__ == '__main__':
    main()
