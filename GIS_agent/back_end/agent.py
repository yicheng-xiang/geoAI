import json
import os
import re
import sys
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from dotenv import load_dotenv
from openai import AzureOpenAI

from agent_schemas.tools_definition import MAP_TOOLS
from session_store import SessionStore
from tools import REGISTRY_TOOLS, init_map_state
from tools.tool_results import normalize_tool_result, tool_error

AVAILABLE_TOOLS = {
    'restyle_map': REGISTRY_TOOLS['restyle_map'],
    'network_distance_query': REGISTRY_TOOLS['network_distance_query'],
    **{name: REGISTRY_TOOLS[name] for name in ('csdi_catalog', 'csdi_download', 'csdi_map', 'csdi_nearby')},
    "network_service_area": REGISTRY_TOOLS["network_service_area"],
    "draw_choropleth": REGISTRY_TOOLS["draw_choropleth"],
    "add_points_layer": REGISTRY_TOOLS["add_points_layer"],
    "aggregate_points_to_districts": REGISTRY_TOOLS["aggregate_points_to_districts"],
    "buffer_facility_coverage": REGISTRY_TOOLS["buffer_facility_coverage"],
    "add_title": REGISTRY_TOOLS["add_title"],
    "add_compass": REGISTRY_TOOLS["add_compass"],
    "add_gridlines": REGISTRY_TOOLS["add_gridlines"],
    "add_scale_bar": REGISTRY_TOOLS["add_scale_bar"],
}

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-12-01-preview",
)

SESSION_STORE = SessionStore()


def set_agent_uploaded_dataset(session_id, uploaded_dataset):
    """Replace one session upload and invalidate maps made from older data."""
    session = SESSION_STORE.get_or_create(session_id)
    with session["lock"]:
        previous = session.get('map_state') or {}
        session["map_state"] = init_map_state() if previous.get('results') else None
        if session['map_state'] is not None:
            session['map_state']['results'] = previous['results']
            session['map_state']['active_result_id'] = previous.get('active_result_id')
        session["uploaded_dataset"] = uploaded_dataset
        session["updated_at"] = time.time()


def get_agent_session_state(session_id):
    """Return JSON-safe session metadata without exposing the uploaded DataFrame."""
    session = SESSION_STORE.get_or_create(session_id)
    with session["lock"]:
        uploaded = session.get("uploaded_dataset")
        if not uploaded:
            return {"uploaded_dataset": None}
        return {
            "uploaded_dataset": {
                "dataset_id": uploaded["id"],
                "filename": uploaded["filename"],
                "row_count": int(len(uploaded["dataframe"])),
                "crs": uploaded["crs"],
                "columns": dict(uploaded.get("columns", {})),
                "quality": dict(uploaded.get("quality", {})),
                "sha256": uploaded.get("sha256"),
                "uploaded_at": uploaded.get("uploaded_at"),
            }
        }


def clear_agent_session(session_id):
    """Clear exactly one browser session."""
    cleared = SESSION_STORE.clear(session_id)
    if cleared:
        print(f"[Session] Session [{session_id}] cleared.")
    return cleared


def _system_prompt():
    return (
        "For road/network DISTANCE in metres or km use network_distance_query with explicit walk or drive. "
        "network_distance_query returns actual shortest-route LINE features, matched targets and center, but NO service-area polygon. "
        "To add/fix route traces or legends, rerun this tool with existing origin/mode/distance/categories and replace_existing=true. "
        "Never add an unfiltered add_points_layer to fix a network result legend: it would show out-of-range facilities. "
        "Only claim route_count lines actually returned. Do not claim a service-area polygon. "
        "Never convert distance to driving minutes or claim csdi_nearby driving accepts a metre threshold. "
        "For named places such as PolyU Block Z use location_query; never look them up in fitness-room datasets. "
        "Reuse the place, category and threshold already supplied in prior turns. Ask only for missing travel mode. "
        "When a named place and buffer radius are already supplied, run the official resolver directly; do not ask to confirm PolyU Block Z again. "
        "New analyses replace the map by default unless overlay was explicitly requested. Do not repeatedly ask for replacement confirmation. "
        "If a network is missing, report the tool error; do not substitute another mode, origin, or old map. "
        "CSDI WFS temporary sources are available: csdi_fitness_rooms (LCSD public fitness rooms, NOT all commercial gyms), "
        "csdi_ambulance_depots (FSD ambulance depots). For gym/fitness distribution or explicit official/CSDI data, "
        "use csdi_map: it downloads and caches the dataset without changing local files. Use csdi_catalog for "
        "live official catalogue search with concise English or Chinese facility keywords. For other types such as badminton, "
        "always call csdi_catalog first, then use its exact dataset ID with csdi_map/download/nearby. Never invent URLs or IDs. "
        "Catalogue discovery does not guarantee compatible point WFS; report unsupported sources honestly. "
        "Use csdi_download to keep multiple snapshots, and csdi_nearby for ambulance depots "
        "within a named fitness room's distance buffer or driving time. csdi_nearby downloads both sources automatically. "
        "Incoming driving time (targets TO the selected origin) is not implemented by csdi_nearby; explain that "
        "limitation instead of silently reversing the request. "
        "For driving mode it counts reachable target facilities FROM the selected origin, not polygon containment. "
        "Never substitute a local dataset if CSDI fails. For an ambiguous origin ask the user for one name. "
        "Temporary datasets last until Clear session or backend restart. Do not claim private gym coverage. "
        "For driving-time coverage (e.g. ambulance depots within 5 minutes), call network_service_area, "
        "not the distance buffer tool. Default constant scenario speed is 30 km/h. "
        "Use facility_name only for an explicitly named depot. The result already includes roads, "
        "approximate service polygons and origin markers; do not overwrite these with other mapping tools. "
        "Never claim population coverage or real emergency response time. "
        "You are a professional GIS Copilot. Parse user intent and coordinate "
        "cartographic operators through Thought -> Action -> Observation cycles.\n"
        "Administrative polygons use HKDistrict18.shp. For a categorical district map, "
        "pass NAME to draw_choropleth; for a numeric map use OBJECTID.\n"
        "Facility tools accept dataset_id='all_facilities', dataset_id='session_upload', or an exact downloaded CSDI snapshot ID; "
        "never pass or invent a file path. Use all_facilities by default. Use session_upload only "
        "when the request refers to uploaded data OR follows up an active uploaded-data analysis without changing source. "
        "all_facilities is a separate LOCAL file, NOT an index of downloaded CSDI data. Never claim otherwise. "
        "For a follow-up about downloaded official facilities, retain their exact snapshot IDs, never substitute all_facilities. "
        "When fitness rooms and ambulance depots were prepared and the user names a fitness room as origin, "
        "use csdi_nearby with those two IDs for both buffer and driving-time follow-ups, not buffer_facility_coverage on local data. "
        "For session_upload, use facility_types=[] to include every uploaded "
        "point unless the user explicitly requests a FacilityType filter. "
        "Map Ambulance/Rescue to Ambulance Depot, "
        "Fire Station/Firefighting to Fire Station, Primary School to Primary School, "
        "Secondary School to Secondary School, Country Park to Country Park, and "
        "Higher Education/University to Higher Education Institutions.\n"
        "For per-district totals use aggregate_points_to_districts with metric='count'. "
        "Only when the user explicitly requests density, use metric='density_per_km2'; "
        "this means facilities per square kilometer. Do not describe raw counts as density.\n"
        "For a within-distance request around a coordinate or named Hong Kong location, use "
        "buffer_facility_coverage. Pass location_query when the user gives a place, building, "
        "facility, or address; pass latitude and longitude only when the user provides coordinates. "
        "Buffer distances are metres and the tool performs metric analysis in EPSG:2326. "
        "Never estimate or invent coordinates from a place name. Named locations are resolved only "
        "by the official Lands Department Location Search API.\n"
        "Treat follow-up map edits as tool operations, never as narration-only changes. "
        "For a title-only edit call add_title. To change or switch the current map to points, "
        "call add_points_layer with replace_existing=true. To change facility points into a district "
        "polygon map, always call aggregate_points_to_districts with replace_existing=true; use "
        "draw_choropleth only for an existing district attribute field. "
        "Reuse the current registered dataset, facility filter, metric, and other analysis parameters "
        "unless the user changes them. Use replace_existing=false only when the user explicitly asks "
        "to add or overlay a layer. To recolor current points, polygons, routes or legends, use restyle_map, "
        "never rerun an analysis or add a global point layer for a color-only request. Map features and legend must "
        "use matching colors. Call exactly one tool per iteration. Draw the polygon layer first, "
        "optionally add points, then add title, compass, scale bar, and gridlines. Always call "
        "add_gridlines last. Do not offer CSV, Excel, or report export because those tools are not "
        "implemented. A completed buffer analysis already includes its matched facility points, so "
        "do not claim that another point layer is required. For download-only requests use csdi_download, never csdi_map. "
        "Each tool result's map_state_summary is authoritative: cached datasets are NOT displayed layers. "
        "For requested multiple layers, explicitly call csdi_map for every missing layer, preserving per-call "
        "replace_existing booleans (first true only if replacing, later false). Do not finish until all requested "
        "layers appear in map_state_summary. PNG export is available through the frontend Export preview button. "
        "Do not offer operations that are not in "
        "the registered tool list. Every user-visible final explanation MUST be written in professional "
        "English, even when the user's request is Chinese."
    )


def _compact_tool_result(result):
    """Do not send large GeoJSON payloads back into the model context."""
    return {key: value for key, value in result.items() if key != "data"}


def _verified_csdi_summary(state, prompt):
    """Summarize actual state, never the model's unverified claims."""
    layers = list(state.get('web_layers', {}).values())
    cached = state.get('temporary_datasets', {})
    rendered = {layer['id'] for layer in layers}
    details = ', '.join(f"{layer['id']} ({len(layer['geojson'].get('features', []))} features)" for layer in layers)
    text = f"Current map: {len(layers)} layers. {details or 'No layers displayed.'} Cached datasets: {len(cached)}."
    expected = set(re.findall(r'\bcsdi_[A-Za-z0-9_]+', prompt)) & set(cached)
    map_request = bool(re.search(r'\b(map|layers?|overlay|display|show)\b|地图|图层|叠加', prompt, re.I))
    if map_request and re.search(r'\ball\s+(?:four\s+|4\s+)?(?:cached\s+)?datasets\b|全部数据|四份数据', prompt, re.I):
        expected |= set(cached)
    missing = expected - rendered if map_request else set()
    if missing:
        text += ' Requested layers not displayed: ' + ', '.join(sorted(missing)) + '.'
    return text, sorted(missing)


POINT_DATASET_TOOLS = {
    'network_distance_query',
    "network_service_area",
    "add_points_layer", "aggregate_points_to_districts", "buffer_facility_coverage",
}
SESSION_UPLOAD_REFERENCE = re.compile(
    r"\b(upload(?:ed)?|excel|workbook|my\s+(?:file|data|dataset)|session\s+dataset)\b|上传|我的数据|文件|表格",
    re.IGNORECASE,
)
CURRENT_MAP_MODIFICATION = re.compile(
    r"\b(?:change|switch|convert|replace|recolor|restyle|rename|make\s+(?:it|the\s+map)|"
    r"turn\s+(?:it|the\s+map))\b|修改|更改|改成|切换|替换|换色|配色|颜色|重命名",
    re.IGNORECASE,
)
GEOMETRY_SWITCH_REFERENCE = re.compile(
    r"(?:\b(?:change|switch|convert|replace|turn)\b.{0,48}\b(?:point|polygon|choropleth)\b|"
    r"\b(?:point|polygon|choropleth)\s+map\b|(?:改成|切换|替换|转换).{0,24}(?:点图|点地图|面图|多边形图))",
    re.IGNORECASE,
)
LAYER_OVERLAY_REFERENCE = re.compile(
    r"\b(?:add|overlay|superimpose)\b|叠加|添加图层|加上",
    re.IGNORECASE,
)
COLOR_STYLE_REFERENCE = re.compile(
    r"\b(?:recolor|colou?rs?|palette|colou?rmap)\b|(?:legend|map).{0,20}\bcolou?rs?\b|换色|配色|颜色|色带|图例色",
    re.IGNORECASE,
)
MAP_LAYER_TOOLS = {
    'network_distance_query',
    'csdi_map', 'csdi_nearby',
    "network_service_area",
    "draw_choropleth", "add_points_layer", "aggregate_points_to_districts",
    "buffer_facility_coverage",
}
BUILTIN_DATASET_REFERENCE = re.compile(
    r"\b(?:built[ -]?in|local\s+database|default\s+(?:data|dataset|catalog)|all_facilities)\b|本地数据库|内置数据",
    re.IGNORECASE,
)


def _normalize_dataset_arguments(tool_name, arguments, current_prompt, map_state=None):
    """Make dataset selection depend on the latest request, not stale chat history."""
    normalized = dict(arguments)
    if tool_name not in POINT_DATASET_TOOLS:
        return normalized
    prompt_text = str(current_prompt)
    current_analysis = (map_state or {}).get("last_analysis", {}).get("analysis", {})
    if (
        CURRENT_MAP_MODIFICATION.search(prompt_text)
        and current_analysis.get("dataset_id") == "session_upload"
        and not BUILTIN_DATASET_REFERENCE.search(prompt_text)
    ):
        normalized["dataset_id"] = "session_upload"
        return normalized
    if normalized.get("dataset_id", "all_facilities") != "session_upload":
        return normalized
    if SESSION_UPLOAD_REFERENCE.search(prompt_text) or (
        current_analysis.get('dataset_id') == 'session_upload'
        and not BUILTIN_DATASET_REFERENCE.search(prompt_text)
    ):
        return normalized

    normalized["dataset_id"] = "all_facilities"
    return normalized


def _normalize_map_arguments(tool_name, arguments, current_prompt, map_state=None):
    """Preserve the active registered source and enforce explicit geometry replacement."""
    normalized = _normalize_dataset_arguments(
        tool_name,
        arguments,
        current_prompt,
        map_state=map_state,
    )
    prompt_text = str(current_prompt)
    if tool_name in POINT_DATASET_TOOLS and not (map_state or {}).get('_replacement_applied') and re.search(
        r'replace|new map|取代|替换|替換|新地图|新地圖', prompt_text, re.I):
        if tool_name != 'csdi_nearby':
            normalized['replace_existing'] = True
        return normalized
    if tool_name == 'network_distance_query' and re.search(r'路线|路線|轨迹|軌跡|图例|圖例|route|trace|legend', prompt_text, re.I):
        # Rebuild the scoped bundle together; never keep a stale global points
        # layer introduced by a previous unsuccessful legend/route workaround.
        normalized['replace_existing'] = True
        return normalized
    if tool_name in MAP_LAYER_TOOLS and isinstance(normalized.get('replace_existing'), bool):
        return normalized
    if tool_name == "buffer_facility_coverage" and not LAYER_OVERLAY_REFERENCE.search(prompt_text):
        normalized["replace_existing"] = True
    if (
        tool_name in MAP_LAYER_TOOLS
        and GEOMETRY_SWITCH_REFERENCE.search(prompt_text)
        and not LAYER_OVERLAY_REFERENCE.search(prompt_text)
    ):
        normalized["replace_existing"] = True
    return normalized


def _update_web_layer_stack(map_state, tool_name, result_data):
    from result_catalog import capture_result
    before = {id(layer) for layer in map_state.get('web_layers', {}).values()}
    _update_web_layer_stack_core(map_state, tool_name, result_data)
    changed = [layer for layer in map_state.get('web_layers', {}).values() if id(layer) not in before]
    if changed:
        map_state['_replacement_applied'] = True
    prompt = str(map_state.get('user_prompt', ''))
    style_only = bool(CURRENT_MAP_MODIFICATION.search(prompt) and COLOR_STYLE_REFERENCE.search(prompt)
                      and not GEOMETRY_SWITCH_REFERENCE.search(prompt))
    # Rendering the just-computed aggregation is presentation, not another analysis.
    if tool_name == 'draw_choropleth' and map_state.get('active_result_id'):
        active = map_state.get('results', {}).get(map_state['active_result_id'], {})
        style_only = style_only or active.get('analysis', {}).get('method') == 'point_in_polygon'
    capture_result(map_state, result_data, changed, style_only)


def _update_web_layer_stack_core(map_state, tool_name, result_data):
    """Mirror data-producing GIS tools into replaceable browser map layers."""
    if not isinstance(result_data, dict) or not result_data.get("geojson"):
        return

    prompt_text = str(map_state.get("user_prompt", ""))
    style_only_update = bool(
        CURRENT_MAP_MODIFICATION.search(prompt_text)
        and COLOR_STYLE_REFERENCE.search(prompt_text)
        and not GEOMETRY_SWITCH_REFERENCE.search(prompt_text)
    )
    # A new analysis gets a fresh inferred title, while a color-only rerender
    # preserves an explicit title set in a previous request.
    if not style_only_update:
        map_state.setdefault("web_map", {})["title"] = None

    visualization_layers = result_data.get("visualization_layers")
    if isinstance(visualization_layers, list) and visualization_layers:
        web_layers = map_state.setdefault("web_layers", {})
        if result_data.get("analysis", {}).get("replace_existing", True):
            web_layers.clear()
        for layer in visualization_layers:
            if not isinstance(layer, dict) or not layer.get("id") or not layer.get("geojson"):
                continue
            web_layers[layer["id"]] = {
                "id": layer["id"],
                "kind": layer.get("kind", "polygon"),
                "geojson": layer["geojson"],
                "analysis": layer.get("analysis", result_data.get("analysis", {})),
                "statistics": result_data.get("statistics", []),
                "quality": result_data.get("quality", {}),
            }
        return

    layer_id = {
        "draw_choropleth": "thematic_polygon",
        "aggregate_points_to_districts": "thematic_polygon",
        "add_points_layer": "facility_points",
        "buffer_facility_coverage": "buffer_area",
    }.get(tool_name, tool_name)
    geometry_types = {
        feature.get("geometry", {}).get("type")
        for feature in result_data["geojson"].get("features", [])
        if isinstance(feature, dict)
    }
    layer_kind = "point" if geometry_types and geometry_types <= {"Point", "MultiPoint"} else "polygon"
    web_layers = map_state.setdefault("web_layers", {})
    if result_data.get("analysis", {}).get("replace_existing"):
        web_layers.clear()
    web_layers[layer_id] = {
        "id": layer_id,
        "kind": layer_kind,
        "geojson": result_data["geojson"],
        "analysis": result_data.get("analysis", {}),
        "statistics": result_data.get("statistics", []),
        "quality": result_data.get("quality", {}),
    }


def _web_map_payload(map_state):
    """Return an ordered, JSON-safe snapshot for the React-Leaflet client."""
    layers = list(map_state.get("web_layers", {}).values())
    layers.sort(key=lambda layer: 1 if layer.get("kind") == "point" else 0)
    return {
        **__import__('result_catalog').result_payload(map_state),
        "map_layers": layers,
        "map_presentation": dict(map_state.get("web_map", {})),
    }


def _close_hanging_tool_calls(messages):
    if not messages:
        return
    last_msg = messages[-1]
    last_role = last_msg.get("role") if isinstance(last_msg, dict) else getattr(last_msg, "role", None)
    if last_role != "assistant":
        return
    last_calls = last_msg.get("tool_calls") if isinstance(last_msg, dict) else getattr(last_msg, "tool_calls", None)
    for hanging_call in last_calls or []:
        call_id = hanging_call.get("id") if isinstance(hanging_call, dict) else hanging_call.id
        call_name = (
            hanging_call.get("function", {}).get("name")
            if isinstance(hanging_call, dict)
            else hanging_call.function.name
        )
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": call_name,
            "content": json.dumps(
                tool_error("INTERRUPTED_TOOL_CALL", "Tool call was closed after an interrupted stream."),
                ensure_ascii=False,
            ),
        })


def _model_failure_event(session_id, map_state, structured_result=None):
    """Return a safe terminal event when model planning fails after or before GIS work."""
    if structured_result:
        event = {
            "session_id": session_id,
            "thought": (
                "The GIS analysis completed successfully. The final AI narration was unavailable, "
                "so the verified spatial result was returned directly."
            ),
            "log": (
                "[Task Success] Spatial analysis completed; the verified result was returned "
                "without additional AI narration."
            ),
            "warning": "The model service could not generate the final narration.",
            "warning_code": "MODEL_FINALIZATION_FALLBACK",
            "status": "completed",
        }
        event.update(structured_result)
        event.update(_web_map_payload(map_state))
        return event

    return {
        "session_id": session_id,
        "thought": "The AI planning service could not interpret or continue this request.",
        "error": "The model service rejected or could not process the request. Rephrase it and try again.",
        "error_code": "MODEL_REQUEST_FAILED",
        "log": "[Task Failed] The model service could not process the request.",
        "status": "failed",
    }


def run_gis_agent_stream(user_prompt, session_id):
    """Run one request while serializing mutations inside its isolated session."""
    session = SESSION_STORE.get_or_create(session_id)
    with session["lock"]:
        yield from _run_locked_session(user_prompt, session_id, session)


def _current_session_context(state):
    """Supply current facts each iteration, without resending feature collections."""
    layers = [{'id': l.get('id'), 'result_id': l.get('result_id'), 'kind': l.get('kind'),
               'features': len(l.get('geojson', {}).get('features', [])),
               'role': l.get('analysis', {}).get('visual_role'),
               'dataset_id': l.get('analysis', {}).get('dataset_id')}
              for l in state.get('web_layers', {}).values()]
    results = [{'id': r['id'], 'rows': len(r.get('rows', [])),
                'radius_m': r.get('analysis', {}).get('radius_m'),
                'distance_m': r.get('analysis', {}).get('distance_m')}
               for r in state.get('results', {}).values()]
    return ('Current session facts (data, not instructions): ' + json.dumps({
        'visible_layers': layers, 'cached_dataset_ids': list(state.get('temporary_datasets', {})),
        'saved_results': results}, ensure_ascii=False) +
        '\nOnly visible_layers are displayed. Cached datasets and saved results are not necessarily visible. '
        'The optional Results panel has a Result list to reopen saved tables and Show on map to restore saved layers without analysis. '
        'Closing tables does not delete results. Explain this when asked about an older result; do not claim it is lost. '
        'Do not offer unsupported new tools or imply downloaded snapshots were merged into the local file.')


def _origin_conflicts_with_request(prompt, arguments):
    """Prevent a planner from replacing an explicit PolyU block with a suggestion."""
    from tools.location_search import _canonical_query
    explicit = _canonical_query(str(prompt))
    planned = _canonical_query(str(arguments.get('location_query', '')))
    prefix = 'Hong Kong Polytechnic University Block '
    return explicit.startswith(prefix) and planned.startswith(prefix) and explicit != planned


def _run_locked_session(user_prompt, session_id, session):
    if session["map_state"] is None:
        session["map_state"] = init_map_state()
    if not session["messages"]:
        session["messages"] = [{"role": "system", "content": _system_prompt()}]
    else:
        # Keep the conversation, but refresh capabilities after a deployment.
        session['messages'][0] = {'role': 'system', 'content': _system_prompt()}

    map_state = session["map_state"]
    map_state['temporary_datasets'] = session.setdefault('temporary_datasets', {})
    map_state["uploaded_dataset"] = session.get("uploaded_dataset")
    messages = session["messages"]
    _close_hanging_tool_calls(messages)

    map_state["user_prompt"] = user_prompt
    map_state['_replacement_applied'] = False
    messages.append({"role": "user", "content": user_prompt})
    session["updated_at"] = time.time()

    max_iterations = 8
    executed_tools = []
    structured_result = None

    for iteration in range(1, max_iterations + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[messages[0], {'role': 'system', 'content': _current_session_context(map_state)}, *messages[1:]],
                tools=MAP_TOOLS,
                tool_choice="auto",
            )
        except Exception as exc:
            print(f"[Model Request Error] {type(exc).__name__}: {exc}")
            terminal_event = _model_failure_event(
                session_id,
                map_state,
                structured_result=structured_result,
            )
            messages.append({
                "role": "assistant",
                "content": (
                    "The verified GIS result was returned without additional narration."
                    if structured_result
                    else "The model service could not process this request."
                ),
            })
            yield terminal_event
            return
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        messages.append(response_message)

        if not tool_calls:
            if executed_tools and "add_gridlines" not in executed_tools:
                try:
                    grid_result = normalize_tool_result(AVAILABLE_TOOLS["add_gridlines"](map_state))
                except Exception as exc:
                    grid_result = tool_error("GRIDLINE_FINALIZER_ERROR", str(exc))
                if not grid_result["ok"]:
                    yield {
                        "session_id": session_id,
                        "error": grid_result["message"],
                        "error_code": grid_result["code"],
                        "log": f"[Task Failed] {grid_result['message']}",
                        "status": "failed",
                    }
                    return

            narration = response_message.content or 'The map is ready.'
            missing = []
            if any(name.startswith('csdi_') for name in executed_tools) or any(
                key.startswith('csdi_') for key in map_state.get('web_layers', {})
            ):
                narration, missing = _verified_csdi_summary(map_state, user_prompt)
                if structured_result and executed_tools and executed_tools[-1] == 'csdi_nearby':
                    narration, _ = _verified_csdi_summary(map_state, '')
                    missing = []
                    narration = last_tool_message + ' ' + narration
                messages[-1] = {'role': 'assistant', 'content': narration}
            if executed_tools and all(name in ('csdi_catalog', 'csdi_download') for name in executed_tools):
                narration = 'Catalogue search/download finished, but no new spatial analysis or map was generated. The previous map is unchanged. ' + narration
            if not executed_tools and map_state.get('temporary_datasets') and re.search(
                r'数据库|資料庫|数据源|資料源|下载|下載|缓存|緩存|database|dataset|source|cache|download', user_prompt, re.I):
                snapshots = map_state['temporary_datasets']
                narration = ('The official datasets are separate session snapshots; they are not merged into the local database. '
                    'Cached dataset IDs: ' + ', '.join(snapshots) + '. ' + _verified_csdi_summary(map_state, '')[0] +
                    ' Only the listed current map layers are visible; cached datasets are not necessarily displayed. No download or analysis was run for this answer.')
                messages[-1] = {'role': 'assistant', 'content': narration}
            if 'network_distance_query' in executed_tools and structured_result:
                actual = structured_result.get('analysis', {})
                narration = (f"{actual.get('matched_count', 0)} matched facilities; {actual.get('route_count', 0)} shortest-route features "
                             f"within {actual.get('distance_m')} m {actual.get('travel_mode')} network distance of {actual.get('location_name')}. "
                             "Only matched facilities and routes are shown. Access connectors are included; no service-area polygon is generated.")
                messages[-1] = {'role': 'assistant', 'content': narration}
            final_event = {
                "session_id": session_id,
                "thought": "Requested layers are missing." if missing else "Task finished; verified map state returned.",
                "log": f"[Task {'Failed' if missing else 'Success'}] {narration}",
                "status": "failed" if missing else "completed",
            }
            if missing:
                final_event.update(error_code='INCOMPLETE_MAP_LAYERS', error=narration)
            if structured_result:
                final_event.update(structured_result)
            final_event.update(_web_map_payload(map_state))
            yield final_event
            return

        primary_call = tool_calls[0]
        func_name = primary_call.function.name
        raw_arguments = primary_call.function.arguments.replace("\n", " ").replace("\r", "")
        print(f"[ReAct Agent Loop {iteration}] Deploying function: {func_name}")

        try:
            func_args = json.loads(raw_arguments)
            func_args = _normalize_map_arguments(func_name, func_args, user_prompt, map_state)
            if "dataset_id" in func_args:
                print(f"[Dataset Selection] {func_name} -> {func_args['dataset_id']}")
            if func_name not in AVAILABLE_TOOLS:
                result = tool_error("UNKNOWN_TOOL", f"Tool [{func_name}] is not registered.")
            elif _origin_conflicts_with_request(user_prompt, func_args):
                result = tool_error('ORIGIN_MISMATCH', 'The proposed origin differs from the explicitly requested university block. No analysis was run; the previous map is unchanged.')
            elif (func_name == 'add_points_layer'
                  and map_state.get('last_analysis', {}).get('analysis', {}).get('method') == 'network_distance'
                  and (re.search(r'路线|路線|轨迹|軌跡|图例|圖例|范围|範圍|可达|可達|route|trace|legend|within|reachable', user_prompt, re.I)
                       or 'network_distance_query' in executed_tools)
                  and not re.search(r'全港|all Hong Kong|all schools in Hong Kong', user_prompt, re.I)):
                result = tool_error('NETWORK_SCOPE_PROTECTED', 'Unfiltered facility points were not added. Use network_distance_query to update routes, matched facilities and legends together. The scoped map is retained.')
            else:
                result = normalize_tool_result(AVAILABLE_TOOLS[func_name](map_state, **func_args))
        except json.JSONDecodeError as exc:
            result = tool_error("INVALID_TOOL_ARGUMENTS", str(exc))
        except Exception as exc:
            result = tool_error("TOOL_RUNTIME_ERROR", str(exc))

        if result['ok'] and result.get('data'):
            structured_result = result['data']
            _update_web_layer_stack(map_state, func_name, result['data'])
        if func_name.startswith('csdi_'):
            result['map_state_summary'], _ = _verified_csdi_summary(map_state, '')
        last_tool_message = result['message']
        messages.append({
            "role": "tool",
            "tool_call_id": primary_call.id,
            "name": func_name,
            "content": json.dumps(_compact_tool_result(result), ensure_ascii=False),
        })

        for extra_call in tool_calls[1:]:
            messages.append({
                "role": "tool",
                "tool_call_id": extra_call.id,
                "name": extra_call.function.name,
                "content": json.dumps(
                    tool_error("DEFERRED_TOOL_CALL", "Only one tool is executed per iteration."),
                    ensure_ascii=False,
                ),
            })

        if not result["ok"]:
            failed_event = {
                "session_id": session_id,
                "thought": f"Tool [{func_name}] failed; the task was stopped to avoid a false success.",
                "error": result["message"],
                "error_code": result["code"],
                "log": f"[Task Failed] [{result['code']}] {result['message']}",
                "status": "failed",
            }
            if result.get("data"):
                failed_event["details"] = result["data"]
            yield failed_event
            return

        executed_tools.append(func_name)
        yield {
            "session_id": session_id,
            "thought": f"[Iteration {iteration}] Applied [{func_name}].",
            "log": f"[Tool Success] {result['message']}",
            "tool_result": _compact_tool_result(result),
            "status": "processing",
        }

    yield {
        "session_id": session_id,
        "thought": "Maximum execution threshold reached before the plan completed.",
        "error": "The GIS agent reached the maximum of 8 tool iterations.",
        "error_code": "MAX_ITERATIONS_REACHED",
        "log": "[Task Failed] Maximum execution threshold reached.",
        "status": "failed",
    }
