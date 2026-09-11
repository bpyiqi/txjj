from __future__ import annotations

import random
import subprocess
from pathlib import Path
from typing import Any


def ensure_video_decodable(video_path: Path) -> bool:
    """Keep readable videos unchanged; normalize unsupported MP4 codecs in place."""
    import cv2

    if video_path.stat().st_size < 4096:
        header = video_path.read_bytes()
        if b"ftyp" in header and b"mdat" not in header and b"moof" not in header:
            raise ValueError(
                f"所选文件仅有 {video_path.stat().st_size} 字节，只包含视频初始化信息，不包含可分析画面"
            )

    capture = cv2.VideoCapture(str(video_path))
    try:
        opened, frame = capture.isOpened(), capture.read()[1] if capture.isOpened() else None
    finally:
        capture.release()
    if opened and frame is not None:
        return False

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise ValueError("当前视频编码需要兼容转换，请重新运行系统环境检查后上传") from exc

    converted = video_path.with_name(f"{video_path.stem}.normalized.mp4")
    try:
        result = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(video_path), "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(converted),
            ],
            capture_output=True,
            timeout=600,
        )
        if result.returncode != 0 or not converted.exists() or converted.stat().st_size == 0:
            raise ValueError("视频文件无法读取，请确认文件已完整下载并可正常播放")
        check = cv2.VideoCapture(str(converted))
        try:
            valid, frame = check.read() if check.isOpened() else (False, None)
        finally:
            check.release()
        if not valid or frame is None:
            raise ValueError("视频兼容转换失败，请将视频导出为标准 MP4 后重试")
        converted.replace(video_path)
        return True
    except subprocess.TimeoutExpired as exc:
        raise ValueError("视频兼容转换超时，请压缩视频后重试") from exc
    finally:
        converted.unlink(missing_ok=True)


def read_key_frames(video_path: Path, sample_count: int) -> list[tuple[float, Any]]:
    """Read evenly positioned frames, falling back to sequential decoding."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("施工影像解析组件不可用") from exc

    sample_count = max(1, sample_count)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("无法打开施工视频，请确认文件为可播放的 MP4")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0
    samples: list[tuple[int, float, Any]] = []
    try:
        if duration > 0:
            for index in range(sample_count):
                timestamp = duration * (index + 0.5) / sample_count
                cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = cap.read()
                if ok:
                    samples.append((index, timestamp, frame))
        if len(samples) < sample_count:
            samples.clear()
            cap.release()
            cap = cv2.VideoCapture(str(video_path))
            rng = random.Random(0)
            frame_index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                stream_seconds = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0) / 1000
                timestamp = stream_seconds if stream_seconds > 0 else frame_index / (fps or 25.0)
                item = (frame_index, timestamp, frame)
                if len(samples) < sample_count:
                    samples.append(item)
                else:
                    position = rng.randint(0, frame_index)
                    if position < sample_count:
                        samples[position] = item
                frame_index += 1
    finally:
        cap.release()
    if not samples:
        raise ValueError("无法解码施工视频关键影像，请确认视频编码可正常播放")
    return [(timestamp, frame) for _, timestamp, frame in sorted(samples, key=lambda item: item[0])]


def write_jpeg(frame: Any, target: Path) -> None:
    import cv2

    encoded_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not encoded_ok:
        raise ValueError("关键施工影像生成失败")
    encoded.tofile(target)
