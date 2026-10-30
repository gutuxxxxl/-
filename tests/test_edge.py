"""第二轮极限：快照与写入并发、恢复、CLI 退出码、emoji、空块、边界日期。"""
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from memblocks.store import Store
from memblocks.janitor import Janitor
from memblocks.timeparse import normalize

ROOT = Path(__file__).resolve().parents[1]


class TestEdge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "记忆 目录"  # 带空格和中文
        self.st = Store(self.root)
        self.st.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_path_with_spaces_and_cn(self):
        self.st.stable_add("路径里有空格")
        self.assertEqual(len(self.st.stable_list()), 1)

    def test_emoji_and_long_line(self):
        self.st.stable_add("😀" * 100)
        out = self.st.inject("😀", 200)
        self.assertIn("😀", out)

    def test_empty_block_rejected(self):
        with self.assertRaises(ValueError):
            self.st.block_add("   ")

    def test_snapshot_while_writing(self):
        stop = threading.Event()
        errs = []

        def writer():
            i = 0
            while not stop.is_set():
                try:
                    self.st.block_add(f"写入{i}")
                except Exception as e:  # noqa
                    errs.append(e)
                i += 1

        t = threading.Thread(target=writer)
        t.start()
        try:
            for _ in range(5):
                self.st.snapshot()
        finally:
            stop.set()
            t.join(timeout=30)
        self.assertEqual(errs, [])

    def test_restore_after_block_delete(self):
        self.st.block_add("要恢复的块")
        snap = self.st.snapshot()
        for p in self.st.blocks.glob("*.json"):
            p.unlink()
        self.assertEqual(len(self.st.block_list()), 0)
        self.st.restore(snap)
        self.assertEqual(len(self.st.block_list()), 1)

    def test_restore_missing_snapshot(self):
        with self.assertRaises(FileNotFoundError):
            self.st.restore(self.root / "snapshots" / "nope")

    def test_corrupt_todo(self):
        self.st.todo.write_text("{oops", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.st.todo_list()
        self.assertEqual(len(list(self.root.glob("todo.json.bad-*"))), 1)

    def test_weekday_edge(self):
        # 2026-10-28 是周三
        r = date(2026, 10, 28)
        self.assertEqual(normalize("下周三", r), "2026-11-04")
        self.assertEqual(normalize("这周三", r), "2026-10-28")

    def test_cli_error_exit_code(self):
        r = subprocess.run(
            [sys.executable, "-m", "memblocks.cli", "--root", str(self.root),
             "stable", "add", "x" * 201],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", r.stdout)

    def test_inject_empty_memory(self):
        self.assertIn("元记忆", self.st.inject("随便问问", 100))

    def test_janitor_idempotent(self):
        self.st.todo_add("旧事", (date.today().replace(day=1)).isoformat())
        a = Janitor(self.st, dry_run=False).run()
        b = Janitor(self.st, dry_run=False).run()
        self.assertEqual(b["purged"], 0)
        self.assertLessEqual(a["purged"], 1)


class TestTailAndDates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inject_keeps_tail_keyword(self):
        self.st.block_add("开头" * 300 + "关键字在尾巴上" + "结尾" * 300)
        out = self.st.inject("尾巴", 800)
        self.assertIn("关键字在尾巴上", out)

    def test_date_variants(self):
        r = date(2026, 10, 31)
        self.assertEqual(normalize("十二月二十八", r), "2026-12-28")
        self.assertEqual(normalize("二十八号", r), "2026-10-28")
        self.assertEqual(normalize("28号", r), "2026-10-28")


if __name__ == "__main__":
    unittest.main()
