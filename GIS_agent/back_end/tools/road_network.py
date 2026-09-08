"""Versioned, fixed-path Hong Kong driving network. No AI-supplied paths."""
from pathlib import Path
from functools import lru_cache
import hashlib
import threading

NETWORK_PATH = Path(__file__).resolve().parents[3] / '.geoai-runtime' / 'networks' / 'hong_kong_drive.graphml'
NETWORK_LOCK = threading.Lock()


def load_network():
    if not NETWORK_PATH.is_file():
        raise ValueError('Road network is not prepared. Run python prepare_road_network.py in back_end first.')
    with NETWORK_LOCK:
        return _load(str(NETWORK_PATH), NETWORK_PATH.stat().st_mtime_ns)


@lru_cache(maxsize=1)
def _load(path, version):
    import osmnx as ox
    graph = ox.load_graphml(path)
    graph = ox.project_graph(graph, to_crs='EPSG:2326')
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return graph, {'network_id': 'hong_kong_drive', 'sha256': digest,
                   'prepared_at': graph.graph.get('prepared_at'),
                   'source': 'OpenStreetMap / OSMnx', 'network_type': 'drive',
                   'retained_all_components': True}
