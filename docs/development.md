# 开发与验证

[返回项目首页](../README.md)

## 手动启动

在两个终端分别运行（以下以项目位于 `D:\geoAI` 为例）：

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

2026-09-08 上传前验证：92 个后端测试、16 个前端地图表达测试全部通过，前端 lint 和 build 通过。这些测试涵盖状态隔离、上传、质量检查、空间分析、路网方向和 CSDI 容错，不代表 100% 代码覆盖。测试不调用真实 Azure OpenAI。

手动联网检查 CSDI 可运行后端 `tests/manual_csdi_probe.py`。浏览器验收重点：数量/密度单位、图层替换、标题和图例同步、切换/导出一致性、超时失败提示及两个独立会话的数据隔离。

真实 WFS 测试与真实 AI 浏览器验收的范围不同，详见 [2026-09-07 CSDI 验收记录](csdi-stability-report-2026-09-07.md)。修复后的 WFS 工具链为 16/16 通过；该记录未宣称修复后所有真实 AI 浏览器场景均已重验。最新 10 条真实 AI 请求、导出结果及 CSDI 响应处理修复见 [2026-09-08 地图验收记录](map-ui-acceptance-2026-09-08.md)：8 条通过，2 条因官方服务故障未完成制图。
