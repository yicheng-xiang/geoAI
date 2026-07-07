# GeoAI

基于大语言模型的自然语言 GIS 制图 Agent。系统接收中英文地图指令，调用 GeoPandas / Matplotlib 工具链生成香港专题地图，并通过前端实时展示思考过程和出图结果。

## 当前能力

- 行政区分类/分级设色图
- 设施点图层叠加
- 点落区空间聚合统计与 choropleth
- 标题、指北针、比例尺、经纬网、地图框
- OSM 高精度陆地背景底图（按香港范围 `bbox` 增量加载）
- SSE 流式回传中间步骤与最终图片

## 项目结构

```text
geoAI/
└── GIS_agent/
    ├── back_end/
    │   ├── server.py
    │   ├── agent.py
    │   ├── requirements.txt
    │   ├── agent_schemas/tools_definition.py
    │   └── tools/
    │       ├── data_catalog.py
    │       ├── base_map.py
    │       ├── layer_styles.py
    │       ├── spatial_aggregation.py
    │       └── map_elements.py
    ├── front_end/
    └── data/
```

## 环境要求

| 组件 | 版本建议 |
|------|----------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

后端需要 Azure OpenAI 资源，并提供与 `agent.py` 中模型名一致的部署（当前使用 `gpt-5-mini`）。

## 启动方式

### 后端

```powershell
cd D:\geoAI\GIS_agent\back_end
pip install -r requirements.txt
copy .env.example .env
python server.py
```

`.env` 至少需要：

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-api-key-here
```

后端默认地址：`http://127.0.0.1:5000`

### 前端

```powershell
cd D:\geoAI\GIS_agent\front_end
npm install
npm run dev
```

前端通常访问：`http://localhost:5173`  
前端默认请求后端 `http://127.0.0.1:5000`。

## 使用方式

示例指令：

- `Show Hong Kong districts colored by name with a title, compass, scale bar and gridlines.`
- `Plot all ambulance depots on the district map.`
- `Count ambulance depots by district and render a density choropleth.`

执行后前端会流式显示：

- Agent 当前 thought
- 工具调用日志
- 实时地图图片

`Clear Sandbox` 可重置会话与画布。

## 数据管理

所有主要数据入口统一注册在：

- `GIS_agent/back_end/tools/data_catalog.py`

当前分为两类：

- `VECTOR_DATASETS`：矢量边界、底图
- `TABULAR_DATASETS`：CSV 点位表

当前已注册：

- `hong_kong_districts` → `HKDistrict18.shp`
- `osm_land_polygons` → `land_polygons.shp`
- `all_facilities` → `AllTogether.csv`

如果项目目录变化，优先修改 `data_catalog.py` 里的 `DATA_ROOT`，尽量不要在其他工具文件里重新写死路径。

### 新增 / 修改 / 删除数据

**新增**

1. 把文件放到 `GIS_agent/data/`
2. 在 `data_catalog.py` 里注册
3. 如有必要，再更新工具逻辑或 Agent 提示词

**修改**

- 文件同名替换：通常不需要改代码，只要格式兼容
- 文件名或目录变化：同步改 `data_catalog.py` 中对应项的 `path` / `filename`

**删除**

1. 删除 `GIS_agent/data/` 中的文件
2. 删除 `data_catalog.py` 中对应注册项
3. 清理 README、工具或 Agent 提示词中的引用

## 数据格式要求

详细格式规范已拆分到单独文档：

- [`docs/data-format.md`](docs/data-format.md)

摘要：

- 点位数据使用 CSV，推荐至少包含 `Latitude`、`Longitude`、`FACILITY_TYPE`
- 面数据使用完整 shapefile，推荐为 polygon / multipolygon，坐标系为 `EPSG:4326`
- 新增或替换数据时，优先更新 `GIS_agent/back_end/tools/data_catalog.py`

## 当前制图元素

| 工具 | 说明 |
|------|------|
| `draw_choropleth` | 行政区分类/分级设色图 |
| `add_points_layer` | 点位图层 |
| `aggregate_points_to_districts` | 点落区聚合统计 |
| `add_title` | 标题 |
| `add_compass` | 指北针 |
| `add_scale_bar` | 比例尺 |
| `add_gridlines` | 经纬网、坐标标签、地图框 |

说明：

- 导出前会强制执行香港视窗裁切与等比例锁定
- Agent 已有兜底逻辑，最终图若遗漏经纬网，会在导出前自动补加

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat_and_map_stream` | 接收 `{ "prompt": "..." }`，SSE 返回 `{ thought, log, image, status }` |
| `POST` | `/api/clear_session` | 清空当前会话与画布状态 |

## 常用命令

```powershell
cd D:\geoAI\GIS_agent\front_end
npm run build
npm run preview
npm run lint
```

## 常见问题

**Q: 后端找不到 Shapefile？**  
检查 `HKDistrict18.shp`、`land_polygons.shp` 是否存在，并确认 `data_catalog.py` 中路径正确。

**Q: 地图没有经纬网或地图框？**  
确认使用最新后端代码。当前版本会在最终导出前自动补调 `add_gridlines`。

**Q: OSM 底图加载很慢？**  
当前已通过 `bbox` 只加载香港周边范围，但首次运行仍可能较慢。

**Q: 图例挡住地图内容？**  
可调整 `layer_styles.py` 中 `refresh_clean_legend()` 的 `loc` 和 `bbox_to_anchor`。

**Q: 多用户会互相影响吗？**  
会。当前使用全局内存态 `GLOBAL_MAP_STATE` / `GLOBAL_MESSAGES`，适合本地单用户演示。

## 备注

- 前端依赖里有 `leaflet` / `react-leaflet`，但当前主流程展示的是后端返回的 Base64 图片
- 项目适合课程项目、毕设原型和本地研究演示
