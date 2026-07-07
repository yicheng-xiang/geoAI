import os
import sys

# 1. 🛡️ 刚性防御：获取当前 tools 目录的绝对路径，强行置顶注入 sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 2. 🌟 移除所有可能导致混淆的点号（.），全部使用环境内最绝对安全的直接导入
import base_map
import map_elements
import layer_styles
import spatial_aggregation

# 3. 从已经注入环境的绝对模块中提取具体的工具函数
init_canvas = base_map.init_canvas
export_map_to_base64 = base_map.export_map_to_base64
finalize_hong_kong_window = base_map.finalize_hong_kong_window

add_title = map_elements.add_title
add_compass = map_elements.add_compass
add_gridlines = map_elements.add_gridlines
add_scale_bar = map_elements.add_scale_bar

draw_choropleth = layer_styles.draw_choropleth
add_points_layer = layer_styles.add_points_layer
aggregate_points_to_districts = spatial_aggregation.aggregate_points_to_districts

# 4. 构建大模型大脑可以直接动态呼叫的中央工具箱注册表字典
REGISTRY_TOOLS = {
    "init_canvas": init_canvas,
    "export_map_to_base64": export_map_to_base64,
    "draw_choropleth": draw_choropleth,
    "add_points_layer": add_points_layer,
    "aggregate_points_to_districts": aggregate_points_to_districts,
    "add_title": add_title,
    "add_compass": add_compass,
    "add_gridlines": add_gridlines,
    "add_scale_bar": add_scale_bar,
}