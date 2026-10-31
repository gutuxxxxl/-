"""双击加权的极限测试：权重上限、并发、非法 ID、不存在的 ID。"""
import tempfile
import threading
import unittest
from pathlib import Path

from memblocks.store import Store


class TestHit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        self.st.init()
        self.item = self.st.stable_add("测试记忆", weight=1.0)["item"]

    def tearDown(self):
        self.tmp.cleanup()

    def weight(self):
        return [x for x in self.st.stable_list() if x["id"] == self.item["id"]][0]["weight"]

    def test_weight_caps_at_9(self):
        for _ in range(100):
            self.st.stable_hit(self.item["id"])
        self.assertEqual(self.weight(), 9.0)

    def test_concurrent_hits(self):
        def work():
            for _ in range(5):
                self.st.stable_hit(self.item["id"])

        ts = [threading.Thread(target=work) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        # 1.0 + 20*5*0.2 = 21 → 上限 9
        self.assertEqual(self.weight(), 9.0)

    def test_unknown_id(self):
        self.assertIsNone(self.st.stable_hit("st-does-not-exist"))

    def test_todo_id_not_hit(self):
        t = self.st.todo_add("待办不该被加权")
        self.assertIsNone(self.st.stable_hit(t["id"]))

    def test_empty_id(self):
        self.assertIsNone(self.st.stable_hit(""))


if __name__ == "__main__":
    unittest.main()
