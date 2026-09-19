"""Start and supervise the AMC backend and frontend together."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PRODUCT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PRODUCT_ROOT / "backend"
WEB_ROOT = PRODUCT_ROOT / "web1"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:8001"


def fetch(url: str, timeout: float = 1.5) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read(), response.headers.get("Server", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Server", "")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b"", ""


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def backend_ready() -> bool:
    status, body, _ = fetch(f"{BACKEND_URL}/health")
    if status != 200:
        return False
    try:
        payload = json.loads(body)
        return payload.get("code") == 0 and payload.get("data", {}).get("status") == "up"
    except (json.JSONDecodeError, AttributeError):
        return False


def frontend_ready() -> bool:
    status, body, _ = fetch(f"{FRONTEND_URL}/health")
    if status == 200:
        try:
            return json.loads(body).get("service") == "amc-web"
        except (json.JSONDecodeError, AttributeError):
            pass
    status, body, _ = fetch(f"{FRONTEND_URL}/")
    return status == 200 and b"AMC Steady Lab" in body and b'id="app"' in body


def wait_until(check, process: subprocess.Popen[bytes] | None, label: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if check():
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"{label}启动失败，进程退出码为 {process.returncode}")
        time.sleep(0.25)
    raise RuntimeError(f"{label}在 15 秒内未通过健康检查")


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    backend_python = BACKEND_ROOT / ".venv" / "Scripts" / "python.exe"
    if not backend_python.exists():
        print("未找到 backend/.venv，请先按照 backend/README.md 安装依赖。", file=sys.stderr)
        return 1

    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        if backend_ready():
            print(f"后端已在运行，继续使用 {BACKEND_URL}")
        else:
            if port_open(8000):
                raise RuntimeError("8000 端口已被非 AMC 后端占用，请先确认并关闭对应进程。")
            print("检查数据库连接……")
            check = subprocess.run(
                [str(backend_python), "-m", "app.cli", "check-db"],
                cwd=BACKEND_ROOT,
                check=False,
            )
            if check.returncode:
                print("数据库检查失败，后端未启动。请检查 backend/.env 和 MySQL。", file=sys.stderr)
                return check.returncode
            backend_process = subprocess.Popen(
                [
                    str(backend_python), "-m", "uvicorn", "app.main:app",
                    "--host", "127.0.0.1", "--port", "8000",
                ],
                cwd=BACKEND_ROOT,
            )
            wait_until(backend_ready, backend_process, "后端")
            print(f"后端已就绪：{BACKEND_URL}")

        if frontend_ready():
            print(f"前端已在运行，继续使用 {FRONTEND_URL}")
        else:
            # Distinguish an occupied port from a service that has not started.
            status, _, server = fetch(f"{FRONTEND_URL}/")
            if status or port_open(8001):
                raise RuntimeError(
                    f"8001 端口已被其他 HTTP 服务占用（{server or 'unknown server'}），"
                    "请先关闭占用进程。"
                )
            frontend_process = subprocess.Popen(
                [sys.executable, str(WEB_ROOT / "serve.py"), "--host", "127.0.0.1", "--port", "8001"],
                cwd=WEB_ROOT,
            )
            wait_until(frontend_ready, frontend_process, "前端")
            print(f"前端已就绪：{FRONTEND_URL}")

        print("\n启动完成。请访问 http://127.0.0.1:8001")
        print("保持此窗口运行；按 Ctrl+C 同时停止本次启动的服务。")
        while True:
            for process, label in ((backend_process, "后端"), (frontend_process, "前端")):
                if process is not None and process.poll() is not None:
                    raise RuntimeError(f"{label}意外退出，退出码为 {process.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务……")
        return 0
    except RuntimeError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1
    finally:
        stop_process(frontend_process)
        stop_process(backend_process)


if __name__ == "__main__":
    raise SystemExit(main())
