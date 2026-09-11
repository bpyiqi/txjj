# 通信基建施工透明化管理系统架构分析

> 扫描对象：当前项目工作副本。原有 API 与新增管理模块均纳入分析。

## 1. 完整目录结构

```text
项目根目录/
├─ backend/
│  ├─ __init__.py
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py                       # FastAPI 应用及全部既有 API
│  │  ├─ database.py                   # SQLite 建表、连接与种子初始化
│  │  ├─ engine.py                     # 对象匹配、规则验真、问题同步
│  │  ├─ exports.py                    # Excel/PDF/ZIP 可信交付物生成
│  │  └─ air_blowing_analyzer.py       # 新增：独立气吹光缆 AI/规则分析器
│  │  └─ fiber_splicing_analyzer.py     # 新增：独立光纤熔接工序分析器
│  ├─ assets/
│  │  ├─ README.txt
│  │  ├─ raw/                          # 31 张原始现场图片（IMG_*.jpg）
│  │  └─ roi/                          # 12 张端口 ROI 图片（ROI_PORT_*.jpg）
│  ├─ data/
│  │  ├─ seed.json
│  │  ├─ verification.db
│  │  └─ source_tables/
│  │     ├─ engineering_objects.xlsx
│  │     ├─ evidence_table.xlsx
│  │     ├─ verification_results.xlsx
│  │     └─ verification_rules.xlsx
│  ├─ static/
│  │  ├─ index.html
│  │  ├─ app.js
│  │  └─ styles.css
│  └─ requirements.txt
├─ demo_air_blowing/                   # 新增：跨场景智能验真 Demo
│  ├─ input/
│  │  ├─ BV1Ld4y1X7AA.mp4
│  │  └─ BV1u2Mv6METn.mp4
│  │  └─ BV1k5411P7qE.mp4
│  ├─ frames/
│  │  ├─ BV1Ld4y1X7AA/                 # 2–16 秒，共 8 帧
│  │  └─ BV1u2Mv6METn/                 # 0–21 秒，共 8 帧
│  ├─ output/
│  │  ├─ construction_evidence.json
│  │  ├─ cross_video_analysis.json
│  │  ├─ fiber_splicing_evidence.json
│  │  ├─ fiber_splicing_metrics.json
│  │  ├─ full_process_summary.json
│  │  └─ 高速公路通信工程光缆敷设施工智能验真报告.md
│  │  └─ 高速公路通信工程光缆施工全过程智能验真报告.md
│  ├─ video_profiles.json
│  ├─ fiber_splicing_profile.json
│  ├─ run_demo.py
│  ├─ run_fiber_splicing_demo.py
│  ├─ generate_reports.py
│  ├─ generate_full_process_report.py
│  ├─ range_server.py
│  ├─ preview_b.html
│  └─ README.md
├─ demo_upload/
│  ├─ PBO-JAD-MAR-0008_site_inspection.mp4
│  └─ PBO-JAD-MAR-0021_site_overview.jpg
├─ docs/                               # 项目文档目录
├─ output/pdf/
│  └─ 高速公路通信工程光缆敷设施工智能验真报告.pdf
│  └─ 高速公路通信工程光缆施工全过程智能验真报告.pdf
├─ sample_exports/
│  ├─ verification_export.xlsx
│  ├─ verification_report.pdf
│  └─ digital_delivery_archive.zip
├─ tests/
│  ├─ test_api.py
│  └─ test_air_blowing_analyzer.py
│  └─ test_fiber_splicing_analyzer.py
├─ 01_CHECK_SYSTEM.cmd
├─ 02_START_DEMO_RESET.cmd
├─ 03_START_KEEP_DATA.cmd
├─ reset_and_start_windows.bat
├─ reset_and_start_linux_mac.sh
├─ start_windows.bat
├─ start_linux_mac.sh
├─ self_check_windows.bat
├─ self_check_linux_mac.sh
├─ bootstrap_windows.py
├─ self_check.py
├─ run.py
├─ README_RUN_CN.md
├─ DEMO_SCRIPT_CN.md
├─ TECHNICAL_ARCHITECTURE.md
├─ SYSTEM_ACCEPTANCE_REPORT.md
├─ RELEASE_NOTES.md
├─ CHECKSUMS.sha256
├─ VERSION
├─ cross_scene_validation_report.md
└─ architecture_analysis.md
```

运行后可能出现 `__pycache__/`、`.pytest_cache/`、`backend/uploads/` 和 `tmp/`，均为缓存、上传或质检中间目录，不属于源代码。

## 2. 前后端架构

系统是轻量单体 Web 应用，没有 Node 构建链：浏览器直接加载原生 HTML/CSS/JavaScript，调用同源 FastAPI；FastAPI 使用 SQLite 持久化，并由规则引擎计算对象验真状态。`run.py` 负责端口选择、可选数据重置、启动 Uvicorn 和打开浏览器。

```text
Browser SPA (backend/static)
        │ JSON / multipart / file download
        ▼
FastAPI (backend/app/main.py)
   ├─ SQLite repository (database.py → verification.db)
   ├─ verification engine (engine.py)
   ├─ export service (exports.py)
   ├─ uploaded image/video sampling (OpenCV)
   └─ AI verification service (ai_routes.py → ai_platform.py)
          ├─ Air Blowing analyzer
          ├─ Fusion Splicing analyzer
          └─ Project → ConstructionTask → Evidence → AIAnalysisResult
```

### 前端

- `index.html` 提供单页壳体、导航、抽屉与弹窗容器。
- `app.js` 使用 hash route 渲染仪表盘、GIS、证据中心、对象台账和问题中心；使用 `fetch` 调用 `/api/*`。
- `styles.css` 提供无框架响应式样式。
- GIS 为浏览器端 SVG 投影绘制，并非外部地图 SDK。

### 后端

- `main.py`：请求模型、查询编排、上传处理、静态文件挂载及 API 路由。
- `database.py`：SQLite schema、事务上下文、`seed.json` 初始化。
- `engine.py`：证据类型推断、编码/空间候选匹配、完整率计算、规则重验与问题闭环同步。
- `exports.py`：使用 XlsxWriter、ReportLab 和 ZIP 生成交付物。
- `air_blowing_analyzer.py`：不挂接旧 API，独立执行真实视频抽帧证据的目标—时序规则推断；新视频可选 OpenCV + 自定义 YOLO 权重。
- `fiber_splicing_analyzer.py`：同样不挂接旧 API，识别剥纤、清洁、切割、熔接与盘纤整理，并生成独立证据哈希。
- `ai_platform.py`：将两个分析器纳入工程任务、旧 `evidence` 表、AI 结果、风险和可信交付报告闭环。
- `ai_routes.py`：只新增 `/api/ai/*` 路由，旧 API 路径与响应契约不变。

## 3. 数据库模型

SQLite 文件为 `backend/data/verification.db`，核心表如下：

| 表 | 主键 | 职责 | 关键关系 |
|---|---|---|---|
| `project` | `project_id` | 项目、场景、流程、治理元数据 | 顶层配置 |
| `objects` | `object_id` | 通信工程对象及 GIS/设计属性 | 被证据、结果、问题引用 |
| `gis_features` | `(feature_id, layer)` | 线路、站点、设施几何 | 前端 GIS 展示 |
| `rules` | `rule_id` | 对象类型、工序、必需证据和验收逻辑 | 被问题引用 |
| `evidence` | `evidence_id` | 图片/视频证据、OCR、定位、置信度 | `linked_object_id → objects` |
| `verification_results` | `object_id` | 必需/已匹配数、完整率和状态 | `object_id → objects` |
| `issues` | `issue_id` | 缺失、异常、责任人和整改闭环 | 对象/证据/规则三外键 |
| `activities` | 自增 ID | 操作与验真活动审计 | 可关联对象和证据 |
| `construction_tasks` | `task_id` | 项目施工任务与流程状态 | `project_id → project` |
| `construction_task_evidence` | `(task_id, evidence_id)` | 任务—证据关联及时间戳/哈希 | 双外键连接任务与旧证据表 |
| `ai_analysis_results` | `analysis_id` | 工序、目标、置信度、风险、规则与复核状态 | 关联任务和证据 |
| `ai_delivery_reports` | `report_id` | 项目级可信交付报告及 SHA-256 | `project_id → project` |

JSON 字段使用 TEXT 保存：`workflow_json`、`governance_json`、`attributes_json`、`coordinates_json`、`properties_json`。

## 4. 关键业务模块定位

### 工程对象模块

- 数据模型：`database.py` 的 `objects`、`verification_results`。
- 服务入口：`GET /api/objects`、`GET /api/objects/{object_id}`、`POST /api/objects/{object_id}/reverify`。
- 规则计算：`engine.py::recompute_object()`，按对象类型加载强制规则并匹配证据。
- 展示：`app.js::renderLedger()`、`openObjectLedger()`、`openMapObject()`。

### 视频/图片处理模块

- 既有图片上传：`POST /api/evidence/upload`，完成文件保存、类型/编码推断、候选对象匹配。
- 既有视频上传：`POST /api/evidence/upload-video`，OpenCV 按 2 秒间隔抽帧，上限 900 帧，并形成证据记录。
- 新增气吹 Demo：`air_blowing_analyzer.py::analyze_profiles()` 和 `analyze_video_with_opencv()`；目标域包含光缆、吹缆机、空压机、人员、光缆盘、安全帽。
- 静态素材：`backend/assets/raw`、`backend/assets/roi`；运行上传：`backend/uploads`。

### 验收规则模块

- 规则定义：`rules` 表，包含工序、必需证据、强制性、顺序、来源文件和验收逻辑。
- 核心引擎：`engine.py::recompute_object()`、`sync_issues_for_object()`、`synchronize_all()`。
- 新增气吹规则：`air_blowing_analyzer.py::ACCEPTANCE_RULES`，将四个施工阶段映射到 `EXP-FOC-001` 至 `EXP-FOC-004`，每条证据同时带工程对象和验收规则。

### 报告生成模块

- 原系统：`exports.py::build_excel()`、`build_pdf()`、`build_archive()`。
- 新 Demo：`generate_reports.py` 生成 `cross_scene_validation_report.md`、验真报告 Markdown、PDF 及机器可读跨视频指标 JSON。

## 5. API 接口清单

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/project` | 项目元数据 |
| GET | `/api/summary` | 仪表盘汇总 |
| GET | `/api/objects` | 对象列表、状态/搜索筛选 |
| GET | `/api/objects/{object_id}` | 对象、时间轴、规则、证据、问题详情 |
| POST | `/api/objects/{object_id}/reverify` | 重新执行对象验真 |
| GET | `/api/gis` | GIS 要素 |
| GET | `/api/rules` | 验收规则列表 |
| GET | `/api/evidence` | 证据列表与筛选 |
| GET | `/api/evidence/{evidence_id}` | 证据与候选对象详情 |
| POST | `/api/evidence/candidates` | 获取候选关联对象 |
| POST | `/api/evidence/upload` | 上传图片/文档证据 |
| POST | `/api/evidence/upload-video` | 上传视频并抽帧入库 |
| POST | `/api/evidence/{evidence_id}/confirm-link` | 人工确认证据—对象关联 |
| GET | `/api/issues` | 问题列表与筛选 |
| PATCH | `/api/issues/{issue_id}` | 更新处置状态、责任人、期限和记录 |
| GET | `/api/exports/excel` | 下载 Excel 台账 |
| GET | `/api/exports/pdf` | 下载验真 PDF |
| GET | `/api/exports/archive` | 下载可信交付 ZIP |
| POST | `/api/admin/reset` | 恢复标准演示数据 |

新增 AI 验真接口使用独立命名空间，因此上述既有接口契约和路径保持不变：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/ai/dashboard` | AI 驾驶舱项目、任务、证据、结果和风险统计 |
| POST | `/api/ai/projects` | 创建通信基建工程项目 |
| POST | `/api/ai/tasks` | 创建施工任务 |
| GET | `/api/ai/projects/{project_id}/tasks` | 查询项目任务流 |
| GET | `/api/ai/tasks/{task_id}` | 查询任务、证据和 AI 结果 |
| POST | `/api/ai/tasks/{task_id}/upload-video` | 向具体施工任务上传视频 |
| POST | `/api/ai/tasks/{task_id}/analyze` | 执行气吹或熔接 AI 分析并入证据链 |
| POST | `/api/ai/tasks/{task_id}/complete` | 完成人工复核/任务验真 |
| POST | `/api/ai/projects/{project_id}/deliver` | 生成项目级可信交付报告 |
| GET | `/api/ai/projects/{project_id}/report.pdf` | 下载已生成报告 |

## 6. 架构结论与风险

- 优点：单机可运行、依赖少、数据与规则透明、工程对象—证据—规则—问题链路完整，适合比赛离线演示。
- 当前 AI 边界：随包两视频使用人工复核的领域目标标注驱动时间规则；通用新视频只有配置自定义 YOLO 权重后才能识别全部六类领域对象。
- 数据规模边界：跨场景准确率来自 2 段视频、16 个抽帧，不能外推为生产精度。
- 工序模型风险：短视频剪辑可能发生工序回切，固定时间先验会造成后段误判；需要连续帧投票和状态转移模型。
- 交付可信性：帧与视频均保存 SHA-256，风险保持人工复核状态；仍需把操作者、签名、时间源和归档策略接入实际项目治理。
