# 施工目标检测训练

检测类别：吹缆机、光缆盘、熔接机。

数据来源为项目内三段施工视频。`reviewed_annotations.json` 保存人工复核框，数据集构建后每个样本在 `manifest.json` 中记录源视频、时间戳、工序、源视频哈希和影像哈希。

运行：

```cmd
04_BUILD_AND_TRAIN_YOLO.cmd
```

默认训练40轮。快速验证可运行：

```cmd
04_BUILD_AND_TRAIN_YOLO.cmd 5
```

输出：

- `datasets/construction_objects/`：YOLO格式训练集与验证集；
- `backend/models/construction_yolo.pt`：系统加载的最佳权重；
- `backend/models/training_summary.json`：真实训练参数与验证指标；
- `backend/models/training_runs/construction_objects/`：训练曲线和混淆矩阵。

当前数据集是竞赛演示小样本，只用于验证完整技术链。生产部署前必须补充不同施工队、设备型号、天气和拍摄角度的数据，并使用独立项目视频进行验收。

## 安全监管独立模型

安全监管使用项目同级目录的 `construction-ppe`，与通信施工目标检测使用完全独立的权重。

训练前只校验数据：

```cmd
.venv\Scripts\python.exe training\train_safety_yolo.py --check-only
```

快速建立 YOLOv8n 基线（默认 50 轮）：

```cmd
06_TRAIN_SAFETY_YOLO.cmd
```

先做 5 轮流程验证：

```cmd
06_TRAIN_SAFETY_YOLO.cmd 5
```

建立 YOLOv8s 对照基线：

```cmd
06_TRAIN_SAFETY_YOLO.cmd 50 yolov8s.pt
```

训练配置参考 `vamsiprasanth/constructionsafety` 的 YOLOv8 安全检测路线，使用 AdamW、640像素、早停和独立测试集评估；数据仍使用本地 `construction-ppe` 的原始11类定义，不混用参考仓库的10类编号。

训练输出：

- `backend/models/safety_ppe_yolo.pt`：安全监管独立权重；
- `backend/models/safety_ppe_training_summary.json`：数据审计、验证集指标和独立测试集指标；
- `backend/models/training_runs/safety_ppe_yolov8n/` 或 `safety_ppe_yolov8s/`：训练曲线、混淆矩阵和中间权重。

平台使用人员、安全帽、反光背心、未戴安全帽四类结果。只有模型明确检测到 `no_helmet` 时才生成安全违规，不以“没有检测到安全帽”反推违规。

## 新增施工视频处理与标注

`fd4737c5ce424df8061a4d8d2176d460.mp4` 固定为独立测试视频，其余五段作为训练候选。运行标注台：

```cmd
07_ANNOTATE_NEW_VIDEOS.cmd
```

浏览器打开 `http://127.0.0.1:8765`。候选类别只作提示，必须人工画框并保存。测试视频不会进入训练集或验证集；合并训练时运行 `training/build_video_training_dataset.py`，只有人工标注过的图片会被纳入。

全部283张复核完成后运行 `07B_FREEZE_VIDEO_DATASET.cmd`。冻结程序会校验每张图片的复核记录和YOLO标签，并生成 `frozen_split_manifest.json`；缺少任何一张都会拒绝冻结。

安全业务评测先在 `safety_business_ground_truth.csv` 填写116张测试图的事件真值，再运行 `08_EVALUATE_SAFETY_BUSINESS.cmd`。参赛证据归档运行 `09_BUILD_RELEASE_EVIDENCE.cmd`，缺失材料会进入 `release_evidence/data_manifest/missing_items.json`，不会自动伪造。
