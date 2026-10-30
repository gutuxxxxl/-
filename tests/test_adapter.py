"""适配层导入测试：用假的 astrbot 模块验证 main.py 能加载、装饰器能挂上。"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _install_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                       error=lambda *a, **k: None)
    event = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:
        pass

    def passthrough():
        def deco(fn):
            fn.__wrapped_by = True
            return fn
        return deco

    event.AstrMessageEvent = AstrMessageEvent
    event.filter = types.SimpleNamespace(on_llm_request=passthrough,
                                         on_llm_response=passthrough)
    star = types.ModuleType("astrbot.api.star")

    class Star:
        def __init__(self, context):
            self.context = context

    class Context:
        pass

    star.Star = Star
    star.Context = Context
    sys.modules.update({
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.api.event": event,
        "astrbot.api.star": star,
    })
    astrbot.api = api
    astrbot.event = event
    astrbot.star = star


class TestAdapter(unittest.TestCase):
    def test_import_and_decorators(self):
        _install_stubs()
        path = ROOT / "astrbot_adapter" / "main.py"
        spec = importlib.util.spec_from_file_location("mb_adapter", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "MemoryBlocks"))
        self.assertTrue(getattr(mod.MemoryBlocks.inject_memory, "__wrapped_by", False))
        self.assertTrue(getattr(mod.MemoryBlocks.after_reply, "__wrapped_by", False))
        # 路径配置存在
        self.assertIn("memories_root", mod.CONFIG)


if __name__ == "__main__":
    unittest.main()
