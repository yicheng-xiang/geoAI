# 面向香港公共设施的自然语言 GIS 分析系统

GeoAI 让用户通过对话完成公共设施数据发现、地图绘制与空间分析。Azure OpenAI 负责理解需求并调用工具，Python 后端执行空间计算，前端展示交互地图并支持 PNG 导出。

## 核心功能

- **数据接入**：本地设施与行政区数据、Excel 点数据上传、CSDI 官方数据搜索与下载。
- **空间分析**：分区数量与密度、缓冲区查询、基于有向路网的驾驶可达分析、跨数据集设施查询。
- **交互制图**：十八区设色、设施点位、多图层叠加，以及通过对话修改标题、颜色和地图要素。
- **结果管理**：地图导出、会话隔离、数据质量检查与来源记录；完整统计和质量报告表格展示仍待完善。

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

双击项目根目录的 **start_geoai.bat**，打开 [系统页面](http://localhost:5173/)。首次可输入：

> Show all 18 Hong Kong districts, colored by district name using tab20.

确认生成地图后，可继续修改标题，或点击 **Export preview → Download PNG** 导出。停止系统使用 **stop_geoai.bat**；修改 `.env` 后需停止并重新启动，重启会清空临时会话数据。

### 4. 可选：准备驾驶分析路网

**使用驾驶覆盖或跨数据集车程查询前必须完成**，普通制图和缓冲区分析无需此步骤：

```powershell
.\GIS_agent\back_end\.venv\Scripts\python.exe .\GIS_agent\back_end\prepare_road_network.py
```

首次联网下载香港路网，缓存到 `.geoai-runtime/networks/`；以后默认复用。

## 使用与分析范围

完整命令已按 **基础制图、修改地图、Excel、CSDI、空间分析** 分组，见 [使用指南](docs/user-guide.md#分类使用示例)。

- **CSDI**：获取目录 → 后端按关键词筛选 → 选择数据集 → WFS 下载与校验 → 制图。搜索结果不代表可导入；当前通用适配支持单图层、具有可识别英文名称的香港 WGS84 点数据，最多 10,000 条。尚未实现 AI 数据集推荐。
- **Excel**：支持 `.xlsx` 第一张工作表，要求名称和 WGS84 经纬度，最多 5 MB、10,000 行。[字段与分析说明](docs/user-guide.md#本地与-excel-数据)
- **能力边界**：分区数量与密度目前支持本地库和 Excel；驾驶分析为恒速、有方向的路网估算，不代表实时交通或救护响应时间。暂不支持人口覆盖、公平性评价和任意数据格式。

## 常见问题

| 问题 | 处理方式 |
|---|---|
| 页面打不开 | 检查启动窗口和 `.geoai-runtime/` 日志，确认依赖已安装、5000/5173 端口可用；代理应允许 localhost / 127.0.0.1 直连。 |
| 认证失败或找不到部署 | 核对 `.env` 文件名、Endpoint、密钥和部署名，保存后重启。仅打开网页不能验证密钥。 |
| 驾驶分析提示缺少路网 | 先执行上面的路网准备命令。 |
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

2026-09-08 上传前验证：**82 项后端测试、14 项前端测试、lint 和 build 通过**。自动化测试不调用真实 Azure OpenAI；真实 WFS 和浏览器验收范围见验收记录。本次文档调整未重新执行模型验收。
