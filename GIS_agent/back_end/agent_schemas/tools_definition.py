# 请用以下代码完整覆盖 D:\geoAI\GIS_agent\back_end\agent_schemas\tools_definition.py
MAP_TOOLS = [
    {'type': 'function', 'function': {'name': 'csdi_catalog',
        'description': 'Search the live official CSDI catalogue by English or Chinese facility keywords. Returns dataset IDs; WFS point compatibility is checked when downloading. Search before selecting unfamiliar sources.',
        'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}}}},
    {'type': 'function', 'function': {'name': 'csdi_download',
        'description': 'Download one registered official WFS dataset into the current session. Keeps previously downloaded datasets.',
        'parameters': {'type': 'object', 'properties': {
            'dataset_id': {'type': 'string', 'description': 'Exact ID returned by csdi_catalog; never invent IDs or URLs.'},
            'refresh': {'type': 'boolean'}}, 'required': ['dataset_id']}}},
    {'type': 'function', 'function': {'name': 'csdi_map',
        'description': 'Download if needed and display the registered CSDI point dataset. No change to the local database.',
        'parameters': {'type': 'object', 'properties': {
            'dataset_id': {'type': 'string', 'description': 'Exact ID returned by csdi_catalog.'},
            'color': {'type': 'string', 'description': 'Optional CSS hex color, e.g. #2563eb. Omit to keep a stable distinct color for this dataset.'},
            'replace_existing': {'type': 'boolean'}}, 'required': ['dataset_id']}}},
    {'type': 'function', 'function': {'name': 'csdi_nearby',
        'description': 'Count and map targets near a uniquely named origin from another CSDI dataset. Downloads both. Driving is FROM origin to targets, with directed roads and endpoint access costs; not emergency response time.',
        'parameters': {'type': 'object', 'properties': {
            'origin_name': {'type': 'string'},
            'origin_dataset_id': {'type': 'string', 'description': 'Exact catalogue dataset ID.'},
            'target_dataset_id': {'type': 'string', 'description': 'Exact catalogue dataset ID.'},
            'mode': {'type': 'string', 'enum': ['buffer', 'driving']},
            'radius_m': {'type': 'number'}, 'time_minutes': {'type': 'number'}, 'speed_kmh': {'type': 'number'}},
            'required': ['origin_name', 'mode']}}},
    {
        "type": "function",
        "function": {
            "name": "network_service_area",
            "description": "Estimated outbound driving-time coverage from registered facilities using cached Hong Kong directed roads. Returns reachable roads, approximate service polygons and origin quality. Not population coverage or actual emergency response time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_minutes": {"type": "number", "exclusiveMinimum": 0, "maximum": 30},
                    "speed_kmh": {"type": "number", "minimum": 1, "maximum": 100, "description": "Constant scenario speed, default 30 km/h; not live traffic."},
                    "dataset_id": {"type": "string", "enum": ["all_facilities", "session_upload"]},
                    "facility_types": {"type": "array", "items": {"type": "string"}},
                    "facility_name": {"type": "string", "description": "Optional explicit facility name substring, e.g. Aberdeen. Omit to use all matching facilities."},
                    "replace_existing": {"type": "boolean"}
                },
                "required": ["time_minutes", "dataset_id", "facility_types"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draw_choropleth",
            "description": "根据属性表中的数值字段或文本分类字段，生成可追溯的 GeoJSON、统计结果及 WebGIS 分级设色元数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {
                        "type": "string",
                        "description": "属性表中的字段名称。如果用户要求按名称、区名显示分类图例，可传入 '名称'；若绘制数值人口图且表中缺乏POP字段，可默认传入 'OBJECTID'。"
                    },
                    "cmap": {
                        "type": "string",
                        "description": "配色调色盘名称。数值分级推荐 'Purples', 'Blues', 'Reds'，定性类别图强烈推荐离散多色调 'tab20'。"
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Set true when the user asks to change, switch, convert, or replace the current map with a polygon map. Set false for an explicit overlay."
                    }
                },
                "required": ["column"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_points_layer",
            "description": "读取注册点数据集，按设施类别筛选并生成 GeoJSON、质量报告及 WebGIS 点符号元数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "enum": ["all_facilities", "session_upload"],
                        "description": "Allowed facility dataset ID. Use all_facilities for the built-in catalog or session_upload for the current browser's uploaded Excel file."
                    },
                    "facility_types": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Facility category filters. Use [] to include every row of session_upload; the built-in all_facilities dataset requires at least one category."
                    },
                    "cmap": {
                        "type": "string",
                        "description": "散点分类间区隔的色带名称，默认推荐使用高对比度离散色带 'Set1' 或 'tab10'。"
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Set true when the user asks to change, switch, convert, or replace the current map with a point map. Set false only when the user explicitly asks to add or overlay points."
                    }
                },
                "required": ["dataset_id", "facility_types"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_points_to_districts",
            "description": "Spatially join registered facility points to districts and return GeoJSON and style metadata for either raw facility count or facilities per square kilometer. Use metric='count' for totals and metric='density_per_km2' only when explicitly requested.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "enum": ["all_facilities", "session_upload"],
                        "description": "Use all_facilities for the built-in catalog or session_upload for the current browser's uploaded Excel file. No paths are accepted."
                    },
                    "facility_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Facility category filters (case-insensitive substring match). Use [] to aggregate all rows from session_upload; all_facilities requires at least one category."
                    },
                    "cmap": {
                        "type": "string",
                        "description": "Sequential colormap for quantitative choropleth. Recommended: 'YlOrRd', 'Blues', 'Greens', 'Purples', 'Reds'."
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of classification intervals for the choropleth legend. Default: 5."
                    },
                    "metric": {
                        "type": "string",
                        "enum": ["count", "density_per_km2"],
                        "description": "count returns raw facility totals; density_per_km2 returns facilities per square kilometer using EPSG:2326 area calculations."
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Set true when the user asks to change, switch, convert, or replace the current map with this district polygon map. Set false for an explicit overlay."
                    }
                },
                "required": ["dataset_id", "facility_types", "metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buffer_facility_coverage",
            "description": "Resolve a Hong Kong place/building/address through the official Lands Department Location Search API, or use supplied WGS84 coordinates; then create a metric buffer, count matching registered facilities, and return traceable WebGIS results. Prefer location_query when the user gives a place name and never invent coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "minimum": -90,
                        "maximum": 90,
                        "description": "WGS84 latitude of the user-specified analysis center."
                    },
                    "longitude": {
                        "type": "number",
                        "minimum": -180,
                        "maximum": 180,
                        "description": "WGS84 longitude of the user-specified analysis center."
                    },
                    "location_query": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "Hong Kong place name, building name, facility name, or address to resolve with the official Lands Department API. Use this instead of latitude/longitude when the user gives a named location."
                    },
                    "radius_m": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "maximum": 50000,
                        "description": "Buffer radius in metres. Use 500 when the user says within 500 metres."
                    },
                    "dataset_id": {
                        "type": "string",
                        "enum": ["all_facilities", "session_upload"],
                        "description": "Registered point dataset; arbitrary file paths are not accepted."
                    },
                    "facility_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Facility categories to count. Use [] only for all records in session_upload."
                    },
                    "location_name": {
                        "type": "string",
                        "description": "Optional display label supplied by the user for the center coordinate."
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Replace the current analytical map. Defaults to true."
                    }
                },
                "required": ["radius_m", "dataset_id", "facility_types"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_title",
            "description": "设置交互地图和 PNG 导出的自定义主标题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "标题的文字字符串具体内容，例如 '香港行政区划与设施点分布图'。"
                    },
                    "fontsize": {
                        "type": "integer",
                        "description": "标题的字体大小级别，默认传入 16 即可。"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_compass",
            "description": "启用交互地图和 PNG 导出右上角的 SVG 指北针。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "指北针轴向相对坐标X，取值0到1，默认0.92。"},
                    "y": {"type": "number", "description": "指北针轴向相对坐标Y，取值0到1，默认0.88。"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_scale_bar",
            "description": "Set the responsive scale bar for the interactive map and PNG export. Default: 10 km.",
            "parameters": {
                "type": "object",
                "properties": {
                    "length_km": {
                        "type": "number",
                        "description": "Ground distance represented by the scale bar in kilometers. Default: 10 (recommended for Hong Kong full-region maps)."
                    },
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Relative placement on the axes as [x, y] fractions from 0 to 1. Default: [0.05, 0.05] (lower-left)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_gridlines",
            "description": "启用随视口动态更新的四角经纬度标注；完整贯穿网格保持隐藏。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]
