"""Session-owned immutable analysis snapshots and explicit table/feature identities."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json


def uid():
    return uuid4().hex


def business_layer(layer, analysis):
    role = layer.get('analysis', {}).get('visual_role')
    if analysis.get('method') in ('buffer_coverage', 'network_distance'):
        return role == 'matched_facilities'
    if analysis.get('method') == 'network_service_area':
        return layer['id'] == ('network_targets' if 'target_category' in analysis else 'network_origins')
    return layer.get('kind') != 'line'


def values(feature):
    props = {k: v for k, v in feature.get('properties', {}).items() if not k.startswith('_result')}
    geometry = feature.get('geometry') or {}
    if geometry.get('type') == 'Point':
        props['longitude'], props['latitude'] = geometry['coordinates'][:2]
    raw = props.pop('source_properties', None)
    if raw:
        try:
            for key, value in json.loads(raw).items():
                if value is None or isinstance(value, (str, int, float, bool)):
                    props.setdefault('source.' + key, value)
        except (ValueError, TypeError, AttributeError):
            pass
    return props


def capture_result(state, data, changed, style_only=False):
    if not changed:
        return
    archive = state.setdefault('results', {})
    previous = archive.get(state.get('active_result_id')) if style_only else None
    # Only reuse identity for a styling operation with exactly the same geometry.
    def geometries(layers):
        return [[f.get('geometry') for f in l['geojson'].get('features', [])] for l in layers]
    if previous and geometries(previous['layers']) == geometries(changed):
        for old, new in zip(previous['layers'], changed):
            new.update(result_id=previous['id'], instance_id=old['instance_id'])
            for a, b in zip(old['geojson']['features'], new['geojson']['features']):
                b.setdefault('properties', {}).update({k: v for k, v in a['properties'].items() if k.startswith('_result')})
        previous['layers'] = deepcopy(changed)
        previous['analysis'].update(deepcopy(data.get('analysis', {})))
        return
    rid = uid()
    analysis = deepcopy(data.get('analysis', {}))
    rows = []
    targets = {str(r.get('source_feature_id')): r for r in data.get('statistics', [])
               if r.get('source_feature_id') is not None}
    target_rows = 'target_category' in analysis
    linked_targets = set()
    for layer in changed:
        layer.update(result_id=rid, instance_id=uid())
        business = business_layer(layer, analysis)
        for feature in layer['geojson'].get('features', []):
            props = feature.setdefault('properties', {})
            fid = uid()
            props.update(_result_id=rid, _result_feature_id=fid)
            if not business:
                continue
            row_id = uid()
            props['_result_row_id'] = row_id
            row_values = values(feature)
            if target_rows:
                source_id = str(props.get('source_feature_id'))
                row_values.update(targets.get(source_id, {}))
                linked_targets.add(source_id)
            rows.append({'id': row_id, 'feature_id': fid, 'layer_id': layer['instance_id'], 'values': row_values})
    if target_rows:
        for stat in data.get('statistics', []):
            if str(stat.get('source_feature_id')) not in linked_targets:
                rows.append({'id': uid(), 'feature_id': None, 'layer_id': None, 'values': deepcopy(stat)})
    # Preserve statistics that have no geometries rather than linking them by name.
    if not rows and analysis.get('method') not in ('buffer_coverage', 'facility_filter'):
        rows = [{'id': uid(), 'feature_id': None, 'layer_id': None, 'values': deepcopy(s)}
                for s in data.get('statistics', [])]
    types = analysis.get('facility_types') or []
    subject = analysis.get('target_category') or ', '.join(types) or analysis.get('dataset_id') or 'Districts'
    suffix = (f"{analysis['travel_mode']} {analysis['distance_m']:g} m" if analysis.get('method') == 'network_distance' else
              f"{analysis['radius_m']:g} m" if 'radius_m' in analysis else
              f"{analysis['time_minutes']:g} min" if 'time_minutes' in analysis else
              analysis.get('metric') or analysis.get('method', 'Map'))
    sources = deepcopy(analysis.get('sources', []))
    if not sources:
        sources = [{'id': analysis.get('dataset_id'), 'filename': analysis.get('source_filename'),
                    'sha256': analysis.get('source_sha256')}]
        uploaded = state.get('uploaded_dataset') or {}
        if analysis.get('dataset_id') == 'session_upload':
            sources[0]['uploaded_at'] = uploaded.get('uploaded_at')
    archive[rid] = {'id': rid, 'title': f'{subject} · {suffix}', 'analysis': analysis,
                    'created_at': datetime.now(timezone.utc).isoformat(), 'sources': sources,
                    'rows': rows, 'layers': deepcopy(changed)}
    state['active_result_id'] = rid


def result_payload(state):
    active = state.get('results', {}).get(state.get('active_result_id'))
    title = state.get('web_map', {}).get('title')
    if active and title:
        active['title'] = str(title)
    return {'results': list(state.get('results', {}).values()), 'active_result_id': state.get('active_result_id')}


def restore_result(state, rid):
    result = state.get('results', {}).get(rid)
    if result is None:
        raise KeyError('Result not found in this session.')
    layers = state.setdefault('web_layers', {})
    visible = {l.get('instance_id') for l in layers.values()}
    for layer in result['layers']:
        if layer['instance_id'] not in visible:
            layers[layer['instance_id']] = deepcopy(layer)
