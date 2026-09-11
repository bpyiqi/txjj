# GIS 增量融合说明

本版本将 `latest_design.geojson` 作为通信工程对象的空间底座，接入现有的施工任务、视频分析、证据和验真链路。没有复制第二套数据库，也没有替换现有的气吹、熔接和 YOLO 分析模块。

## 数据链路

```text
latest_design.geojson
        |
        v
objects + gis_features
        |
        +--> engineering_objects 台账视图
        |
        +--> evidence.linked_object_id
        |
        +--> construction_tasks.linked_object_id
        |
        v
施工视频 -> AI 分析 -> 证据 -> 对象验真 -> 空间化交付
```

## 已实现内容

- `backend/app/gis_importer.py`：解析 GeoJSON，写入现有 `objects` 和 `gis_features` 表。
- `backend/data/gis/latest_design.geojson`：当前项目的 629 个设计要素。
- 启动时自动导入，按 SHA-256 判断是否需要重复导入，重复启动不会重复插入。
- 新导入对象自动建立初始的“缺失影像”验真状态，实际补证或重新验真时仍由原规则引擎计算。
- `/api/management/engineering-objects` 返回图层、几何类型、经纬度、设计属性和 GeoJSON 几何。
- `/api/management/gis/status` 查看导入状态；`POST /api/management/gis/import` 手动重新导入。
- 工程对象台账增加离线 GIS 空间视图，设计线、设计点和对象验真状态可以联动查看。

## 运行方式

```powershell
cd <项目目录>
python run.py
```

打开运行日志给出的地址，进入“工程对象台账”。点击地图对象或表格对象，可以继续查看任务、证据、工序和问题。

## 设计取舍

空间数据的权威来源使用已有的 `objects` 和 `gis_features`，`engineering_objects` 继续作为管理台账视图。这样可以避免同时维护两套坐标和几何字段，也能保持现有证据外键、施工任务外键和 AI 分析接口不变。
