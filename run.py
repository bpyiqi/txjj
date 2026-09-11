from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        if port_available(host, port):
            return port
    raise RuntimeError("未找到可用本地端口，请关闭占用 8501-8520 端口的程序后重试。")


def open_browser_later(url: str) -> None:
    time.sleep(1.4)
    webbrowser.open(url)


def local_network_ip() -> str | None:
    """Return the address used by this computer on its active local network."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return None


def reset_data() -> None:
    from backend.app.database import initialize_database
    from backend.app.engine import synchronize_all

    initialize_database(force=True)
    synchronize_all()


def main() -> None:
    parser = argparse.ArgumentParser(description="通信基建施工数字化验真系统")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reset", action="store_true", help="启动前恢复标准工程数据")
    args = parser.parse_args()

    if args.reset:
        reset_data()
        print("[系统] 标准工程数据已恢复。")

    port = pick_port(args.host, args.port)
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{browser_host}:{port}"
    print("=" * 62)
    print("  通信基建施工透明化管理与数字化验真交付系统")
    print(f"  本地地址: {url}")
    if args.host == "0.0.0.0":
        network_ip = local_network_ip()
        if network_ip:
            print(f"  局域网地址: http://{network_ip}:{port}")
        print("  如其他电脑无法访问，请允许 Windows 防火墙放行此端口。")
    print("  按 Ctrl+C 停止系统")
    print("=" * 62)

    if not args.no_browser:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    from backend.app.main import app

    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
