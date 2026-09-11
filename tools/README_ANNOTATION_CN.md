# 扩展 YOLO 标注与训练

新增数据集共有 527 张精选图片：

- 气吹施工 300 张；
- 光纤熔接 120 张；
- 接头盒/手井 107 张。

图片没有边界框标注，`suggested_classes` 只作提示，不能直接训练。

## 标注

也可以直接双击项目根目录的 `05_START_ANNOTATION.cmd`。启动窗口必须保持打开。

在项目根目录执行：

```powershell
cd D:\GIS\new\VeriBuild_AirBlowing_Demo
.\.venv\Scripts\python.exe training\prepare_expanded_dataset.py
.\.venv\Scripts\python.exe tools\annotation_server.py
```

浏览器打开 `http://127.0.0.1:8765`，按以下原则标注：

1. 只框选画面中真实可见且轮廓相对清晰的目标；
2. 同一张图中多个目标分别画框；
3. 看不清或无法区分的目标不要强行标注；
4. 先完成至少 30 张图片、50 个框，再开始第一次训练；
5. 训练前运行标签检查。

## 检查和训练

```powershell
.\.venv\Scripts\python.exe training\validate_expanded_labels.py
.\.venv\Scripts\python.exe training\train_expanded_yolo.py --epochs 50 --batch 4 --workers 0
```

训练结果会写入 `backend/models/construction_yolo_expanded.pt`，在独立验证通过前不会自动覆盖原来的 `construction_yolo.pt`。

## 类别

统一类别为：`blowing_machine`、`cable_reel`、`air_compressor`、`fiber_cable`、`worker`、`fusion_splicer`、`fiber`、`splice_tray`、`splice_closure`、`manhole`。

气吹数据集的原视频授权信息目前未提供，正式参赛或公开发布前应补充授权说明；熔接数据集记录为 CC0，接头盒数据集仍需确认来源许可。
