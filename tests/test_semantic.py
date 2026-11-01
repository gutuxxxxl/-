"""语义抽取测试：用假的模型客户端，不联网。"""
import json
import tempfile
import unittest
from pathlib import Path

from memblocks.store import Store
from memblocks.semantic import capture, distill, parse_facts


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def chat(self, messages, temperature=0.2, max_tokens=800):
        self.calls += 1
        return json.dumps(self.payload, ensure_ascii=False), {
            "prompt_tokens": 120, "completion_tokens": 40}


class TestParse(unittest.TestCase):
    def test_plain(self):
        raw = '[{"text":"他晚上要做鸡翅","kind":"待办","importance":3,"confidence":0.8}]'
        facts = parse_facts(raw)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["text"], "他晚上要做鸡翅")

    def test_fenced(self):
        raw = "```json\n[{\"text\":\"喜欢深色主题\"}]\n```"
        self.assertEqual(parse_facts(raw)[0]["text"], "喜欢深色主题")

    def test_garbage(self):
        self.assertEqual(parse_facts("不知道"), [])
        self.assertEqual(parse_facts("[]"), [])


class TestDistill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()
        self.st.config_set(distill_min=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_capture_ready_flag(self):
        self.assertFalse(capture(self.st, "第一句")["ready"])
        capture(self.st, "第二句")
        self.assertTrue(capture(self.st, "第三句")["ready"])

    def test_skip_below_min(self):
        capture(self.st, "只有一句")
        r = distill(self.st, client=FakeClient([]))
        self.assertTrue(r.get("skipped"))

    def test_extract_and_store(self):
        for t in ["他晚上要做鸡翅", "周末去爬山", "周三跑步十公里"]:
            capture(self.st, t)
        client = FakeClient([
            {"text": "他晚上要做鸡翅", "kind": "待办", "importance": 3, "confidence": 0.9},
            {"text": "周三跑步十公里", "kind": "习惯", "importance": 4, "confidence": 0.8},
        ])
        r = distill(self.st, client=client)
        self.assertEqual(r["facts"], 2)
        self.assertEqual(len(r["added"]), 2)
        self.assertEqual(len(self.st.stable_list()), 1)   # 习惯进稳定区
        self.assertEqual(len(self.st.todo_list()), 1)     # 待办进待办
        self.assertEqual(len(self.st.buffer_list()), 0)   # 缓冲区清空

    def test_dedupe_merges(self):
        for t in ["喜欢深色主题"] * 3:
            capture(self.st, t)
        client = FakeClient([{"text": "喜欢深色主题", "kind": "偏好", "importance": 3}])
        distill(self.st, client=client)
        client2 = FakeClient([{"text": "喜欢深色主题", "kind": "偏好", "importance": 3}])
        for t in ["又说了一次"] * 3:
            capture(self.st, t)
        r = distill(self.st, client=client2)
        self.assertEqual(len(self.st.stable_list()), 1)
        self.assertTrue(r["merged"] or len(r["added"]) == 0)

    def test_todo_keeps_due(self):
        for t in ["我明天做可乐鸡翅", "x", "y"]:
            capture(self.st, t)
        client = FakeClient([{"text": "做可乐鸡翅", "kind": "待办", "due": "明天",
                              "importance": 3, "confidence": 0.9}])
        distill(self.st, client=client)
        todo = self.st.todo_list()[0]
        from datetime import date, timedelta
        self.assertEqual(todo["due"], (date.today() + timedelta(days=1)).isoformat())

    def test_short_task_without_due(self):
        for t in ["去做可乐鸡翅", "x", "y"]:
            capture(self.st, t)
        client = FakeClient([{"text": "做可乐鸡翅", "kind": "待办", "due": "",
                              "importance": 2, "confidence": 0.6}])
        distill(self.st, client=client)
        self.assertEqual(len(self.st.todo_list()), 1)

    def test_usage_logged(self):
        for t in ["a", "b", "c"]:
            capture(self.st, t)
        distill(self.st, client=FakeClient([{"text": "测试事实", "kind": "事实"}]))
        log = self.st.audit.read_text(encoding="utf-8")
        self.assertIn("tokens in=120", log)


if __name__ == "__main__":
    unittest.main()
