import os
import sys

# 1. 🛡️ 刚性防御：获取当前 tools 目录的绝对路径，强行置顶注入 sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 2. 🌟 移除所有可能导致混淆的点号（.），全部使用环境内最绝对安全的直接导入
import map_state
import map_elements
import layer_styles
import spatial_aggregation
import buffer_analysis
import network_accessibility
import csdi_tools
import network_distance
import map_restyle

# 3. 从已经注入环境的绝对模块中提取具体的工具函数
init_map_state = map_state.init_map_state

add_title = map_elements.add_title
add_compass = map_elements.add_compass
add_gridlines = map_elements.add_gridlines
add_scale_bar = map_elements.add_scale_bar

draw_choropleth = layer_styles.draw_choropleth
add_points_layer = layer_styles.add_points_layer
aggregate_points_to_districts = spatial_aggregation.aggregate_points_to_districts
buffer_facility_coverage = buffer_analysis.buffer_facility_coverage

# 4. 构建大模型大脑可以直接动态呼叫的中央工具箱注册表字典
REGISTRY_TOOLS = {
    'restyle_map': map_restyle.restyle_map,
    'network_distance_query': network_distance.network_distance_query,
    'csdi_catalog': csdi_tools.csdi_catalog,
    'csdi_download': csdi_tools.csdi_download,
    'csdi_map': csdi_tools.csdi_map,
    'csdi_nearby': csdi_tools.csdi_nearby,
    "network_service_area": network_accessibility.network_service_area,
    "init_map_state": init_map_state,
    "draw_choropleth": draw_choropleth,
    "add_points_layer": add_points_layer,
    "aggregate_points_to_districts": aggregate_points_to_districts,
    "buffer_facility_coverage": buffer_facility_coverage,
    "add_title": add_title,
    "add_compass": add_compass,
    "add_gridlines": add_gridlines,
    "add_scale_bar": add_scale_bar,
}
