# 高速公路通信工程光缆敷设施工智能验真 Demo

本目录保留气吹光缆和光纤熔接分析模块，不修改任何既有 API。

## 场景口径

- `scene`: `highway_communication_construction`
- `project_type`: `expressway_optical_cable_deployment`
- `construction_environment`: `高速公路通信基础设施施工现场`
- 工序：`equipment_setup`、`cable_loading`、`blowing_process`、`completion_check`
- 目标：`fiber_cable`、`blowing_machine`、`air_compressor`、`worker`、`cable_reel`、`safety_helmet`

## 运行

```bash
python demo_air_blowing/run_demo.py
python demo_air_blowing/run_fiber_splicing_demo.py
python demo_air_blowing/generate_reports.py
python demo_air_blowing/generate_full_process_report.py
```

输出：

- `demo_air_blowing/output/construction_evidence.json`
- `demo_air_blowing/output/fiber_splicing_evidence.json`
- `demo_air_blowing/output/fiber_splicing_metrics.json`
- `demo_air_blowing/output/full_process_summary.json`
- `demo_air_blowing/output/高速公路通信工程光缆施工全过程智能验真报告.md`
- `demo_air_blowing/output/cross_video_analysis.json`
- `demo_air_blowing/output/高速公路通信工程光缆敷设施工智能验真报告.md`
- `cross_scene_validation_report.md`
- `output/pdf/高速公路通信工程光缆敷设施工智能验真报告.pdf`
- `output/pdf/高速公路通信工程光缆施工全过程智能验真报告.pdf`

回归测试：

```bash
python -m pytest -q tests/test_air_blowing_analyzer.py
python -m pytest -q tests/test_fiber_splicing_analyzer.py
```

`air_blowing_analyzer.py` 还提供 `analyze_video_with_opencv()`，可对新视频按间隔抽帧；传入自定义 Ultralytics YOLO 权重后，可执行真实目标检测。通用 COCO 权重只能可靠映射 `person -> worker`，其余通信工程目标必须使用领域数据训练，不能用时间规则冒充检测结果。

随包两条公开视频的检测目标为人工抽样复核标注，工序标签由统一时序规则推断；它们用于 Demo 和小样本跨场景验证，不代表生产模型精度。

## 施工全过程展示

系统驾驶舱展示两条连续作业链：

- Air Blowing：设备布设、光缆上料、气吹敷设、完工检查。
- Fusion Splicing：光纤剥除、光纤清洁、光纤切割、光纤熔接、盘纤整理。

熔接样例未清晰展示 `splice_tray`，因此证据输出不会伪造该目标，报告将其列为补证项。
