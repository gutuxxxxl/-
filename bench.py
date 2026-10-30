"""性能基线：1000 块时的注入/维护耗时。

用法：
    python bench.py
"""
import statistics
import tempfile
import time
from pathlib import Path

from memblocks.store import Store
from memblocks.janitor import Janitor


def main():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    st = Store(root)
    st.init()

    for i in range(100):
        st.stable_add(f"长期事实{i}", weight=1.0 + (i % 10) * 0.1)

    t0 = time.perf_counter()
    for i in range(1000):
        st.block_add(f"第{i}块：讨论了记忆分层、上下文压缩和检索策略，结论是保留稳定区。")
    build = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(5):
        st.block_list()
    listing = (time.perf_counter() - t0) / 5

    times = []
    for i in range(20):
        t0 = time.perf_counter()
        out = st.inject(f"第{i}块 记忆", 800)
        times.append((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    rep = Janitor(st, dry_run=False).run()
    jan = time.perf_counter() - t0

    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

    print(f"建 1000 块:     {build:.2f}s ({build / 1000 * 1000:.1f} ms/块)")
    print(f"block_list:     {listing * 1000:.0f} ms")
    print(f"inject 平均:    {statistics.mean(times):.1f} ms (p95 {sorted(times)[18]:.1f} ms)")
    print(f"inject 输出:    {len(out)} 字符")
    print(f"janitor:        {jan * 1000:.0f} ms")
    print(f"磁盘占用:       {size / 1048576:.2f} MB")
    print(f"块文件数:       {len(st.block_list())}")


if __name__ == "__main__":
    main()
