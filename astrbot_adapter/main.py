"""AstrBot 适配层（模板，需自行安装启用）。

作用：把 memblocks 的 inject 文本拼进 LLM 请求的系统提示，
并在回复后调用 review 更新权重。

安装：把本目录放到 AstrBot 的 data/plugins/ 下，改 CONFIG 里的路径。
"""
import sys
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

CONFIG = {
    "memories_root": "/opt/astrbot/data/plugin_data/memory_blocks",
    "lib_path": "/opt/astrbot/data/plugin_data/memory_blocks_lib",
    "max_tokens": 800,
}


class MemoryBlocks(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        sys.path.insert(0, CONFIG["lib_path"])
        self.store = None
        try:
            from memblocks.store import Store
            self.store = Store(Path(CONFIG["memories_root"]))
            self.store.init()
            logger.info("[memory_blocks] loaded")
        except Exception as e:
            logger.error(f"[memory_blocks] init failed: {e}")

    @filter.on_llm_request()
    async def inject_memory(self, event: AstrMessageEvent, req):
        if not self.store:
            return
        try:
            text = self.store.inject(event.message_str or "", CONFIG["max_tokens"])
            if text:
                req.system_prompt = (req.system_prompt or "") + "\n\n" + text
        except Exception as e:
            logger.error(f"[memory_blocks] inject failed: {e}")

    @filter.on_llm_response()
    async def after_reply(self, event: AstrMessageEvent, resp):
        if not self.store:
            return
        try:
            self.store.review(event.message_str or "")
        except Exception as e:
            logger.error(f"[memory_blocks] review failed: {e}")
