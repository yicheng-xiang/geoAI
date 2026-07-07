# Data Format Guide

本文档说明 `GeoAI` 项目当前支持的数据格式要求，重点覆盖：

- 点位数据（CSV）
- 面数据（Shapefile）

数据入口统一注册在：

- `GIS_agent/back_end/tools/data_catalog.py`

## 点位数据（CSV）

主要用于：

- `add_points_layer`
- `aggregate_points_to_districts`

### 推荐字段

| 字段 | 说明 |
|------|------|
| `Latitude` | 纬度，WGS84 十进制度 |
| `Longitude` | 经度，WGS84 十进制度 |
| `FACILITY_TYPE` | 设施类别 |
| `NAME` | 可选，点位名称 |
| `ADDRESS` | 可选，地址 |
| `DISTRICT` | 可选，行政区文本 |

### 自动识别规则

工具当前不是严格写死字段名，而是按关键字自动识别：

- 纬度列：字段名包含 `LAT`
- 经度列：字段名包含 `LON` 或 `LNG`
- 类型列：字段名包含 `TYPE`、`FACILITY` 或 `CLASS`

因此以下命名通常都能识别：

- 纬度：`Latitude`、`LAT`、`Lat_WGS84`
- 经度：`Longitude`、`LON`、`Lng`
- 类型：`FACILITY_TYPE`、`TYPE`、`FacilityClass`

为了减少歧义，最推荐直接使用：

```csv
Latitude,Longitude,FACILITY_TYPE
22.25036991,114.173867,Ambulance Depot
22.28813421,114.2017064,Ambulance Depot
```

### 坐标要求

- 坐标系应为 **WGS84 / EPSG:4326**
- 坐标值应为十进制度

例如：

- `22.302711`
- `114.177216`

如果 CSV 中存的是投影坐标（如 Easting / Northing），当前工具不会自动转换，需要先预处理为 WGS84 经纬度。

### 类型字段建议

- `FACILITY_TYPE` 建议使用稳定、统一的英文类别名称
- 同一类设施尽量不要混用过多拼写

当前工具使用的是**不区分大小写的包含匹配**，例如：

- `Ambulance` 可以匹配 `Ambulance Depot`
- `Primary` 可以匹配 `Primary School`

建议尽量保持类别值规范一致，例如：

- `Ambulance Depot`
- `Fire Station`
- `Primary School`
- `Secondary School`
- `Higher Education Institutions`
- `Country Park`

### 常见问题

- 字段名里没有 `LAT` / `LON` / `TYPE` 等关键字
- 坐标不是经纬度而是投影坐标
- 类型列空值较多
- 同类设施命名不统一
- CSV 编码异常，导致文本字段读取失败

## 面数据（Shapefile）

主要用于：

- `base_map.py` 中的行政区边界与底图
- `draw_choropleth`
- `aggregate_points_to_districts`

### 基本要求

- 使用完整 shapefile 组件：至少包含 `.shp`、`.shx`、`.dbf`
- 推荐同时包含 `.prj`、`.cpg`
- 几何类型应为 polygon / multipolygon
- 坐标系推荐为 **EPSG:4326**

### 字段建议

如果用于行政区专题图，建议至少有一个可用于显示分类的文本字段，例如：

- `NAME`
- `ENAME`
- `DISTRICT`
- `ENG_NAME`

如果要做数值分级图，还需要至少一个数值字段。

### 用于空间聚合时

- 面数据应为真实行政区或区域边界
- 点数据与面数据最终需要对齐到同一 CRS
- 系统会尝试重投影，但前提是源数据 CRS 元数据正确

### 新增面数据示例

在 `data_catalog.py` 的 `VECTOR_DATASETS` 中新增一项，例如：

```python
"new_districts": {
    "path": os.path.join(DATA_ROOT, "NewDistricts.shp"),
    "crs": "EPSG:4326",
    "description": "Alternative district boundary dataset.",
    "kind": "polygon",
}
```

### 常见问题

- 缺失 `.shx` / `.dbf`
- `.prj` 缺失或 CRS 错误
- 几何不是 polygon
- 字段名混乱，导致分类字段难以识别

## 维护建议

- 新增或替换数据时，优先更新 `data_catalog.py`
- 不要把路径重新分散写回 `base_map.py`、`layer_styles.py`、`spatial_aggregation.py`
- 超大底图建议保持支持 `gpd.read_file(..., bbox=...)` 的格式，便于局部增量加载
