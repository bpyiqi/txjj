# VeriBuild 2.2.0 Release Notes

## 新增

- MP4上传接口 `/api/evidence/upload-video`；
- 固定2秒间隔关键帧提取；
- 原视频和关键帧分目录存储；
- 关键帧自动写入 evidence 表，`media_type=video_frame`；
- 视频帧候选对象评分与人工确认；
- 演示MP4和视频端到端自动测试；
- 正式验证报告、规则来源说明和实验支撑数据。

## 可靠性改进

- 嵌套上传路径可正确映射为静态资源URL；
- 视频解码失败时删除已写入文件并返回明确错误；
- Windows依赖自检新增OpenCV；
- self_check新增演示MP4和解码组件检查。
