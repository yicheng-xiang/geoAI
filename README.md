# GeoAI

基于大语言模型的自然语言 GIS 制图 Agent。系统接收中英文地图指令，调用后端的 GeoPandas / Matplotlib 工具链，流式生成香港专题地图，并在前端实时展示思考过程和出图结果。

## 当前能力

- 行政区分类/分级设色图
- 设施点图层叠加
- 按行政区进行空间聚合统计并生成 choropleth
- 自动添加标题、指北针、比例尺、经纬网与地图框
- OSM 高精度陆地背景底图（按香港范围 `bbox` 增量加载）
- SSE 流式回传中间步骤与最终图片

## 项目结构

```text
geoAI/
└── GIS_agent/
    ├── back_end/
    │   ├── server.py                 # Flask API / SSE 网关
    │   ├── agent.py                  # ReAct Agent 编排
    │   ├── requirements.txt          # Python 依赖
    │   ├── agent_schemas/
    │   │   └── tools_definition.py   # LLM function calling schema
    │   └── tools/
    │       ├── base_map.py           # 底图初始化、OSM 背景、视窗裁切
    │       ├── layer_styles.py       # 行政区/点图层绘制与图例
    │       ├── spatial_aggregation.py# 空间聚合统计工具
    │       └── map_elements.py       # 标题、指北针、比例尺、经纬网/地图框
    ├── front_end/
    │   ├── src/App.jsx               # 前端主界面
    │   └── package.json
    └── data/
```

## 环境要求

| 组件 | 版本建议 |
|------|----------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

后端需要可用的 Azure OpenAI 资源，并提供与 `agent.py` 中模型名一致的部署（当前代码使用 `gpt-5-mini`）。

## 数据准备

`GIS_agent/data/` 目录需要至少包含以下数据：

| 路径 | 用途 |
|------|------|
| `HKDistrict18.shp` 及其配套文件 | 香港 18 区行政边界 |
| `AllTogether.csv` | 设施点数据（含经纬度与 `FACILITY_TYPE` 字段） |
| `land-polygons-complete-4326/land-polygons-complete-4326/land_polygons.shp` 及配套文件 | OSM 高精度陆地背景底图 |

说明：

- 当前 `base_map.py` 中的 `DATA_PATH` 和 `WORLD_SHP_PATH` 为绝对路径，默认指向 `D:\geoAI\GIS_agent\data\...`。
- 如果你的项目不在 `D:\geoAI`，请同步修改 `base_map.py` 中这两个路径。
- `spatial_aggregation.py` 的设施点 CSV 使用相对路径解析，通常无需改动。

## 后端启动

### 1. 安装依赖

```powershell
cd D:\geoAI\GIS_agent\back_end
pip install -r requirements.txt
```

### 2. 配置 Azure OpenAI

复制并编辑环境变量文件：

```powershell
copy .env.example .env
```

`.env` 至少需要：

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-api-key-here
```

### 3. 启动后端

```powershell
python server.py
```

默认地址：

- 后端 API: `http://127.0.0.1:5000`

## 前端启动

### 1. 安装依赖

```powershell
cd D:\geoAI\GIS_agent\front_end
npm install
```

### 2. 启动开发服务器

```powershell
npm run dev
```

浏览器通常访问：

- 前端页面: `http://localhost:5173`

前端默认向 `http://127.0.0.1:5000` 请求后端，因此应先启动后端。

## 使用方式

在左侧输入框直接输入自然语言指令，例如：

- `Show Hong Kong districts colored by name with a title, compass, scale bar and gridlines.`
- `Plot all ambulance depots on the district map.`
- `Count ambulance depots by district and render a density choropleth.`
- `Show primary school density by district with legend and title.`

点击 `Execute Command` 后，前端会流式显示：

- Agent 当前 thought
- 每一步工具调用日志
- 实时更新的地图图片

点击 `Clear Sandbox` 可重置会话与画布。

## 当前制图元素

系统当前支持的主要地图元素与工具：

| 工具 | 说明 |
|------|------|
| `draw_choropleth` | 基于行政区属性字段绘制分类/分级设色图 |
| `add_points_layer` | 过滤 CSV 设施点并叠加到地图 |
| `aggregate_points_to_districts` | 点落区空间连接、计数、专题图渲染 |
| `add_title` | 标题 |
| `add_compass` | 右上角指北针 |
| `add_scale_bar` | 左下角线段式比例尺 |
| `add_gridlines` | 学术风经纬网、坐标标签与地图框 |

说明：

- 最终导出前会强制执行香港视窗裁切与等比例锁定，避免底图撑大视窗。
- Agent 侧已补充兜底逻辑，最终图若遗漏经纬网，会在导出前自动补加。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat_and_map_stream` | 接收 `{ "prompt": "..." }`，SSE 流式返回 `{ thought, log, image, status }` |
| `POST` | `/api/clear_session` | 清空当前会话与画布状态 |

## 常用命令

```powershell
# 前端构建
cd D:\geoAI\GIS_agent\front_end
npm run build

# 前端预览
npm run preview

# 前端 lint
npm run lint
```

## 常见问题

**Q: 后端启动后报找不到 Shapefile？**  
检查 `HKDistrict18.shp` 和 `land_polygons.shp` 是否存在，并确认 `base_map.py` 里的绝对路径与本机目录一致。

**Q: 地图能生成，但没有经纬网或地图框？**  
确认使用的是最新后端代码。当前版本在 Agent 最终导出前会自动补调 `add_gridlines`。

**Q: OSM 底图加载很慢？**  
当前已通过 `bbox` 仅按香港周边范围增量加载。首次运行仍可能较慢，取决于磁盘速度和 OSM 数据体量。

**Q: 图例挡住地图内容？**  
当前版本图例默认放在地图内部右下角。如果仍需调整，可修改 `layer_styles.py` 中 `refresh_clean_legend()` 的 `loc` 和 `bbox_to_anchor`。

**Q: 多用户会不会互相影响？**  
会。当前后端使用全局内存态 `GLOBAL_MAP_STATE` / `GLOBAL_MESSAGES`，适合本地单用户演示，不适合多用户并发。

## 备注

- 前端依赖中包含 `leaflet` / `react-leaflet`，但当前主流程实际展示的是后端返回的 Base64 图片，而不是交互式 Leaflet 地图。
- 这是一个原型系统，适合课程项目、毕设原型和本地研究演示。
