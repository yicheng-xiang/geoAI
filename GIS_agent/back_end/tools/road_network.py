"""Versioned, fixed-path Hong Kong driving network. No AI-supplied paths."""
from pathlib import Path
from functools import lru_cache
import hashlib
import threading

NETWORK_PATH = Path(__file__).resolve().parents[3] / '.geoai-runtime' / 'networks' / 'hong_kong_drive.graphml'
NETWORK_LOCK = threading.Lock()


def load_network(mode='drive'):
    if mode not in ('drive', 'walk'):
        raise ValueError('Network mode must be walk or drive.')
    path = NETWORK_PATH if mode == 'drive' else NETWORK_PATH.with_name('hong_kong_walk.graphml')
    if not path.is_file():
        raise ValueError(f'{mode} network is not prepared. Run python prepare_road_network.py --mode {mode}. Existing map is unchanged.')
    with NETWORK_LOCK:
        graph, metadata = _load(str(path), path.stat().st_mtime_ns)
        return graph, {**metadata, 'network_id': f'hong_kong_{mode}', 'network_type': mode}


@lru_cache(maxsize=2)
def _load(path, version):
    import osmnx as ox
    graph = ox.load_graphml(path)
    graph = ox.project_graph(graph, to_crs='EPSG:2326')
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return graph, {'network_id': 'hong_kong_drive', 'sha256': digest,
                   'prepared_at': graph.graph.get('prepared_at'),
                   'source': 'OpenStreetMap / OSMnx', 'network_type': 'drive',
                   'retained_all_components': True}
