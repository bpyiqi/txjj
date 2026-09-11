# 通信基建施工透明化管理系统技术架构

- 前端：本地HTML/CSS/JavaScript单页工作台。
- API：FastAPI。
- 数据库：SQLite。
- GIS：对象点、CABLE/PTECH/SITE/基础设施图层。
- 视频：OpenCV读取MP4，从0秒起每隔2秒提取JPEG关键帧。
- 证据：照片、PDF和video_frame统一写入evidence表。
- 验真：5条强制规则计算对象完整率，15条规则可追溯到规范章节。
- 问题：影像缺失、工序缺失、编码未匹配、对象未关联、完整率不足、缺少测试/报告、节点顺序异常。
- 导出：Excel、PDF和ZIP数字交付档案。
