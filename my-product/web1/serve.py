"""Reliable local static server for the AMC frontend."""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parent


class AMCRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self) -> None:
        # Development must always pick up the latest HTML, JS, and CSS.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            payload = json.dumps(
                {"status": "up", "service": "amc-web", "root": str(WEB_ROOT)},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve AMC web1 without browser caching")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer((args.host, args.port), AMCRequestHandler)
    except OSError as exc:
        raise SystemExit(
            f"前端端口 {args.host}:{args.port} 无法绑定，可能已有程序占用。"
            "请关闭旧服务，或使用项目统一启动器检查端口。"
        ) from exc

    print(f"AMC frontend: http://{args.host}:{args.port}", flush=True)
    print(f"Health check: http://{args.host}:{args.port}/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
