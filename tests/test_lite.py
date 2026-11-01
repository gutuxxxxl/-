import json
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

    def test_overlong_rejected(self):
        with self.assertRaises(ValueError):
            self.st.stable_add("x" * 201)


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


class TestRobust(Base):
    def test_corrupt_json_raises_and_backs_up(self):
        self.st.stable.write_text("{broken", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.st.stable_list()
        self.assertEqual(len(list(self.st.root.glob("stable.json.bad-*"))), 1)

    def test_block_split_before_check(self):
        self.st.block_add("字" * 1700)
        self.assertEqual(len(self.st.block_list()), 3)

    def test_snapshot_names_unique(self):
        a = self.st.snapshot()
        b = self.st.snapshot()
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())

    def test_snapshot_contains_archive(self):
        snap = self.st.snapshot()
        self.assertTrue((snap / "stable.json").exists())
        self.assertTrue((snap / "archive.jsonl").exists())


class TestFirstRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_flag(self):
        self.st = Store(Path(self.tmp.name) / "fresh")
        info = self.st.init()
        self.assertTrue(info["first_run"])
        self.assertFalse(info["star_enabled"])
        self.st.config_set(star_enabled=True, first_run=False)
        self.assertFalse(self.st.init()["first_run"])
        self.assertTrue(self.st.config_get()["star_enabled"])


class TestPermanent(Base):
    def test_permanent_never_evicted(self):
        self.st.stable_add("人设：你是小鲸", weight=0.1, permanent=True)
        for i in range(STABLE_CAP):
            self.st.stable_add(f"普通{i}", weight=9.0)
        texts = [x["text"] for x in self.st.stable_list()]
        self.assertIn("人设：你是小鲸", texts)
        self.assertEqual(len(texts), STABLE_CAP)

    def test_pin_unpin(self):
        r = self.st.stable_add("要固定的记忆")
        sid = r["item"]["id"]
        self.st.stable_pin(sid, True)
        self.assertTrue([x for x in self.st.stable_list() if x["id"] == sid][0]["permanent"])
        self.st.stable_pin(sid, False)
        self.assertFalse([x for x in self.st.stable_list() if x["id"] == sid][0]["permanent"])

    def test_star_marks_permanent(self):
        from memblocks.star import build
        self.st.stable_add("恒星记忆", permanent=True)
        self.st.stable_add("普通记忆")
        nodes = build(self.st)["nodes"]
        flags = {n["label"]: n["permanent"] for n in nodes}
        self.assertTrue(flags["恒星记忆"])
        self.assertFalse(flags["普通记忆"])


class TestStaleTodo(Base):
    def test_old_todo_fades_by_weight(self):
        self.st.todo_add("没写时间的旧待办")
        data = json.loads(self.st.todo.read_text(encoding="utf-8"))
        from datetime import date, timedelta
        data[0]["last_decay"] = (date.today() - timedelta(days=20)).isoformat()
        self.st.todo.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        rep = Janitor(self.st, dry_run=False).run()
        self.assertEqual(len(self.st.todo_list(True)), 0)
        self.assertEqual(rep["purged"], 1)

    def test_recent_todo_fades_but_kept(self):
        self.st.todo_add("五天前的待办")
        data = json.loads(self.st.todo.read_text(encoding="utf-8"))
        from datetime import date, timedelta
        data[0]["last_decay"] = (date.today() - timedelta(days=5)).isoformat()
        self.st.todo.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        Janitor(self.st, dry_run=False).run()
        items = self.st.todo_list()
        self.assertEqual(len(items), 1)
        self.assertLess(items[0]["weight"], 1.0)

    def test_repeat_mention_boosts(self):
        t1 = self.st.todo_add("做可乐鸡翅")
        t2 = self.st.todo_add("做可乐鸡翅")
        self.assertEqual(t1["id"], t2["id"])
        self.assertGreater(t2["weight"], 1.0)

    def test_fresh_todo_kept(self):
        self.st.todo_add("今天的待办")
        Janitor(self.st, dry_run=False).run()
        self.assertEqual(len(self.st.todo_list()), 1)


class TestEvents(Base):
    def test_event_expires_after_three_days(self):
        from datetime import date, timedelta
        self.st.event_add("昨天吃了火锅")
        self.st.event_add("今天去了超市")
        data = self.st.events.read_text(encoding="utf-8").splitlines()
        import json as _json
        rows = [_json.loads(x) for x in data]
        rows[0]["at"] = (date.today() - timedelta(days=4)).isoformat()
        self.st.events.write_text("".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                  encoding="utf-8")
        dropped = self.st.event_purge()
        self.assertEqual(len(dropped), 1)
        self.assertEqual([e["text"] for e in self.st.event_list()], ["今天去了超市"])

    def test_event_in_inject(self):
        self.st.event_add("刚吃完火锅")
        self.assertIn("刚吃完火锅", self.st.inject("吃什么", 300))

    def test_event_in_star(self):
        from memblocks.star import build
        self.st.event_add("刚吃完火锅")
        nodes = build(self.st)["nodes"]
        self.assertTrue(any(n["kind"] == "事件" for n in nodes))


class TestDisplayOnly(Base):
    def test_inject_excludes_display_only(self):
        self.st.stable_add("要注入的事实")
        self.st.stable_add("只给人看的人设摘要", tags=["人设"], permanent=True, display_only=True)
        out = self.st.inject("测试")
        self.assertIn("要注入的事实", out)
        self.assertNotIn("只给人看的人设摘要", out)

    def test_star_includes_display_only(self):
        from memblocks.star import build
        self.st.stable_add("只给人看的人设摘要", display_only=True)
        nodes = build(self.st)["nodes"]
        self.assertTrue(any("人设摘要" in n["label"] for n in nodes))


class TestStar(Base):
    def test_render_html(self):
        from memblocks.star import render
        self.st.stable_add("用户是律师，在邹城执业", weight=2.0)
        self.st.todo_add("检查注入效果", "2026-11-07")
        self.st.block_add("讨论分层记忆：稳定区、待办、归档", ["记忆"])
        out = Path(self.tmp.name) / "map.html"
        render(self.st, out)
        html = out.read_text(encoding="utf-8")
        self.assertIn("记忆星图", html)
        self.assertIn("用户是律师", html)


class TestTime(unittest.TestCase):
    def test_cases(self):
        r = date(2026, 10, 31)
        self.assertEqual(normalize("大前天", r), "2026-10-28")
        self.assertEqual(normalize("上周三", r), "2026-10-21")
        self.assertEqual(normalize("2026-1-5", r), "2026-01-05")
        self.assertEqual(normalize("三个月前", r), "2026-07-31")
        self.assertEqual(normalize("一个月后", r), "2026-11-30")
        self.assertEqual(normalize("乱写", r), "")
        self.assertEqual(normalize("周末", r), "2026-10-31")  # ref 是周六
        self.assertEqual(normalize("晚上", r), "2026-10-31")
        self.assertEqual(normalize("明天晚上", r), "2026-11-01")
        self.assertEqual(normalize("一会", r), "2026-10-31")
        self.assertEqual(normalize("十二月二十八号", r), "2026-12-28")
        self.assertEqual(normalize("十月二十日", r), "2026-10-20")


if __name__ == "__main__":
    unittest.main()
