import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from memblocks.store import Store
from memblocks.janitor import Janitor
from memblocks.timeparse import normalize


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()

    def tearDown(self):
        self.tmp.cleanup()


class TestFacts(Base):
    def test_persona_protected(self):
        self.st.set_persona("你是小鲸")
        per = self.st.persona()
        self.assertTrue(per["protected"])

    def test_owner_fact_protected(self):
        f = self.st.fact_add("生日是5月20日", "主人", ["生日"])
        self.assertTrue(f["protected"])
        f2 = self.st.fact_add("生日是3月3日", "张三", ["生日"])
        self.assertFalse(f2["protected"])

    def test_conflict_supersede(self):
        self.st.fact_add("职业是老师", "张三", ["职业"])
        self.st.fact_add("职业是律师", "张三", ["职业"])
        live = self.st.fact_list()
        self.assertEqual(len(live), 1)
        self.assertIn("律师", live[0]["text"])

    def test_inject_readonly(self):
        f = self.st.fact_add("职业是律师", "张三", ["职业"])
        before = f["score"]
        self.st.inject("张三")
        after = {x["id"]: x for x in self.st.fact_list()}[f["id"]]["score"]
        self.assertEqual(before, after)

    def test_review_boost(self):
        f = self.st.fact_add("职业是律师", "张三", ["职业"])
        before = {x["id"]: x for x in self.st.fact_list()}[f["id"]]["score"]
        self.st.review("张三")
        after = {x["id"]: x for x in self.st.fact_list()}[f["id"]]["score"]
        self.assertGreater(after, before)

    def test_decay_spaced(self):
        f = self.st.fact_add("喜欢咖啡", "张三", ["偏好"])
        data = json.loads((self.st.facts).read_text(encoding="utf-8"))
        data[0]["last_hit"] = (date.today() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M")
        self.st.facts.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        left, dropped = self.st.fact_decay()
        after = {x["id"]: x for x in self.st.fact_list()}[f["id"]]["score"]
        self.assertLess(after, f["score"])

    def test_flashbulb_no_decay(self):
        f = self.st.fact_add("他妈妈去世了", "张三", ["其他"])
        data = json.loads((self.st.facts).read_text(encoding="utf-8"))
        data[0]["last_hit"] = (date.today() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M")
        self.st.facts.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.st.fact_decay()
        after = {x["id"]: x for x in self.st.fact_list()}[f["id"]]["score"]
        self.assertEqual(after, f["score"])


class TestTime(unittest.TestCase):
    def test_relative(self):
        ref = date(2026, 10, 31)
        self.assertEqual(normalize("昨天", ref), "2026-10-30")
        self.assertEqual(normalize("上周三", ref), "2026-10-21")
        self.assertEqual(normalize("10月20日", ref), "2026-10-20")
        self.assertEqual(normalize("三个月前", ref), "2026-07-31")
        self.assertEqual(normalize("瞎写的"), "")


class TestJanitor(Base):
    def test_dry_run_no_change(self):
        self.st.todo_add("过期事", "2026-10-27")
        before = (self.st.todo).read_text(encoding="utf-8")
        Janitor(self.st, dry_run=True).run()
        self.assertEqual(before, (self.st.todo).read_text(encoding="utf-8"))

    def test_purge_expired(self):
        self.st.todo_add("过期事", (date.today() - timedelta(days=5)).isoformat())
        Janitor(self.st, dry_run=False).run()
        self.assertEqual(len(self.st.todo_list(True)), 0)


class TestPending(Base):
    def test_extract_approve(self):
        from memblocks.extract import extract
        items = extract("我的生日是5月20日。张三是我同事。")
        self.assertGreaterEqual(len(items), 2)
        n = self.st.pending_add(items)
        self.assertEqual(n, len(items))
        pid = self.st.pending_list()[0]["id"]
        fact = self.st.pending_approve(pid)
        self.assertIsNotNone(fact)


if __name__ == "__main__":
    unittest.main()
