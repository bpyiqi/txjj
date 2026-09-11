from __future__ import annotations

import argparse
import importlib
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
WINDOWS_REQUIREMENTS = ROOT / "backend" / "requirements-windows.txt"
VENV_DIR = ROOT / ".venv"
REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "multipart",
    "xlsxwriter",
    "reportlab",
    "cv2",
    "imageio_ffmpeg",
    "torch",
    "ultralytics",
)


def configure_windows_console() -> None:
    if os.name != "nt":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    for stream_id in (-11, -12):
        handle = kernel32.GetStdHandle(stream_id)
        mode = ctypes.c_ulong()
        if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def fail(message: str, code: int = 1) -> int:
    print(f"[ERROR] {message}")
    return code


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def enter_project_venv() -> int:
    python = venv_python()
    usable = False
    if python.exists():
        try:
            usable = subprocess.run(
                [str(python), "-c", "import sys"],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode == 0
        except OSError:
            pass
    if not usable:
        action = "Repairing" if python.exists() else "Creating"
        print(f"[SETUP] {action} isolated Python environment: {VENV_DIR}")
        command = [sys.executable, "-m", "venv"]
        if python.exists():
            command.append("--clear")
        result = subprocess.run([*command, str(VENV_DIR)], cwd=ROOT)
        if result.returncode != 0:
            return fail("Could not create or repair the project virtual environment.", result.returncode)
    command = [str(python), str(Path(__file__).resolve()), *sys.argv[1:]]
    return subprocess.call(command, cwd=ROOT)


def runtime_errors() -> dict[str, str]:
    errors: dict[str, str] = {}
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    return errors


def ensure_runtime() -> int:
    if sys.version_info < (3, 11):
        return fail("Python 3.11 or newer is required.")

    broken = runtime_errors()
    if not broken:
        print(f"[OK] Python {sys.version.split()[0]} and required packages are available.")
        return 0

    for name, error in broken.items():
        print(f"[SETUP] {name}: {error}")
    print("[SETUP] Installing required Python packages...")
    requirements = WINDOWS_REQUIREMENTS if platform.system() == "Windows" else REQUIREMENTS
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements),
    ]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return fail("Dependency installation failed. Check the network and Python installation.", result.returncode)

    broken_after = runtime_errors()
    if broken_after:
        print("[SETUP] Existing packages are incompatible; reinstalling them...")
        repair = subprocess.run([*command[:-2], "--force-reinstall", *command[-2:]], cwd=ROOT)
        if repair.returncode != 0:
            return fail("Dependency repair failed.", repair.returncode)
        broken_after = runtime_errors()
        if broken_after:
            details = "; ".join(f"{name}: {error}" for name, error in broken_after.items())
            return fail("Packages are still unavailable after repair: " + details)
    print("[OK] Dependencies installed.")
    return 0


def main() -> int:
    configure_windows_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--train", type=int, metavar="EPOCHS")
    parser.add_argument("--train-safety", type=int, metavar="EPOCHS")
    parser.add_argument("--safety-model", choices=["yolov8n.pt", "yolov8s.pt"], default="yolov8n.pt")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    os.environ.setdefault("PYTHONUTF8", "1")
    if not running_in_project_venv():
        if runtime_errors():
            return enter_project_venv()
        print(f"[OK] Using available Python environment: {sys.executable}")

    status = ensure_runtime()
    if status:
        return status

    if args.train_safety is not None:
        if args.train_safety < 1:
            return fail("Training epochs must be at least 1.")
        command = [
            sys.executable,
            str(ROOT / "training" / "train_safety_yolo.py"),
            "--epochs",
            str(args.train_safety),
            "--model",
            args.safety_model,
        ]
    elif args.train is not None:
        if args.train < 1:
            return fail("Training epochs must be at least 1.")
        command = [
            sys.executable,
            str(ROOT / "training" / "train_construction_yolo.py"),
            "--epochs",
            str(args.train),
        ]
    elif args.self_check:
        command = [sys.executable, str(ROOT / "self_check.py")]
    else:
        command = [sys.executable, str(ROOT / "run.py"), "--host", args.host]
        if args.reset:
            command.append("--reset")

    print("[START] " + " ".join(command))
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        print("\n[STOP] 系统已停止。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
