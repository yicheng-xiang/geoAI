# 面向香港公共设施的自然语言 GIS 分析系统

GeoAI 让用户通过对话完成公共设施数据发现、地图绘制与空间分析。Azure OpenAI 负责理解需求并调用工具，Python 后端执行空间计算，前端展示交互地图并支持 PNG 导出。

## 核心功能

- **数据接入**：本地设施与行政区数据、Excel 点数据上传、CSDI 官方数据搜索与下载。
- **空间分析**：分区数量与密度、直线缓冲区查询、步行/驾车最短路网距离及路线、恒速驾驶时间覆盖、跨数据集设施查询。
- **交互制图**：十八区设色、设施点位、多图层叠加，以及通过对话修改标题、颜色和地图要素。
- **结果管理**：可选多标签结果表格、地图双向联动、搜索/排序/分页、筛选结果 CSV 导出、历史图层恢复，以及会话隔离、数据质量检查与来源记录。

左侧 **GeoAI chat** 支持连续追问，工具日志收纳在 **Operation details**；Excel 与 CSDI 入口位于 **Data sources & uploads**。表格默认收起，不影响独立制图。

## 技术栈

| 层次 | 技术 | 用途 |
|---|---|---|
| 前端界面 | React、Vite | 页面交互与前端构建 |
| 地图展示 | React-Leaflet、Leaflet、MapLibre GL | 交互地图、图层和底图渲染 |
| 后端服务 | Python、Flask | 接口、会话与工具执行 |
| 大模型交互 | Azure OpenAI、Function Calling | 理解需求、选择工具和生成参数 |
| 空间数据处理 | GeoPandas、Shapely | 坐标转换、空间关联与缓冲区计算 |
| 路网分析 | OSMnx、NetworkX | 路网准备、最短路径与可达性计算 |
| 表格处理 | pandas、openpyxl | Excel 读取、字段整理与校验 |

**数据来源与接口**：CSDI 官方目录及 WFS 服务、地政总署 Location Search API、本地设施与行政区数据、用户上传的 Excel。

## 快速启动

本手册以 **Windows + PowerShell** 为例。准备 Git、Python 3.10+、Node.js 20.19+（20.x）或 22.12+，以及可用的 Azure OpenAI 资源和部署。

### 1. 获取项目并安装依赖

在准备存放项目的文件夹中打开 PowerShell，依次执行：

```powershell
git clone https://github.com/yicheng-xiang/geoAI.git
cd geoAI\GIS_agent\back_end
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\front_end
npm ci
cd ..\..
```

也可在 GitHub 点击 **Code → Download ZIP** 并解压，再从项目根目录执行安装步骤（跳过克隆，将第二行改为 `cd GIS_agent\back_end`）。后续命令均从项目根目录运行，无需放在固定盘符。

### 2. 填写密钥

从模板创建本地配置并用记事本打开；已有配置不会被覆盖：

```powershell
if (!(Test-Path GIS_agent\back_end\.env)) {
    Copy-Item GIS_agent\back_end\.env.example GIS_agent\back_end\.env
}
notepad GIS_agent\back_end\.env
```

保留等号左边的名称，将右边替换为同一 Azure OpenAI 资源的 **Endpoint 和完整 API Key**，按 **Ctrl+S** 保存：

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-api-key
```

文件必须名为 **`.env`，不能是 `.env.txt`**。真实密钥只放在本地 `.env`，该文件已被 Git 忽略；仓库模板只保留示例值。当前 [agent.py](GIS_agent/back_end/agent.py) 使用部署名 `gpt-5-mini`、API 版本 `2024-12-01-preview`；部署名不同需修改代码中的 `model` 值。[详细配置说明](docs/user-guide.md#详细密钥配置)

### 3. 启动与首次使用

双击项目根目录的 **start_geoai.bat**，打开 [系统页面](http://localhost:5173/)，首次可运行下方第 1 个使用例子。

确认生成地图后，可继续修改标题，或点击 **Export preview → Download PNG** 导出。停止系统使用 **stop_geoai.bat**；修改 `.env` 后需停止并重新启动，重启会清空临时会话数据。

### 4. 可选：准备路网

**使用路网分析前须准备对应模式的缓存**；普通制图和直线缓冲区分析无需此步骤：

```powershell
.\GIS_agent\back_end\.venv\Scripts\python.exe .\GIS_agent\back_end\prepare_road_network.py --mode drive
# 仅在需要步行距离分析时执行
.\GIS_agent\back_end\.venv\Scripts\python.exe .\GIS_agent\back_end\prepare_road_network.py --mode walk
```

首次联网下载香港路网，分别缓存到 `.geoai-runtime/networks/hong_kong_drive.graphml` 和 `hong_kong_walk.graphml`；以后默认复用。步行查询目前较慢。路网距离按米计算，驾驶时间按分钟及情景速度计算，两者不能互换。

## 使用例子

以下英文请求可直接复制到聊天框。除标明连续操作的例子外，建议使用独立会话；清空会话会删除临时数据。数据数量以实际快照为准。

| # | 功能与前置条件 | 可复制的请求 |
|---|---|---|
| 1 | 行政区分类制图 | `Show all 18 Hong Kong districts, colored by district name using tab20.` |
| 2 | 本地设施按区计数 | `Count ambulance depots by district using the built-in dataset and map the counts.` |
| 3 | 本地设施按区密度 | `Calculate primary school density per square kilometre by district using the built-in dataset.` |
| 4 | 设施点位与图层叠加；接第 1 例 | `Overlay ambulance depot points from the built-in dataset on the current district map. Keep the district layer.` |
| 5 | 仅修改展示；接第 2 例 | `Change the palette to Blues and the title to "Ambulance Depots by District". Keep the analysis unchanged.` |
| 6 | Excel 点数据落区统计；先在页面上传 `.xlsx` | `Count all uploaded points by district and create a choropleth.` |
| 7 | 地名解析与直线缓冲区；需要联网 | `Find primary schools within a straight-line distance of 1 km from Hong Kong Polytechnic University Block Z using the built-in dataset.` |
| 8 | 驾驶覆盖；先准备路网 | `Show 10-minute driving coverage FROM Aberdeen Ambulance Depot at 30 km/h using the built-in dataset.` |
| 9 | CSDI 目录发现、下载与制图；需要联网 | `Search CSDI for badminton courts and show their locations in Hong Kong.` |
| 10 | CSDI 跨数据集缓冲区查询；需要联网，工具会下载所需数据 | `Using CSDI, find ambulance depots within 500 metres of Tung Cheong Street Sports Centre from the public fitness rooms dataset.` |

**连续追问示例**：接第 7 例，逐条发送并等待上一轮结束；步行和驾车路网均须事先准备。

1. `Use walking distance instead of straight-line distance. Keep the same origin and 1 km threshold.`
2. `Now use driving distance and increase the threshold to 3 km.`
3. `Include secondary schools too, but only those within the same driving distance. Show the shortest routes to the matched schools.`
4. `Make primary schools red and secondary schools blue. Keep the analysis unchanged.`

改变距离、模式或类别会重新分析并保存新结果；仅修改标题或通过 `restyle_map` 改色不新增结果。路线是实际返回的最短路几何，不是直线连点。

坐标查询、地图要素、数据刷新和跨数据集车程等更多例子见 [使用指南](docs/user-guide.md#分类使用示例)。

## 可选结果表格

点击 **Show table** 展开。每份分析对应一个标签，可独立搜索、数字排序和分页（每页 50 条）；CSV 导出包含当前筛选后的全部记录。点击表格行或地图业务要素可双向选中、定位并查看弹窗。

切换标签不自动换图。旧结果显示 **Not displayed on map** 时，点击 **Show on map** 可恢复保存的图层，无需重新计算或下载；关闭标签仅隐藏表格，可通过 **Result list** 重开。清空会话或后端重启才会清除这些内存结果。PNG 默认不包含表格和临时选中高亮。

## 数据与分析范围

- **CSDI**：获取目录 → 后端按关键词筛选 → 选择数据集 → WFS 下载与校验 → 制图。搜索结果不代表可导入；当前通用适配支持单图层、具有可识别英文名称的香港 WGS84 点数据，最多 10,000 条。尚未实现 AI 数据集推荐。
- **Excel**：支持 `.xlsx` 第一张工作表，要求名称和 WGS84 经纬度，最多 5 MB、10,000 行。[字段与分析说明](docs/user-guide.md#本地与-excel-数据)
- **能力边界**：分区数量与密度支持注册点数据，包括本地库、Excel 和已下载的兼容 CSDI 快照。路网距离包含设施接入道路的距离；驾驶时间为恒速、有方向的情景估算，不代表实时交通或救护响应时间。暂不支持人口覆盖、公平性评价和任意数据格式。
- **地点与来源**：地名由官方接口解析，低相关、歧义或楼座不符的候选不能直接作为起点。CSDI 快照与本地库相互独立；“已下载”不等于“正在地图显示”。

## 常见问题

| 问题 | 处理方式 |
|---|---|
| 页面打不开 | 检查启动窗口和 `.geoai-runtime/` 日志，确认依赖已安装、5000/5173 端口可用；代理应允许 localhost / 127.0.0.1 直连。 |
| 认证失败或找不到部署 | 核对 `.env` 文件名、Endpoint、密钥和部署名，保存后重启。仅打开网页不能验证密钥。 |
| 步行/驾驶分析提示缺少路网 | 按报错模式执行上面的 `--mode walk` 或 `--mode drive` 命令。 |
| `GEOCODING_SERVICE_UNAVAILABLE` | 地名接口连接失败，不等于设施为零。稍后重试原请求，或提供确认过的 WGS84 坐标；不需要改端口。当前默认超时 10 秒、无自动重试，成功地点缓存仅保存在内存中。 |
| `LOCATION_CONFIRMATION_REQUIRED` | 使用提示中的准确官方名称或确认过的坐标；不要把模糊候选直接当成目标地点。失败时保留上次成功地图，不代表新分析完成。 |
| CSDI 下载超时或不兼容 | 网络超时可重试；多图层、线面数据或不符合字段要求的数据需额外适配。刷新失败保留旧快照。 |
| 重启后数据消失 | Excel、CSDI 快照和对话保存在会话内存中，重启后需要重新导入；刷新数据后需重新运行分析。 |

## 项目结构与开发

```text
GIS_agent/
├── back_end/       # Flask、AI 调度、GIS 工具与后端测试
├── front_end/      # React 页面、地图、PNG 导出与前端测试
└── data/           # 本地行政区与设施数据
docs/              # 使用指南、开发说明与验收记录
start_geoai.bat     # 启动系统
stop_geoai.bat      # 停止系统
```

[开发接口与测试命令](docs/development.md) · [CSDI 验收记录](docs/csdi-stability-report-2026-09-07.md)

**2026-09-11 阶段验收：120 项后端测试、28 项前端测试全部通过，lint 与生产构建通过。** 已使用真实模型和 GIS 工具执行12组60轮连续对话测试，完成主要缺陷修复与针对性复测；网页实测验证了地图替换、配色修改、历史结果恢复及地图—表格联动。本次发布不包含新增测试集及详细验收报告；官方服务仍有偶发波动，PNG 导出尚待补充完整验收。
