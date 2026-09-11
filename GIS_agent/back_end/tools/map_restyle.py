"""Presentation-only edits: never requery, replace geometry, or create results."""
from copy import deepcopy

from color_palettes import PALETTES, literal_color, sample_palette
from tool_results import tool_error, tool_success


def restyle_map(state, color=None, cmap=None, category_colors=None):
    mapping = category_colors or {}
    if not isinstance(mapping, dict) or any(not literal_color(v) for v in mapping.values()):
        return tool_error('INVALID_COLOR', 'Use named colors or hexadecimal colors.')
    if color is not None and not literal_color(color):
        return tool_error('INVALID_COLOR', 'Use a named color or hexadecimal color.')
    if cmap is not None and str(cmap).lower() not in {k.lower() for k in PALETTES}:
        return tool_error('INVALID_PALETTE', 'Choose a registered color palette.')
    if not color and not cmap and not mapping:
        return tool_error('MISSING_STYLE', 'Specify color, cmap, or category_colors.')
    layers = list(state.get('web_layers', {}).values())
    eligible = [l for l in layers if l.get('analysis', {}).get('visual_role') not in
                ('buffer_center', 'buffer_area', 'coverage_area', 'analysis_center')
                and (l.get('kind') != 'line' or l.get('analysis', {}).get('visual_role') == 'shortest_routes')]
    if not eligible:
        return tool_error('NO_MAP_LAYERS', 'No business layers are displayed to restyle.')
    # Validate first and commit together, including saved snapshots used for restore.
    changes = {}
    for layer in eligible:
        analysis = deepcopy(layer.get('analysis', {}))
        categories = list(analysis.get('category_colors', {}))
        if mapping and not any(c in mapping for c in categories):
            continue
        if categories:
            colors = ([literal_color(color)] * len(categories) if color else
                      sample_palette(cmap, len(categories)) if cmap else
                      [analysis['category_colors'][c] for c in categories])
            analysis['category_colors'] = {c: literal_color(mapping[c]) if c in mapping else v
                                           for c, v in zip(categories, colors)}
        elif mapping:
            continue
        else:
            n = max(1, len(analysis.get('classification_breaks', [])) or len(analysis.get('palette', [])))
            analysis['palette'] = [literal_color(color)] * n if color else sample_palette(cmap, n)
        if cmap:
            analysis['colormap'] = cmap
        changes[id(layer)] = analysis
    if not changes:
        return tool_error('NO_MATCHING_CATEGORY', 'No displayed category matches the requested style.')
    for layer in eligible:
        if id(layer) not in changes:
            continue
        layer['analysis'] = changes[id(layer)]
        for result in state.get('results', {}).values():
            for saved in result.get('layers', []):
                if saved.get('instance_id') and saved['instance_id'] == layer.get('instance_id'):
                    saved['analysis'] = deepcopy(layer['analysis'])
        for saved in state.get('last_analysis', {}).get('visualization_layers', []):
            if saved.get('id') == layer.get('id'):
                saved['analysis'] = deepcopy(layer['analysis'])
    return tool_success(f'Updated colors on {len(changes)} displayed layer(s); analysis, title and result identities unchanged.',
                        code='MAP_RESTYLED', data={'styled_layers': len(changes)})
