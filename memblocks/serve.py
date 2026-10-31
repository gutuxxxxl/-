"""HTTP 接口：任何外部程序（DSH、n8n、脚本）都能调用的记忆服务。

启动：
    python -m memblocks.cli serve --port 8765
接口：
    GET  /health
    POST /inject   {"query": "...", "max_tokens": 800}
    POST /stable   {"text": "...", "tags": ["身份"], "weight": 1.0}
    POST /todo     {"text": "...", "due": "下周三"}
    POST /block    {"summary": "...", "tags": ["记忆"]}
    POST /review   {"query": "..."}
    GET  /star              记忆星图 HTML
    GET  /memories          稳定区 + 待办
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import Store


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "memblocks/1.6"

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else str(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                return self._json({"ok": True, "root": str(store.root)})
            if path == "/memories":
                return self._json({"stable": store.stable_list(), "todos": store.todo_list()})
            if path == "/star":
                from .star import render
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
                tmp.close()
                out = render(store, tmp.name)
                with open(out, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            path = self.path.split("?")[0]
            body = self._body()
            try:
                if path == "/inject":
                    text = store.inject(body.get("query", ""), int(body.get("max_tokens", 800)))
                    return self._json({"text": text})
                if path == "/stable":
                    item = store.stable_add(body.get("text", ""), body.get("tags") or [],
                                            float(body.get("weight", 1.0)),
                                            permanent=bool(body.get("permanent")),
                                            display_only=bool(body.get("display_only")))
                    return self._json(item)
                if path == "/todo":
                    return self._json(store.todo_add(body.get("text", ""), body.get("due", "")))
                if path == "/block":
                    return self._json(store.block_add(body.get("summary", ""), body.get("tags") or []))
                if path == "/review":
                    return self._json({"boosted": store.review(body.get("query", ""))})
            except (ValueError, RuntimeError) as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"error": "not found"}, 404)

    return Handler


def serve(root, port=8765, host="127.0.0.1"):
    store = Store(root)
    store.init()
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    return httpd
