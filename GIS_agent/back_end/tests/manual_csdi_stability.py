"""Opt-in real WFS stability probe. No model calls or local data writes.

Run from back_end: .venv/Scripts/python.exe -u tests/manual_csdi_stability.py
Output is JSON lines, including request-attempt timing and check results.
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import init_map_state
import csdi_sources as sources
from csdi_tools import csdi_map, csdi_nearby
from agent import _update_web_layer_stack, _web_map_payload


def emit(**data):
    print(json.dumps(data, ensure_ascii=True, default=str), flush=True)


def main():
    started = time.monotonic()
    state = init_map_state()
    checks, attempts, ids = [], [], []
    original_request = sources._request_once

    def request(url, params, direct=False):
        t = time.monotonic()
        entry = {'operation': params.get('request', 'catalogue'), 'direct': direct}
        try:
            result = original_request(url, params, direct=direct)
            entry.update(ok=True, bytes=len(result))
            return result
        except Exception as exc:
            entry.update(ok=False, error=str(exc))
            raise
        finally:
            entry['seconds'] = round(time.monotonic() - t, 2)
            attempts.append(entry)
            emit(request=entry)

    def check(name, action):
        t = time.monotonic()
        try:
            details = action()
            row = {'name': name, 'ok': True, 'details': details}
        except Exception as exc:
            row = {'name': name, 'ok': False, 'error': str(exc)}
        row['seconds'] = round(time.monotonic() - t, 2)
        checks.append(row)
        emit(check=row)

    def discover(query):
        rows = sources.catalog(query)
        exact = [row for row in rows if row['title'].casefold() == query.casefold()]
        if len(exact) != 1:
            raise ValueError(f'Ambiguous/missing source: {rows}')
        ids.append(exact[0]['id'])
        return exact[0]

    def download(dataset_id, refresh=False):
        before = dict(state.get('temporary_datasets', {}))
        data = sources.download_dataset(state, dataset_id, refresh=refresh)
        for key, value in before.items():
            if key != dataset_id:
                assert state['temporary_datasets'][key] is value
        return {key: data[key] for key in ['id', 'row_count', 'sha256', 'downloaded_at']}

    def map_all():
        rows = []
        for index, key in enumerate(ids):
            result = csdi_map(state, key, replace_existing=index == 0)
            assert result['ok'], result
            _update_web_layer_stack(state, 'csdi_map', result['data'])
            rows.append((key, len(result['data']['geojson']['features'])))
        payload = _web_map_payload(state)
        assert len(payload['map_layers']) == len(ids)
        colors = [next(iter(layer['analysis']['category_colors'].values())) for layer in payload['map_layers']]
        assert len(set(colors)) == len(ids), colors
        json.dumps(payload, allow_nan=False)
        return {'layers': rows, 'colors': colors, 'serialized_bytes': len(json.dumps(payload))}

    def cache():
        before = len(attempts)
        for _ in range(5):
            for key in ids:
                sources.download_dataset(state, key)
        assert len(attempts) == before
        return {'reads': 5 * len(ids), 'network_attempts': 0}

    def nearby(mode):
        result = csdi_nearby(state, 'Tung Cheong Street Sports Centre', mode=mode)
        assert result['ok'], result
        _update_web_layer_stack(state, 'csdi_nearby', result['data'])
        return {'message': result['message'], 'layers': len(_web_map_payload(state)['map_layers']),
                'summary': result['data'].get('summary'), 'analysis': result['data']['analysis']}

    def isolation():
        other = init_map_state()
        assert not other.get('temporary_datasets')
        before = dict(state['temporary_datasets'])
        with patch.object(sources, '_request', side_effect=sources.requests.Timeout('simulated outage')):
            try:
                sources.download_dataset(state, ids[0], refresh=True)
            except Exception:
                pass
            else:
                raise AssertionError('Failed refresh unexpectedly succeeded')
        assert all(state['temporary_datasets'][key] is value for key, value in before.items())
        return {'other_session_empty': True, 'all_snapshots_preserved': True,
                'outage_is_simulated': True}

    with patch.object(sources, '_request_once', side_effect=request):
        for query in ['Badminton Courts', 'Swimming Pools']:
            check('discover ' + query, lambda q=query: discover(q))
        ids += ['csdi_fitness_rooms', 'csdi_ambulance_depots']
        for key in ids:
            check('download ' + key, lambda k=key: download(k))
        for key in ids:
            check('refresh ' + key, lambda k=key: download(k, True))
        check('cached reads', cache)
        check('four-layer map stack', map_all)
        for mode in ['buffer', 'driving']:
            check(mode, lambda m=mode: nearby(m))
        check('session isolation and failed-refresh preservation', isolation)
        check('restore four-layer map', map_all)
    emit(summary={'seconds': round(time.monotonic() - started, 2),
                  'passed': sum(row['ok'] for row in checks), 'checks': len(checks),
                  'request_attempts': len(attempts), 'failed_attempts': sum(not row['ok'] for row in attempts),
                  'datasets': [(key, value['row_count']) for key, value in state.get('temporary_datasets', {}).items()]})
    return 0 if all(row['ok'] for row in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
