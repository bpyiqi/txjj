# 系统增量升级报告

## 升级结果

系统已升级为“面向通信基建施工全过程的多源感知监管与数字化验真交付系统”。本次变更为增量升级，原有 API 路径、数据表及气吹光缆/光纤熔接分析逻辑均保留。

## 修改文件

| 文件 | 修改内容 |
|---|---|
| `backend/app/database.py` | 增量新增施工数据与轻量工程对象表，同步原工程对象 |
| `backend/app/management_routes.py` | 新增五层数据总览；扩展空间数据采集和真实交付记录查询 |
| `backend/app/video_sampling.py` | 增加 MP4 关键帧读取及缺少时长元数据时的顺序解码兜底 |
| `backend/app/main.py` | 挂载新路由；修复 OpenCV 在中文 Windows 路径下写入关键帧的兼容问题 |
| `backend/static/index.html` | 更新系统定位，新增数字交付中心导航 |
| `backend/static/app.js` | 串联工程生命周期、三类分析引擎状态和数字资产包流程 |
| `backend/static/ui-overrides.css` | 增加生命周期、采集类型、分析引擎和数字交付布局 |
| `self_check.py` | 系统自检前增量导入现有 GIS 设计数据，不重置用户业务数据 |
| `backend/data/seed.json` | 统一中文施工场景和数据集名称 |
| `tests/test_management_upgrade.py` | 新增采集、分析、统计、证据、对象和旧 API 兼容性测试 |
| 启动脚本、说明文档与报告生成器 | 清理旧品牌词、版本描述和英文页面说明 |

## 数据库增量

### `construction_data`

| 字段 | 作用 |
|---|---|
| `id` | 采集记录编号 |
| `task_id` | 关联施工任务 |
| `data_type` | 施工视频、现场图片、工程资料或空间数据 |
| `file_name` | 原文件名 |
| `file_path` | 本地存储路径 |
| `upload_time` | 上传时间 |
| `status` | 已采集或已分析 |

### `engineering_objects`

字段为 `id`、`name`、`type`、`location`、`status`。现有 `objects` 数据以原编号增量同步，任务、证据和验真结果仍通过原编号关联，无须迁移原表。

## 新增功能

1. 项目驾驶舱的施工任务、施工影像、影像分析和数字交付数量全部来自 SQLite 聚合查询。
2. 施工数据采集中心支持 MP4、图片、PDF、表格、GeoJSON 和 Shapefile 配套文件，上传时必须绑定项目和施工任务；GeoJSON 入库后直接同步工程对象和空间图层。
3. 已采集视频可调用现有气吹光缆或光纤熔接分析器；未匹配已复核样本时明确返回限制，不伪造检测结果。
4. 施工影像分析中心统一展示通信施工视觉检测、安全监管视觉检测、工程信息识别三个引擎；安全监管使用独立权重，没有权重时显示“等待训练”，结果数读取数据库，不生成虚假结论。
5. 新增 `construction-ppe` 数据体检与安全监管训练入口，训练完成后自动发布独立权重、验证集指标和测试集指标。
6. 智能验真工作台展示两类施工的九个阶段、证据完整性和真实风险记录。
7. 影像证据中心展示关键影像、视频来源、时间、施工阶段、任务、工程对象和验真状态。
8. 问题处置详情增加补证上传和重新验真入口；安全模型明确检测到未戴安全帽时自动形成“安全违规”问题。
9. 项目驾驶舱以真实数量串联设计数据导入、现场采集、影像分析、状态识别、智能验真、工程对象关联和数字交付。
10. 数字交付中心汇总项目、工程对象、施工过程、分析结果、影像证据和验真记录，可生成 PDF、Excel 与 ZIP 数字资产包。

## 新增 API

新接口均使用 `/api/management` 前缀：

- `GET /dashboard`
- `GET /projects`
- `GET /tasks`
- `GET|POST /construction-data`
- `POST /construction-data/{data_id}/analyze`
- `GET /analysis-tasks`
- `GET /verification-workbench`
- `GET /evidence`
- `GET /engineering-objects`
- `GET /platform-overview`

原有 `/api/project`、`/api/summary`、`/api/objects`、`/api/evidence`、`/api/issues`、`/api/exports/*` 和 `/api/ai/*` 均保留。

安全监管新增只读状态接口：`GET /api/ai/safety/status`。

## 测试结果

- `D:\python312\python.exe -m pytest -q`：`19 passed`，`2 warnings`（上游测试组件弃用提示）。
- 覆盖原有图片上传、视频抽帧、人工关联、规则复验、问题处置、Excel/PDF/ZIP 导出。
- 覆盖气吹光缆和光纤熔接现有分析器。
- 覆盖施工数据上传、任务绑定、影像分析、真实统计、证据关联和工程对象台账。
- 覆盖非内置哈希气吹视频：按施工任务类型调用既有分析器，生成关键影像、Evidence 和 AIAnalysisResult，不依赖模型权重。
- 覆盖缺少 FPS、总帧数和时长元数据的 MP4：自动切换为顺序解码抽帧，不再因时长元数据缺失而中断。
- 新增 GeoJSON 上传、解析、工程对象入库与查询的端到端测试。
- `construction-ppe` 数据体检：1416 张图、11614 个有效标注框，训练/验证/测试为 1132/143/141 张。
- `01_CHECK_SYSTEM.cmd`：退出码 `0`；626 个工程对象、57 条影像证据、15 条规则、GIS 图层及 Excel/PDF/ZIP 交付均通过。
- 测试仅有 Starlette TestClient 的上游弃用警告，不影响当前功能。

## 运行方法

```bash
python run.py
```

浏览器进入项目驾驶舱，从“施工数据采集中心”选择项目和施工任务，上传已复核的气吹光缆或光纤熔接视频，然后点击“开始影像分析”。
