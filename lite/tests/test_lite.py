import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from memblocks.store import Store, STABLE_CAP
from memblocks.janitor import Janitor
from memblocks.timeparse import normalize


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()

    def tearDown(self):
        self.tmp.cleanup()


class TestStable(Base):
    def test_add_and_list(self):
        self.st.stable_add("我在邹城做律师", ["身份"])
        self.assertEqual(len(self.st.stable_list()), 1)

    def test_dedupe_merge(self):
        self.st.stable_add("生日是12月28号")
        r = self.st.stable_add("生日 12 月 28 日")
        self.assertTrue(r.get("merged"))
        self.assertEqual(len(self.st.stable_list()), 1)

    def test_cap_evicts_low_weight_old(self):
        for i in range(STABLE_CAP):
            self.st.stable_add(f"事实{i}", weight=1.0 + i * 0.01)
        r = self.st.stable_add("最重的事", weight=9.0)
        self.assertEqual(len(self.st.stable_list()), STABLE_CAP)
        self.assertEqual(len(r["evicted"]), 1)
        self.assertIn("事实0", r["evicted"][0]["text"])
        self.assertEqual(self.st.stable_list()[-1]["text"], "最重的事")

    def test_protected_never_evicted(self):
        self.st.stable_add("人设：你是小鲸", weight=0.1, protected=True)
        for i in range(STABLE_CAP):
            self.st.stable_add(f"普通{i}", weight=5.0)
        texts = [x["text"] for x in self.st.stable_list()]
        self.assertIn("人设：你是小鲸", texts)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            self.st.stable_add("   ")


class TestTodo(Base):
    def test_due_normalized(self):
        t = self.st.todo_add("开庭", "下周三")
        self.assertRegex(t["due"], r"^\d{4}-\d{2}-\d{2}$")

    def test_purge_archives(self):
        t = self.st.todo_add("旧事", (date.today() - timedelta(days=10)).isoformat())
        self.st.todo_done(t["id"])
        rep = Janitor(self.st, dry_run=False).run()
        self.assertEqual(rep["purged"], 1)
        self.assertEqual(len(self.st.todo_list(True)), 0)
        lines = self.st.archive.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

    def test_dry_run_no_change(self):
        self.st.todo_add("旧事", (date.today() - timedelta(days=10)).isoformat())
        before = self.st.todo.read_text(encoding="utf-8")
        Janitor(self.st, dry_run=True).run()
        self.assertEqual(before, self.st.todo.read_text(encoding="utf-8"))


class TestBlock(Base):
    def test_split(self):
        self.st.block_add("长" * 1080)
        self.assertEqual(len(self.st.block_list()), 2)

    def test_inject_budget(self):
        for i in range(50):
            self.st.stable_add(f"事实内容{i}")
        out = self.st.inject("测试", 100)
        self.assertLessEqual(len(out), 200 + 60)
        self.assertIn("【稳定记忆】", out)


class TestTime(unittest.TestCase):
    def test_cases(self):
        r = date(2026, 10, 31)
        self.assertEqual(normalize("大前天", r), "2026-10-28")
        self.assertEqual(normalize("上周三", r), "2026-10-21")
        self.assertEqual(normalize("2026-1-5", r), "2026-01-05")
        self.assertEqual(normalize("三个月前", r), "2026-07-31")
        self.assertEqual(normalize("一个月后", r), "2026-11-30")
        self.assertEqual(normalize("乱写", r), "")


if __name__ == "__main__":
    unittest.main()
