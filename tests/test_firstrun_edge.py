"""首次安装流程的边界：升级、坏配置、非交互、参数冲突、disabled 状态。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memblocks.store import Store

ROOT = Path(__file__).resolve().parents[1]


def run_cli(root, *args, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "memblocks.cli", "--root", str(root), *args],
        cwd=str(ROOT), input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=60)


class TestFirstRunEdge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "m"

    def tearDown(self):
        self.tmp.cleanup()

    # 1. 已有数据的老用户升级：不该再问一遍
    def test_upgrade_with_existing_data_no_prompt(self):
        st = Store(self.root)
        st.init()
        st.stable_add("老用户的一条记忆")
        (self.root / "config.json").unlink(missing_ok=True)
        r = run_cli(self.root, "init")
        self.assertNotIn("首次安装", r.stdout)
        self.assertEqual(r.returncode, 0)

    # 2. 非交互：不卡住，默认关闭
    def test_non_interactive_no_hang(self):
        r = run_cli(self.root, "init", stdin="")
        self.assertIn("首次安装", r.stdout)
        cfg = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg["star_enabled"])
        self.assertFalse(cfg["first_run"])

    # 3. 先 config 后 init：不应重复询问
    def test_config_before_init(self):
        r = run_cli(self.root, "config", "--star", "on")
        self.assertEqual(r.returncode, 0)
        r2 = run_cli(self.root, "init")
        self.assertNotIn("首次安装", r2.stdout)
        cfg = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["star_enabled"])

    # 4. 参数冲突：--star 与 --no-star 同时给，后者生效
    def test_conflicting_flags(self):
        r = run_cli(self.root, "init", "--star", "--no-star")
        cfg = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg["star_enabled"])
        self.assertIn("首次安装", r.stdout)

    # 5. 配置损坏：要报错，不能静默重建
    def test_corrupt_config(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "config.json").write_text("{bad", encoding="utf-8")
        r = run_cli(self.root, "config", "--show")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error", r.stdout.lower())

    # 6. 星图关闭时应提示怎么开
    def test_star_disabled_hint(self):
        run_cli(self.root, "init", "--no-star")
        r = run_cli(self.root, "star", "--out", str(self.root / "m.html"))
        self.assertIn("config --star on", r.stdout)

    # 6b. DSH 标记与命令
    def test_dsh_flag_and_command(self):
        r = run_cli(self.root, "init", "--dsh")
        cfg = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["dsh_enabled"])
        self.assertIn("DSH", r.stdout)
        r2 = run_cli(self.root, "dsh", "--json")
        data = json.loads(r2.stdout)
        self.assertTrue(data["enabled"])
        self.assertIn("inject", data["inject_cmd"])
        run_cli(self.root, "config", "--dsh", "off")
        r3 = run_cli(self.root, "dsh", "--json")
        self.assertFalse(json.loads(r3.stdout)["enabled"])

    # 7. init 可重复执行，不重复打印横幅
    def test_init_idempotent_banner(self):
        run_cli(self.root, "init", "--star")
        r = run_cli(self.root, "init")
        self.assertNotIn("首次安装", r.stdout)
        self.assertIn("star_enabled", r.stdout)


class TestUnwritable(unittest.TestCase):
    def test_parent_is_file(self):
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        (base / "blocker").write_text("x", encoding="utf-8")
        r = run_cli(base / "blocker" / "data", "init")
        self.assertEqual(r.returncode, 2)
        self.assertIn("无法创建数据目录", r.stdout)

    def test_missing_disk_like_root(self):
        # 盘符不存在
        r = run_cli(r"Z:\no-such-drive\memblocks", "init")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
