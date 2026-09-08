# GeoAI

面向香港公共设施的自然语言 GIS 分析原型。用户描述需求，由 Azure OpenAI 调用受约束的 GIS 工具，后端返回统计、参数、GeoJSON 和质量报告，前端提供交互地图及 PNG 导出。

## 功能

- 香港十八区分类图、设施点图及多图层叠加。
- 按区统计设施数量（count）或每平方公里密度（density_per_km2）。
- 通过坐标或官方地名搜索，进行 Buffer 范围内设施统计。
- 基于香港有向路网估算指定分钟数的驾驶覆盖范围。
- Excel 点数据上传、CSDI 动态目录发现与多数据集临时缓存。
- 多轮修改标题、配色和图层类型；交互地图与导出使用统一表达。
- 会话隔离、坐标与几何质量检查、统一失败状态及分析来源追溯。

**技术栈：** React / Vite / React-Leaflet / MapLibre GL；Python / Flask / Azure OpenAI Function Calling；GeoPandas / Shapely / OSMnx / NetworkX。

## 快速启动

环境：Python 3.10+；Node.js 20.19+（20.x）或 22.12+；可用的 Azure OpenAI 部署。

首次安装：

```powershell
cd D:\geoAI\GIS_agent\back_end
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Only create .env if it does not already exist.
if (!(Test-Path .env)) { Copy-Item .env.example .env }

cd D:\geoAI\GIS_agent\front_end
npm install
```

### 配置 Azure OpenAI 密钥（首次使用必做）

密钥填写在项目文件夹内的 **`GIS_agent/back_end/.env` 文件**，不是网页聊天框，也不是 Python 代码。以本项目放在 `D:\geoAI` 为例，完整路径为 `D:\geoAI\GIS_agent\back_end\.env`；如果项目放在其他目录，请替换下面命令中的路径。

**1. 准备连接信息。** 从你使用的 Azure OpenAI 资源获取 Endpoint（服务地址）和 API Key（密钥）；如果资源由老师或团队管理，请向资源管理员获取这两项信息和部署名称。Endpoint 和密钥必须属于同一个资源。本项目按 Azure OpenAI 方式连接，不能直接填入普通 OpenAI 平台的 API Key。

**2. 创建并打开配置文件。** 在 PowerShell 中逐行运行：

```powershell
cd D:\geoAI\GIS_agent\back_end
# 从模板创建 .env；已有配置时保留原文件，不覆盖。
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

GitHub 中提供的是 `.env.example` 模板，需要在自己的电脑上复制成 `.env`。如果前面的安装步骤已经创建了 `.env`，此处会直接打开它。

**3. 填入自己的地址和密钥。** 在打开的记事本中，保留等号左边的变量名，将右边的示例值替换为自己的实际值：

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-api-key
```

- 第一行：将整个 `https://your-resource.cognitiveservices.azure.com/` 替换为资源提供的实际 Endpoint，不要自行拼接聊天请求路径。
- 第二行：将 `your-api-key` 替换为完整的实际密钥，不要保留这个占位文字。
- 一项一行，只复制上述两行内容，不要复制 Markdown 的代码块标记。按 **Ctrl+S** 保存并关闭记事本。
- 文件名必须是 **`.env`**，不能是 `.env.txt`。如果手动另存为，请选择“所有文件”类型，并检查文件扩展名。

**4. 核对部署名称。** 当前 [agent.py](GIS_agent/back_end/agent.py) 使用部署名 `gpt-5-mini` 和 API 版本 `2024-12-01-preview`。Azure 资源中必须存在对应部署；如果实际部署名称不同，需要将代码中的 `model="gpt-5-mini"` 改为实际部署名称。当前部署名和 API 版本没有通过 `.env` 配置，仅在 `.env` 添加同名配置项不会生效。

**5. 启动或重启后验证。** 完成配置后按下文启动系统。如果系统已经运行，先双击 `stop_geoai.bat`，再双击 `start_geoai.bat`，使后端重新读取配置。重启会清空临时会话和下载快照。打开页面后，发送下文的“行政区分类”示例，检查是否能完成 AI 工具调用并生成地图；仅能打开网页不代表密钥已经验证成功。

如果出现认证失败，请检查 Endpoint 与密钥是否复制完整、属于同一个资源，以及文件是否误存为 `.env.txt`；如果提示找不到部署，请核对部署名称。

`.env` 已被 Git 忽略，**不要上传真实密钥，也不要把密钥贴入聊天或截图**。提交到仓库的 `.env.example` 应始终只保留示例值。

### 启动系统

之后双击根目录 **start_geoai.bat**，自动启动前后端并打开 [前端页面](http://localhost:5173/)。停止使用 **stop_geoai.bat**，日志在 `.geoai-runtime/`。

手动调试可分别在两个终端运行：

```powershell
# Backend
cd D:\geoAI\GIS_agent\back_end
.\.venv\Scripts\python.exe server.py
```

```powershell
# Frontend
cd D:\geoAI\GIS_agent\front_end
npm run dev
```

默认端口：前端 5173，后端 5000。如本机地址被代理拦截，将 localhost / 127.0.0.1 设为直连，无需修改原代理端口。

## 使用示例

以下为基于当前工具实现的英文示例，不表示每条都已通过真实 AI 验收。独立实验可先清空会话；修改和叠加命令应接着上一张地图执行。

| 场景 | 英文命令 |
|---|---|
| 行政区分类 | `Show all 18 Hong Kong districts, colored by district name using tab20.` |
| 本地设施点 | `Use the built-in dataset to display ambulance depot locations.` |
| 数量统计 | `Count ambulance depots by district using the built-in dataset and map the counts.` |
| 密度分析 | `Calculate primary school density per square kilometre by district using the built-in dataset.` |
| 修改标题 | `Change the map title to "Hong Kong Facility Distribution".` |
| 修改配色 | `Keep the ambulance depot count analysis, but redraw it using Blues.` |
| 面图改点图 | `Replace the current polygon map with ambulance depot points from the built-in dataset.` |
| 点图改面图 | `Replace the point map with an ambulance depot count choropleth using the built-in dataset.` |
| 叠加图层 | `Overlay ambulance depot points on the current district map. Keep the district layer.` |
| 地图要素 | `Enable the north arrow, a 1 km scale bar, and dynamic corner coordinates.` |
| 上传点显示 | `Display all uploaded data on the map.` |
| 上传点统计 | `Count all uploaded points by district and create a choropleth.` |
| 上传点密度 | `Calculate uploaded point density per square kilometre by district.` |
| 坐标 Buffer | `Find ambulance depots within 500 metres of latitude 22.250370, longitude 114.173867, using the built-in dataset.` |
| 地名 Buffer | `Find primary schools within 2 km of Hong Kong Polytechnic University Block Z using the built-in dataset.` |
| 驾驶覆盖 | `Show 10-minute driving coverage FROM Aberdeen Ambulance Depot at 30 km/h using the built-in dataset.` |
| 动态数据发现 | `Search CSDI for badminton courts and show their locations in Hong Kong.` |
| 多份临时数据 | `Download CSDI public fitness rooms and ambulance depots. Keep both in this session.` |
| 刷新官方数据 | `Refresh the CSDI ambulance depots snapshot from the official source.` |
| 跨数据集 Buffer | `Using CSDI, find ambulance depots within 500 metres of Tung Cheong Street Sports Centre from the public fitness rooms dataset.` |
| 跨数据集车程 | `Using CSDI, find ambulance depots reachable within a 5-minute drive FROM Tung Cheong Street Sports Centre at 30 km/h.` |

生成地图后，点击 **Export preview → Download PNG**。切回 Interactive map 保留地图实例与视口。完整经纬网固定隐藏，使用四角坐标；地图要素位置由响应式布局控制。

## 数据与分析说明

### 本地与 Excel 数据

内置行政区和设施数据位于 `GIS_agent/data/`，通过 `tools/data_catalog.py` 注册。AI 只能使用逻辑数据集 ID，不能读取任意文件路径。

上传仅支持 `.xlsx` 第一张工作表，坐标为 WGS84（EPSG:4326）：

| Name | Latitude | Longitude | FacilityType（可选） |
|---|---:|---:|---|
| Clinic A | 22.3193 | 114.1694 | Clinic |

限 5 MB、10,000 行、20 类设施。缺少 FacilityType 时使用 Uploaded Facility；无效名称、空坐标及越界点会报告或排除，疑似重复点标记但不自动删除。再次上传替换本会话的 Excel 数据并使旧分析地图失效。

### CSDI 临时数据

在 **CSDI temporary datasets** 输入关键词，选择结果后 Download；Map this source 填入制图命令，再点击 Run request。空搜索框不展示默认下载卡片。

- 动态查询官方目录，缓存 15 分钟；下载时探测 WFS 图层并验证点数据。
- 当前通用适配仅支持单图层、可识别名称字段的香港 WGS84 点数据；目录有记录不代表一定可导入。
- 可同时保存多个快照，不修改本地数据库。Refresh snapshot 显式更新数据，已有分析不会自动重算。
- 优先使用 geometry 坐标，保留原属性，并记录来源、下载时间与 SHA256；下载时间不是官方更新时间。
- 请求使用连接池、退避重试（最多三次）及直连/代理回退，并短时复用成功线路；网络故障可使用带警告的旧目录，下载失败保留旧快照。超时不会被标记为不支持的数据源。
- 多层制图尊重每次调用的替换/叠加参数；CSDI 点层自动分配不同颜色，可通过自然语言指定十六进制颜色。最终 CSDI 回复显示实际地图层数与缓存数，检测到请求图层缺失时不报告成功。
- 公共健身室不等于所有商业健身房；羽毛球数据中的场所点数不等于独立球场片数。

### 空间指标与路网

数量是点落区后的原始计数；密度是数量除以行政区面积（km²）。面积和 Buffer 距离在 EPSG:2326 下计算，输出 GeoJSON 为 EPSG:4326。地名通过地政总署 Location Search API 解析，需核对实际匹配地点。

首次使用驾驶分析前准备路网：

```powershell
cd D:\geoAI\GIS_agent\back_end
.\.venv\Scripts\python.exe prepare_road_network.py
```

缓存位于 `.geoai-runtime/networks/hong_kong_drive.graphml`；已有文件默认复用，管理员可用 `--refresh` 重建。

驾驶分析支持 0–30 分钟（不含 0）、1–100 km/h、最多 200 个起点；默认 30 km/h，接入超过 100 m 的设施排除。输出有向可达道路及两侧各 30 m 的近似走廊，**不是实时交通或救护响应时间**。跨数据集查询使用从选定起点到目标的有向最短时间，不用覆盖面包含关系代替；反向“救护站到健身室”尚未实现。

### 会话与当前限制

- 消息、地图、Excel 与 CSDI 快照按会话保存在单个后端进程内。Clear session 清除对应会话，重启后端清除所有临时数据。
- 普通落区工具的 Agent Schema 仅支持本地库和 Excel；不要将任意 CSDI 落区统计当作已完成能力。
- 暂不支持人口覆盖、公平性评价、最近设施路径、实时交通或任意格式数据导入。
- 底图、WFS、地名解析依赖外网；简洁矢量底图失败时回退 OSM 并提示。
- 完整统计/质量报告的前端表格联动、生产认证、限流与持久会话仍待完善。
- 工具失败会终止当前执行链；仅 AI 最后总结失败时，可返回已完成的 GIS 结果并附明确警告。

## 后端接口与代码入口

默认服务地址：`http://127.0.0.1:5000`。

| 接口 | 用途 / 参数 |
|---|---|
| GET /api/health | 健康检查 |
| GET /api/session_state | 会话公开摘要；query: session_id |
| GET /api/csdi | 目录与快照；query: session_id、可选 query |
| POST /api/csdi | 下载/刷新；JSON: session_id、dataset_id、可选 refresh |
| POST /api/upload_dataset | Excel 上传；multipart: session_id、file |
| POST /api/chat_and_map_stream | 流式分析；JSON: session_id、prompt |
| POST /api/clear_session | 清空指定会话；JSON: session_id |

聊天通过 SSE 返回状态与分析结果，检查事件中的 status，不能仅看 HTTP 200。结果按工具包含 analysis、statistics、geojson、quality、map_layers 和 map_presentation。PNG 导出在前端完成，没有后端 PNG 下载接口。

主要代码：后端 `server.py`（接口）、`agent.py`（调度）、`agent_schemas/tools_definition.py`（参数）、`tools/`（GIS/CSDI）、`upload_service.py`（上传）、`session_store.py`（会话）；前端 `src/MapView.jsx`（地图）、`src/mapPresentation.js`（表达）、`src/mapExport.js`（导出）。

## 测试

```powershell
cd D:\geoAI\GIS_agent\back_end
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

cd D:\geoAI\GIS_agent\front_end
npm test
npm run lint
npm run build
```

当前有 82 个后端测试和 14 个前端地图表达测试，涵盖状态隔离、上传、质量检查、空间分析、路网方向和 CSDI 容错，不代表 100% 代码覆盖。测试不调用真实 Azure OpenAI。

手动联网检查 CSDI 可运行后端 `tests/manual_csdi_probe.py`。浏览器验收重点：数量/密度单位、图层替换、标题和图例同步、切换/导出一致性、超时失败提示及两个独立会话的数据隔离。
