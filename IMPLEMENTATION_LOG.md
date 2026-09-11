# 气吹光缆智能验真 Demo 修改与测试记录

## 步骤 1：建立隔离式扩展结构

- 修改文件：新增 `backend/app/air_blowing_analyzer.py`、`demo_air_blowing/`，未编辑 `backend/app/main.py`。
- 目的：以旁路模块承载新增 AI 能力，避免改变既有接口。
- 测试方法：计算原压缩包和工作副本 `backend/app/main.py` 的 SHA-256。
- 结果：两者均为 `d56c5708881b97b7c0d7938c5119d33876d82b8025057e3fe8f360b91f0a6621`，字节一致。

## 步骤 2：加入真实视频和抽帧测试数据

- 修改文件：新增 `demo_air_blowing/input/*.mp4`、`frames/BV1Ld4y1X7AA/*.png`、`frames/BV1u2Mv6METn/*.png`、`video_profiles.json`。
- 目的：构造测试集 A（高速公路通信工程现场）与测试集 B（硅芯管高速气吹）。
- 测试方法：检查两个视频文件、16 个目标抽帧均存在，并在生成证据时计算 SHA-256。
- 结果：2 段视频、16 帧全部可读且哈希复算一致。

## 步骤 3：实现施工阶段与风险推断

- 修改文件：`backend/app/air_blowing_analyzer.py`。
- 目的：支持 4 个工序、6 类目标、风险检测，以及工程对象—证据—验收规则关联。
- 测试方法：运行 `python -m pytest -q tests/test_air_blowing_analyzer.py`。
- 结果：`2 passed`；4 个阶段、6 类目标均覆盖，必需字段和规则编号均通过断言。

## 步骤 4：生成机器可读证据链

- 修改文件：新增 `demo_air_blowing/run_demo.py`，生成 `output/construction_evidence.json`。
- 测试方法：运行 `python demo_air_blowing/run_demo.py`，校验 JSON 可解析、16 条证据字段完整、帧与视频哈希一致。
- 结果：15/16 工序预测正确，总体准确率 93.75%。

## 步骤 5：完成跨场景验证和报告升级

- 修改文件：新增 `demo_air_blowing/generate_reports.py`、`cross_scene_validation_report.md`、`cross_video_analysis.json`、新版验真报告 Markdown/PDF。
- 目的：统一高速公路通信基础设施叙事，加入来源、逐帧结果、准确率、泛化、应用价值和效率估算。
- 测试方法：解析 Markdown 必需章节；使用 PDF 解析器检查标题和 3 页文本；将 PDF 逐页渲染为 PNG 人工检查。
- 结果：报告章节完整，无文字截断、重叠或中文字体异常。

## 步骤 6：既有功能回归

- 修改文件：无。
- 测试方法：FastAPI TestClient 调用健康、项目、汇总、对象、GIS、规则、证据、问题、Excel/PDF/ZIP 导出等 11 个既有读取/导出接口，并在测试前后执行数据重置。
- 结果：11 个接口及重置均返回 HTTP 200。完整旧测试中的视频上传路径需要 OpenCV；项目依赖已在 `backend/requirements.txt` 声明，但本次环境下载大包超时，未重复执行该项端到端测试。

## Demo 流程

1. 执行 `python demo_air_blowing/run_demo.py` 生成证据 JSON。
2. 执行 `python demo_air_blowing/generate_reports.py` 生成跨场景报告和验真报告。
3. 打开 `cross_scene_validation_report.md` 查看逐帧结果与泛化分析。
4. 打开 `output/pdf/高速公路通信工程光缆敷设施工智能验真报告.pdf` 进行比赛展示。
5. 如需分析新视频，调用 `analyze_video_with_opencv()` 并传入通信施工领域的 YOLO 权重；无权重时只进行抽帧和有限对象映射。

## 步骤 7：新增 Fiber Fusion Splicing 场景

- 修改文件：新增 `backend/app/fiber_splicing_analyzer.py`、`fiber_splicing_profile.json`、`run_fiber_splicing_demo.py`、`test_fiber_splicing_analyzer.py` 和熔接视频；修改 `backend/static/index.html`、`backend/static/app.js`，只增加全过程展示，不改变 API。
- 目的：识别 `fiber_stripping`、`fiber_cleaning`、`fiber_cleaving`、`fusion_splicing`、`fiber_organizing`，生成格式固定的 `fiber_splicing_evidence.json`。
- 测试方法：执行气吹与熔接共 4 个合同测试、JavaScript 语法检查、Python 编译检查；验证 JSON 每条记录只含 6 个约定字段。
- 结果：4/4 测试通过；9 条熔接证据覆盖 5 个阶段，当前抽样工序判断 9/9 正确。视频未清晰出现 `splice_tray`，已列为补证而非伪造检出。

## 步骤 8：生成光缆施工全过程报告

- 修改文件：新增 `generate_full_process_report.py`、`full_process_summary.json`、全过程报告 Markdown/PDF。
- 测试方法：PDF 文本解析、三页 Poppler 渲染人工检查、既有 11 个 API 与重置接口回归、原 `main.py` 哈希复核。
- 结果：全过程覆盖 Air Blowing + Fusion Splicing，共 3 段视频、25 条抽样证据、9 类工序；PDF 无截断或重叠，既有 API 全部返回 200，`main.py` 与原包字节一致。

## 步骤 9：融入核心业务模型

- 修改文件：`database.py`、新增 `ai_platform.py`和 `ai_routes.py`，`main.py` 只增加 router 挂载。
- 目的：实现 `Project → ConstructionTask → Evidence → AIAnalysisResult`，两类 AI 证据必须归属施工任务。
- 测试方法：运行融合测试并执行跨 5 表 JOIN。
- 结果：17 条 Evidence 与 17 条 AIAnalysisResult 均可追溯到项目和任务。

## 步骤 10：驾驶舱、API 与交付报告融合

- 修改文件：`backend/static/app.js`、`integrated_demo_flow.py`、`test_ai_platform_integration.py`、`SYSTEM_FUSION_REPORT.md`。
- 目的：首页动态展示四阶段任务，并从数据库生成项目级可信交付报告。
- 测试方法：5 项 pytest，11 个旧 API 合同检查，PDF 三页 Poppler 渲染人工验收。
- 结果：全部通过；任务状态为“完成/完成/完成/生成”，可生成通信基建施工数字化验真交付报告。
