# 通信基建施工透明化管理与数字化验真交付系统

## 1. 系统定位

系统将 GIS 设计对象、施工规范、照片/PDF/MP4、验真规则、问题处置和数字交付档案连接为完整闭环：

设计对象 → 施工规则 → 现场影像 → 对象验真 → 问题预警 → 数字交付档案

系统包含工程总览、地图验真、影像证据、对象验真台账和问题清单五个页面。

## 2. MP4 视频抽帧

- 支持上传一个 MP4 文件；
- 从 00:00:00 开始，每隔 2 秒抽取 1 帧；
- 原视频保存在 `backend/uploads/videos/`；
- 关键帧保存在 `backend/uploads/video_frames/`；
- 每个关键帧作为独立 evidence 记录写入 SQLite；
- `media_type` 固定为 `video_frame`；
- 初始状态为“待确认”，可逐帧人工确认关联对象；
- 关联确认后自动触发对象复验和问题同步。

演示视频：`demo_upload/PBO-JAD-MAR-0008_site_inspection.mp4`。该视频时长10秒，可生成5个关键帧。

## 3. Windows 启动

建议完整解压到英文短路径，例如：

`D:\communication_construction`

不要在压缩包预览窗口内直接运行。

1. 双击 `01_CHECK_SYSTEM.cmd`，确认全部项目显示 `[PASS]`。
2. 双击 `02_START_DEMO_RESET.cmd`，恢复标准数据并启动。
3. 需要保留上次上传和处置记录时，双击 `03_START_KEEP_DATA.cmd`。

首次运行会自动创建项目专用的 `.venv` 虚拟环境，并根据
`backend/requirements-windows.txt` 安装依赖。Windows 使用已验证的 CPU 版
PyTorch 组合，避免污染现有 Anaconda 环境或触发 `c10.dll` 加载错误。

如需在 PowerShell 中手动启动，请使用：

```powershell
& .\.venv\Scripts\python.exe run.py
```

## 4. Linux / macOS

```bash
python -m pip install -r backend/requirements.txt
python run.py --reset
```

## 5. 视频抽帧操作

1. 进入“影像证据中心”。
2. 点击“视频抽帧”。
3. 选择 MP4，可选填证据类型和已知工程编码。
4. 点击“上传并抽帧”。
5. 系统展示视频时长、2秒间隔和生成帧数。
6. 点击任一关键帧，查看候选对象及评分依据。
7. 点击“确认关联”，写入对象关系并触发复验。

## 6. 验证与自检

```bash
python self_check.py
python -m pytest -q
```

自检覆盖：30个工程对象、57条初始证据、15条规则、GIS图层、问题引擎、MP4解码、Excel/PDF/ZIP导出。

## 7. 数据与报告

- `backend/data/source_tables/`：初始四张业务表；
- `验真规则来源说明.xlsx`：15条规则的来源章节与转化理由（位于最终提交材料包）；
- `验证报告_初稿.docx`：四项实验及视频功能验证；
- `对比实验数据及支撑材料.xlsx`：人工标注明细、计算口径和自动档案生成耗时。

## 8. 重要口径

系统候选匹配属于可解释建议，只有人工确认后才写入 `linked_object_id`。在缺少对象级编码、定位或同项目证据时，系统不应被表述为已完成真实自动匹配。

## 9. AI 施工验真融合 Demo

气吹光缆和光纤熔接已纳入核心数据链。执行：

```bash
python demo_air_blowing/integrated_demo_flow.py
```

脚本会完成创建项目、创建四个任务、上传两类视频、AI 分析、证据入库、验真和报告交付。运行 `python run.py` 后，首页“AI 施工智能验真”模块会读取同一 SQLite 数据库的项目与任务状态。

完整变更、API 和测试结果见 `SYSTEM_FUSION_REPORT.md`。
