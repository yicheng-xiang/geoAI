# 请用以下代码完整覆盖 D:\geoAI\GIS_agent\back_end\agent_schemas\tools_definition.py
MAP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "draw_choropleth",
            "description": "根据属性表中的某个数值字段或文本分类字段，在画布上绘制空间分级色彩图或唯一值行政区划多边形图层(Choropleth/Categorical Map)。",
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
            "description": "加载外部 CSV 地理散点数据库，并智能根据用户的语义指令过滤并抽取特定的设施类别（如 Ambulance Depot、Fire Station 等）进行独立的异色图层分层堆叠叠加。",
            "parameters": {
                "type": "object",
                "properties": {
                    "csv_name": {
                        "type": "string",
                        "description": "要加载的外部CSV文件名，默认传入 'AllTogether.csv'。"
                    },
                    "facility_types": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "🌟核心：需要从用户口令中精准提取并进行空间打点筛选的设施类别英文关键字数组。例如用户提到救护车或救护站，传入 ['Ambulance Depot']；若提到消防局，传入 ['Fire Station']。可以传入多个类别。"
                    },
                    "cmap": {
                        "type": "string",
                        "description": "散点分类间区隔的色带名称，默认推荐使用高对比度离散色带 'Set1' 或 'tab10'。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_points_to_districts",
            "description": "Perform spatial aggregation: spatially join filtered CSV point assets with administrative district polygons, count facilities per district, and render a quantitative choropleth map with English interval legend. Use when the user asks for per-district counts, density, distribution statistics, or aggregated thematic mapping (e.g. 'how many fire stations in each district').",
            "parameters": {
                "type": "object",
                "properties": {
                    "csv_name": {
                        "type": "string",
                        "description": "External CSV filename to load point assets from. Default: 'AllTogether.csv'."
                    },
                    "facility_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required facility category filters (case-insensitive substring match). Examples: ['Fire Station'], ['Ambulance Depot'], ['Primary School']. Supports multiple categories."
                    },
                    "cmap": {
                        "type": "string",
                        "description": "Sequential colormap for quantitative choropleth. Recommended: 'YlOrRd', 'Blues', 'Greens', 'Purples', 'Reds'."
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of classification intervals for the choropleth legend. Default: 5."
                    }
                },
                "required": ["facility_types"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_title",
            "description": "在当前地图画布的正上方顶部居中位置添加自定义的中文或英文主标题文本。",
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
            "description": "在当前地图画面的右上角指定安全区域内叠加添加标准的地理指北针要素，提升地图专业观感。",
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
            "description": "Overlay a standard international line scale bar on the map canvas showing real-world ground distance. Default 10 km at lower-left, avoiding legend and compass. Use when the user requests a scale bar, distance reference, or cartographic scale indicator.",
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
            "description": "为当前的地图画面激活地理经纬度网格辅助线，并在画布四周边缘显化地理坐标轴刻度标签。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]