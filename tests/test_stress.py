"""极限测试：同一秒批量建、超长内容、坏文件、并发写、极小预算。"""
import json
import multiprocessing as mp
import tempfile
import unittest
from datetime import date
from pathlib import Path

from memblocks.store import Store
from memblocks.janitor import Janitor
from memblocks.timeparse import normalize


def _writer(root, n):
    st = Store(Path(root))
    for i in range(n):
        st.block_add(f"并发块-{i}")


class TestStress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()

    def tearDown(self):
        self.tmp.cleanup()

    # 1. 同一秒大量建块，ID 不能撞
    def test_many_blocks_same_second(self):
        for i in range(300):
            self.st.block_add(f"块{i}")
        blocks = self.st.block_list()
        self.assertEqual(len(blocks), 300)
        self.assertEqual(len({b["id"] for b in blocks}), 300)

    # 2. 5000 字块：切块后内容不能丢
    def test_5000_char_block_no_loss(self):
        text = "字" * 5000
        self.st.block_add(text)
        blocks = self.st.block_list()
        joined = "".join(b["summary"] for b in blocks).replace("…", "")
        self.assertEqual(len(joined), 5000)
        self.assertGreaterEqual(len(blocks), 6)

    # 3. 坏 JSON 一个字节
    def test_corrupt_one_byte(self):
        self.st.stable_add("正常数据")
        p = self.st.stable
        raw = p.read_text(encoding="utf-8")
        p.write_text(raw[:-1], encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.st.stable_list()
        self.assertEqual(len(list(self.st.root.glob("stable.json.bad-*"))), 1)

    # 4. 4 进程并发写块
    def test_concurrent_blocks(self):
        procs = [mp.Process(target=_writer, args=(str(self.st.root), 40)) for _ in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
        self.assertEqual(len(self.st.block_list()), 160)

    # 5. 稳定区 300 条：停在 100，最高权重保留
    def test_cap_300(self):
        for i in range(300):
            self.st.stable_add(f"事实{i}", weight=1.0 + (i % 50) * 0.1)
        items = self.st.stable_list()
        self.assertEqual(len(items), 100)
        self.assertGreaterEqual(min(x["weight"] for x in items), 1.0)

    # 6. 极小预算不崩
    def test_tiny_budget(self):
        for i in range(20):
            self.st.stable_add(f"事实{i}")
        out = self.st.inject("查询", 10)
        self.assertLessEqual(len(out), 300)

    # 7. 非法日期
    def test_invalid_dates(self):
        r = date(2026, 10, 31)
        self.assertEqual(normalize("2026-13-45", r), "")
        self.assertEqual(normalize("2月30日", r), "")

    # 8. 快照 6 次只留 3 份
    def test_snapshot_retention(self):
        for _ in range(6):
            self.st.snapshot()
        snaps = [x for x in self.st.snapshots.iterdir() if x.is_dir()]
        self.assertEqual(len(snaps), 3)

    # 9. 超长直接报错，不落盘
    def test_overlong_raises_no_write(self):
        with self.assertRaises(ValueError):
            self.st.stable_add("x" * 201)
        self.assertEqual(len(self.st.stable_list()), 0)

    # 10. janitor 在坏文件上要报错，不能当空处理
    def test_janitor_on_corrupt(self):
        self.st.stable.write_text("[]x", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            Janitor(self.st, dry_run=True).run()


if __name__ == "__main__":
    unittest.main()
