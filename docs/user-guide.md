# 使用指南

[返回项目首页](../README.md)

## 详细密钥配置

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

**4. 核对部署名称。** 当前 [agent.py](../GIS_agent/back_end/agent.py) 使用部署名 `gpt-5-mini` 和 API 版本 `2024-12-01-preview`。Azure 资源中必须存在对应部署；如果实际部署名称不同，需要将代码中的 `model="gpt-5-mini"` 改为实际部署名称。当前部署名和 API 版本没有通过 `.env` 配置，仅在 `.env` 添加同名配置项不会生效。

**5. 启动或重启后验证。** 完成配置后按[首页启动步骤](../README.md)启动系统。如果系统已经运行，先双击 `stop_geoai.bat`，再双击 `start_geoai.bat`，使后端重新读取配置。重启会清空临时会话和下载快照。打开页面后，发送下文的“行政区分类”示例，检查是否能完成 AI 工具调用并生成地图；仅能打开网页不代表密钥已经验证成功。

如果出现认证失败，请检查 Endpoint 与密钥是否复制完整、属于同一个资源，以及文件是否误存为 `.env.txt`；如果提示找不到部署，请核对部署名称。

`.env` 已被 Git 忽略，**不要上传真实密钥，也不要把密钥贴入聊天或截图**。提交到仓库的 `.env.example` 应始终只保留示例值。

## 分类使用示例

以下为基于当前工具实现的英文示例，不表示每条都已通过真实 AI 验收。独立实验可先清空会话；修改和叠加命令应接着上一张地图执行。

驾驶类示例必须先完成首页的路网准备。独立分析建议使用独立会话，避免沿用上一次的数据或图层。

### 基础制图

| 场景 | 英文命令 |
|---|---|
| 行政区分类 | `Show all 18 Hong Kong districts, colored by district name using tab20.` |
| 本地设施点 | `Use the built-in dataset to display ambulance depot locations.` |
| 数量统计 | `Count ambulance depots by district using the built-in dataset and map the counts.` |
| 密度分析 | `Calculate primary school density per square kilometre by district using the built-in dataset.` |

### 修改地图（接着上一张地图执行）

| 场景 | 英文命令 |
|---|---|
| 修改标题 | `Change the map title to "Hong Kong Facility Distribution".` |
| 修改配色 | `Keep the ambulance depot count analysis, but redraw it using Blues.` |
| 面图改点图 | `Replace the current polygon map with ambulance depot points from the built-in dataset.` |
| 点图改面图 | `Replace the point map with an ambulance depot count choropleth using the built-in dataset.` |
| 叠加图层 | `Overlay ambulance depot points on the current district map. Keep the district layer.` |
| 地图要素 | `Enable the north arrow, a 1 km scale bar, and dynamic corner coordinates.` |

### Excel 数据（先上传文件）

| 场景 | 英文命令 |
|---|---|
| 上传点显示 | `Display all uploaded data on the map.` |
| 上传点统计 | `Count all uploaded points by district and create a choropleth.` |
| 上传点密度 | `Calculate uploaded point density per square kilometre by district.` |

### CSDI 官方数据

| 场景 | 英文命令 |
|---|---|
| 动态数据发现 | `Search CSDI for badminton courts and show their locations in Hong Kong.` |
| 多份临时数据 | `Download CSDI public fitness rooms and ambulance depots. Keep both in this session.` |
| 刷新官方数据 | `Refresh the CSDI ambulance depots snapshot from the official source.` |

### 空间分析

| 场景 | 英文命令 |
|---|---|
| 坐标 Buffer | `Find ambulance depots within 500 metres of latitude 22.250370, longitude 114.173867, using the built-in dataset.` |
| 地名 Buffer | `Find primary schools within 2 km of Hong Kong Polytechnic University Block Z using the built-in dataset.` |
| 驾驶覆盖 | `Show 10-minute driving coverage FROM Aberdeen Ambulance Depot at 30 km/h using the built-in dataset.` |
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

- 后端获取官方目录并缓存 15 分钟，然后在数据集的中英文名称和机构字段中匹配关键词；关键词不会作为搜索参数发送给目录接口。空格分开的关键词必须全部命中，目前没有语义搜索或 AI 推荐。
- 选定数据集后，通过 WFS 检查图层、查询总数并分页下载 GeoJSON，再校验坐标、名称、唯一编号和记录完整性。最多导入 10,000 条记录。
- 当前通用适配仅支持单图层、可识别英文名称字段的香港 WGS84 点数据；目录有记录不代表一定可导入。
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

### 按步行或驾车距离查询

- `Find primary schools within 500 metres walking distance of Hong Kong Polytechnic University Block Z. Replace the current map.`
- `Find primary schools within 2 km driving distance of Hong Kong Polytechnic University Block Z.`

`network_distance_query` 通过官方地名接口解析起点，以 EPSG:2326 道路几何长度求有向最短距离，步行和驾车使用各自独立路网，不用驾驶分钟替代米数。首次准备步行路网运行 `python prepare_road_network.py --mode walk`；驾车仍为 `--mode drive`，不会覆盖另一种缓存。

阈值包含起点及设施到道路的直线接入距离，单端超过100米排除。这些接入线不代表已核实的入口或可通行路径；不处理实时封路、完整转向限制或校园开放时间。表格记录候选设施的路网距离及超限/不可达状态；地图显示匹配设施、起点及到匹配设施的最短道路路线（包含接入段），不用圆形缓冲冒充路网覆盖面。路线和点位按设施类型配色，提供独立路线图例。补轨迹或修复图例会整体更新当前范围结果，避免残留先前误加的全港设施层；失败保留旧图。

### 会话与当前限制

CSDI 搜索支持“消防站 / 消防局 / Fire Stations”和“图书馆 / library / libraries”，并处理常用设施英文单复数。医院、小学的 `Facility_Name` 名称字段也可导入；这不代表所有官方数据格式都已兼容。

同一官方数据源内的 `csdi_nearby` 查询默认排除起点自身（`exclude_origin=true`），缓冲区和驾驶模式一致；不会排除同坐标的其他要素。需要包含自身时可明确请求，例如：`Find fire stations within 500 m of Aberdeen Fire Station, including the origin itself.` 结果参数会记录是否排除以及排除数量，原始快照不变。

- 消息、地图、Excel 与 CSDI 快照按会话保存在单个后端进程内。Clear session 清除对应会话，重启后端清除所有临时数据。
- 普通落区工具的 Agent Schema 仅支持本地库和 Excel；不要将任意 CSDI 落区统计当作已完成能力。
- 暂不支持人口覆盖、公平性评价、最近设施路径、实时交通或任意格式数据导入。
- 底图、WFS、地名解析依赖外网；简洁矢量底图失败时保留提示，可单独重试或点击 `Use detailed OSM basemap`。不会在启动或切换预览时自动显示完整 OSM 底图。
- PNG 复用交互地图已排版的标题、图例、符号和地图整饰；不包含缩放按钮、临时提示和弹窗。请先等待底图加载完成，再导出。
- 结果表格默认收起，点击 `Show table` 或从 `Result list` 选择结果后查看。展开或拖动表格不会压缩地图，而是在地图下方滚动展示；不使用表格也可正常生成、预览和导出地图。
- 表格的地图坐标标为 `(map)`，相同的来源坐标不重复列出；存在差异的来源坐标保留并标明字段名。选择高亮不包含在 PNG 中。
- 完整质量报告展示、生产认证、限流与持久会话仍待完善。
- 工具失败会终止当前执行链；仅 AI 最后总结失败时，可返回已完成的 GIS 结果并附明确警告。
