# CSDI 多数据源稳定性验收

日期：2026-09-07。测试使用真实官方 WFS，未修改本地设施数据库或业务代码。

> 下文为修复前的测试记录。随后已按用户要求修改业务代码，修复与复测结果见文末；保留原始失败记录供对照。

## 范围与结论

覆盖 README 中适用于 CSDI 的目录发现、下载、刷新、点图、标题修改、跨源 Buffer、跨源驾驶分析，并增加四源叠加、缓存重复读取和 PNG 导出。README 的内置库/Excel 示例不应偷换成 CSDI：当前普通聚合工具的 Agent Schema 没有开放任意 CSDI ID，因此本轮不宣称这些示例也已用 WFS 全部通过。

结论：**临时多数据集和底层 GIS 工具可工作，但网络稳定性、Agent 多图层执行与视觉区分仍存在缺陷。不能据此认定生产级稳定。**

## 真实数据与耗时

| 数据源 | 最终有效点数 | 首次下载 | 第二轮显式 refresh |
|---|---:|---:|---:|
| Badminton Courts | 116 | 55.47 秒，含一次超时回退 | 18.34 秒 |
| Swimming Pools | 46 | 60.12 秒，三次超时后失败 | 39.25 秒，成功（此前没有该快照） |
| Public Fitness Rooms | 80 | 20.67 秒 | 19.30 秒 |
| Ambulance Depots | 45 | 1.22 秒 | 37.66 秒，含一次超时回退 |

共 287 条记录，不等于 287 个不重复地点；体育馆可能同时提供健身室和羽毛球场。羽毛球场所记录数不等于独立球场片数。

目录首次获取 6.76 秒，包含 1,149 条条目，随后搜索命中目录缓存。本轮四份数据最终同时留在测试会话内存；非泳池三份数据刷新前后 SHA256 一致，泳池首轮失败所以不能比较两轮哈希。

## 自动化实网结果

运行 `GIS_agent/back_end/tests/manual_csdi_stability.py`，总计 282.36 秒：

- 16 项检查，15 项通过、1 项失败；退出码 1 如实标记泳池首次下载失败。
- 8 次数据下载/刷新操作中 7 次成功；不是“第一次全部成功”。
- 23 次 HTTP 请求尝试，其中 5 次超时。该小样本仅描述本轮，不是长期可用率。
- 20 次缓存读取全部成功，没有新增 HTTP 请求。
- 四图层数据栈与 JSON 序列化通过：116 + 46 + 80 + 45 点，约 464 KB 序列化载荷。
- 500 米 Buffer：东昌街体育馆周边救护站 0 个。
- 从东昌街体育馆出发，30 km/h 恒速、5 分钟驾驶：1 个救护站；可达道路约 70.547 km，445 个可达节点。
- 分析后重新构建四源图层通过，数据快照未丢失。
- 独立状态初始化为空；**模拟**刷新网络故障后旧快照全部保留。该项不是实际并发压力测试。

原始请求耗时和断言输出见 [JSONL 日志](csdi-stability-2026-09-07.jsonl)。

## 浏览器与真实 AI 验收

在 `http://localhost:5173/` 的独立测试标签页执行：

| 请求 / 操作 | 观察 |
|---|---|
| `Search CSDI for badminton courts and show their locations in Hong Kong.` | 成功发现、下载并显示 116 点 |
| `Download CSDI public fitness rooms and ambulance depots. Keep both in this session.` | 数据确实保留；但 Agent 调用了 csdi_map 而非只下载，导致原图被替换 |
| 搜索泳池并要求保留四份数据、显示四层 | 缓存达到四份；地图实际只显示救护站和泳池两层，AI 却声称四层都已显示 |
| 明确逐个 csdi_map、replace_existing=false，再改标题 | 四个工具调用执行后，图例实际包含四类，标题修改成功 |
| Export preview → Interactive map | PNG 成功生成；返回后四个图例仍存在 |
| README 的 CSDI 500 米查询 | 实际返回 0；四份缓存仍保留 |
| README 的 CSDI 5 分钟车程查询 | 实际返回 1：Tai Po Ambulance Depot；地图含道路、覆盖区、起点和目标，四份缓存仍保留 |
| 刷新救护站后用“先 replace=true，再 false”重建 point map | 刷新成功；四次制图日志成功但最后只剩泳池，定位到参数归一化覆盖（见下） |

图层恢复复现指令：

> Explicitly call csdi_map for each cached dataset with replace_existing=false: csdi_auto_lcsd_rcd_1629267205214_38344, csdi_fitness_rooms, csdi_ambulance_depots, csdi_auto_lcsd_rcd_1634540558875_77434. Then change the title to "Hong Kong Public Facilities - Four CSDI Sources".

这些 ID 是本轮官方目录实际返回的 ID，不应推广为让 AI 自行拼接任意 ID。

## 发现的问题（未在本轮修改业务代码）

**新增可复现 P1 根因：`agent.py::_normalize_map_arguments` 错误覆盖每次工具调用的替换参数。** 包含 `point map` 且没有独立 `overlay/add/superimpose` 关键词的整段请求，会触发 `GEOMETRY_SWITCH_REFERENCE`，把所有 MAP_LAYER_TOOLS 的 replace_existing 都强制设为 True。实测将 `{'dataset_id': 'csdi_fitness_rooms', 'replace_existing': False}` 传入该函数，返回 True。即便模型正确提交“第一层 true、后续 false”，地图也只剩最后一层。应优先修复逐工具调用语义，而不是只修改提示词。临时绕开方式是明确写独立的 `Overlay` 关键词；这不是正式修复。

1. **P1：多图层漏执行且总结错误。** 数据缓存与地图栈不是同一状态，Agent 未将缺失层补绘，却报告四层成功。依据：`agent.py::_update_web_layer_stack` / `_compact_tool_result`，以及上述实际日志。建议在返回成功前校验请求图层与真实 `web_layers`，向模型提供当前已绘制层清单。
2. **P1：四类设施符号同色。** 四层都显示红点，重叠点很难识别。依据：`tools/csdi_tools.py::csdi_map` 没有 cmap 参数，调用 `layer_styles.py::add_points_layer` 使用默认 Set1；每个单类别层取相同起始颜色。建议按稳定 dataset ID 分配不同颜色，并增加 CSDI 图层样式参数。
3. **P1：网络故障误报不兼容。** 泳池首次三次超时被包装成“no accessible compatible WFS”，下一轮却成功。依据：`tools/csdi_sources.py::resolve_source` 的宽泛异常包装。建议区分网络超时、无服务、格式不支持三种状态，保留可重试标志。
4. **P2：只下载请求改变地图。** AI 调用 csdi_map 导致图层替换。建议明确 download-only 意图约束，并加入多轮真实 Agent 回归测试。
5. **P2：能力说明失真。** AI 推荐尚未通过 Schema 开放的 CSDI 落区聚合，还曾说 export 不可用，而 UI PNG 导出成功。依据：浏览器最终总结、`agent_schemas/tools_definition.py`、`src/App.jsx`。建议基于实际能力与地图状态生成简短总结。
6. **P2：多图层标题/图例表达不足。** 自动标题只引用最后一层；四张重复的 Facility type 图例占空间，窄窗中明显遮挡；交互标题换行，而 PNG 长标题被单行缩放。依据：`src/mapPresentation.js::resolveMapHeading`、`src/mapExport.js::drawMapHeading` 及截图观察。
7. **外部依赖波动：** Buffer 地图出现 OpenFreeMap 瓦片 502，前端明确回退 OSM，空间统计仍成功。不能把底图失败误判为 WFS 或分析失败。

本轮常规后端回归测试 76 项仍全部通过，说明上述多轮 Agent/参数归一化组合场景未被现有测试充分覆盖。

## 重跑

```powershell
cd D:\geoAI\GIS_agent\back_end
.\.venv\Scripts\python.exe -u tests/manual_csdi_stability.py
```

需要官方网络和已准备好的本地路网；脚本不调用模型、不写设施数据文件。输出到标准输出，测试会话随进程结束释放。浏览器验收另行通过 UI 操作真实 Agent。建议后续再做多时段重复测试和多会话并发测试，不用本轮的小样本替代稳定性基准。

## 四项问题修复后复测（同日）

- 网络：使用线程独立的直连/代理连接池，成功线路复用 120 秒，0.5/1 秒退避，最多三次请求，连接/读取超时 30/45 秒；GetCapabilities 成功结果缓存 15 分钟。网络异常与不兼容格式分别报告，旧快照仍在完整校验成功后才替换。
- 图层：`agent.py::_normalize_map_arguments` 保留明确的逐次 replace_existing 布尔参数，不再用整句话的正则强制覆盖。
- 结果真实性：执行工具后把真实地图栈摘要传回模型；CSDI 最终回复由后端按实际显示层和缓存数生成。对明确请求的缓存数据图层检查缺失，缺失返回 INCOMPLETE_MAP_LAYERS，而不是采信模型“全已显示”的说法。新增模拟模型假报四层的回归测试。
- 配色：`csdi_map` 按数据集 ID 分配并保留会话颜色，优先选用尚未使用的八色集合；支持显式 color。四类点测试全部不同，重绘不变。超过八个图层仍可能复用颜色，不声称无限类别自动区分。

最终版真实 WFS 测试：**16/16 项通过，总耗时 77.02 秒**；20 次请求尝试中 1 次目录直连超时，代理回退成功，其后请求复用代理线路。四次首次数据下载耗时分别为羽毛球 2.99 秒、泳池 3.23 秒、健身室 1.55 秒、救护站 0.39 秒（不包含此前目录发现的 43.19 秒）。缓存读取无新增网络请求，四源合计 287 点，Buffer 0、驾驶 1 的结果不变。

四图层实际返回颜色：羽毛球 #d97706、泳池 #9333ea、健身室 #475569、救护站 #be185d。82 项后端单元/回归测试全部通过。与修复前的 282.36 秒相比，本轮更快且所有检查通过，但仅是小样本，不能归因全部为代码优化或推断长期 SLA。

本轮修复后验证为真实 WFS + GIS 工具链及模拟 Agent 回归；未在旧运行后端上冒充新代码的浏览器验收。重启后端加载修改会清空现有内存快照；需重新下载并生成地图才能看到新配色。
