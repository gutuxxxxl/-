"""并发回归：4 个进程各写 60 条事实，最终必须一条不少。

Windows 走 msvcrt 锁，Linux 走 fcntl.flock。
运行：
    python -m unittest tests.test_concurrency -v
"""
import multiprocessing as mp
import tempfile
import unittest
from pathlib import Path

from memblocks.store import Store


def _worker(root: str, prefix: str, n: int):
    st = Store(Path(root))
    for i in range(n):
        st.fact_add(f"{prefix}-{i}", "压测", ["压测"])


class TestConcurrency(unittest.TestCase):
    def test_parallel_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            Store(Path(tmp)).init()
            procs = [mp.Process(target=_worker, args=(tmp, f"p{k}", 60)) for k in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join(timeout=120)

            st = Store(Path(tmp))
            facts = st.fact_list(True)
            self.assertEqual(len(facts), 240, f"丢了 {240 - len(facts)} 条")
            texts = {x["text"] for x in facts}
            self.assertEqual(len(texts), 240)


if __name__ == "__main__":
    unittest.main()
