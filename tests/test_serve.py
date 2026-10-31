"""HTTP 接口测试：起一个临时服务，跑通 inject / stable / todo / star。"""
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from memblocks.serve import serve


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.httpd = serve(Path(self.tmp.name), port=0)
        self.port = self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def _req(self, path, payload=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_health(self):
        code, body = self._req("/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_flow(self):
        self._req("/stable", {"text": "用户是律师", "tags": ["身份"], "weight": 2.0})
        self._req("/todo", {"text": "写脚本", "due": "明天"})
        self._req("/block", {"summary": "讨论星图", "tags": ["设计"]})
        _, body = self._req("/inject", {"query": "律师", "max_tokens": 400})
        self.assertIn("用户是律师", json.loads(body)["text"])
        _, rv = self._req("/review", {"query": "律师"})
        self.assertGreaterEqual(json.loads(rv)["boosted"], 1)
        _, mem = self._req("/memories")
        data = json.loads(mem)
        self.assertEqual(len(data["stable"]), 1)
        self.assertEqual(len(data["todos"]), 1)

    def test_star(self):
        self._req("/stable", {"text": "一条记忆"})
        code, body = self._req("/star")
        self.assertEqual(code, 200)
        self.assertIn("记忆星图", body)

    def test_bad_payload(self):
        try:
            self._req("/stable", {"text": ""})
            self.fail("应该返回 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_unknown(self):
        try:
            self._req("/nope")
            self.fail("应该 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main()
