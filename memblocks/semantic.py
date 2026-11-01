"""语义化记忆：攒几条消息 → 让模型抽事实 → 合并入库。

比字符串匹配稳：不靠关键词，也不按字数卡。
"""
import json
import re
import time

from .llm import LLM, config

SYSTEM = """你是记忆抽取器。读下面的对话，只抽取值得长期记住的事实。
规则：
1. 只抽长期有效的信息：身份、偏好、习惯、关系、约定、正在做的项目、待办。
2. 聊天语气、情绪不要。日常琐事（吃了什么、去了哪、见了谁）如果是最近三天内的，记成 kind「事件」，只保留三天；超过三天的不记。
5. 但「重要的人生经历」要记：搬家、换工作、升学、结婚、生子、生病住院、手术、亲人去世、大额支出。kind 用「经历」。
6. 判断「三天内」看对话里的时间词：今天、昨天、前天、刚刚 → 事件；上周、上个月、去年 → 不记（重要经历除外）。
3. 每条不超过 40 字，用陈述句，不要用「他说」这类转述前缀。
4. 没有可记的就输出 []。
输出 JSON 数组，每项字段：text（事实）、kind（事实/偏好/习惯/关系/经历/事件/待办）、
due（待办的原话时间，如「明天」「一会」「下周三」，没有就空字符串）、importance（1-5）、confidence（0-1）。
只输出 JSON，不要别的文字。
"""


def _strip_fence(s):
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_facts(raw):
    """把模型输出解析成列表，失败返回空列表。"""
    try:
        data = json.loads(_strip_fence(raw))
    except Exception:
        m = re.search(r"\[.*\]", _strip_fence(raw), re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out = []
    for it in data:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        if not text:
            continue
        try:
            imp = float(it.get("importance", 3))
        except Exception:
            imp = 3.0
        try:
            conf = float(it.get("confidence", 0.7))
        except Exception:
            conf = 0.7
        out.append({
            "text": text[:200],
            "kind": str(it.get("kind") or "事实")[:8],
            "due": str(it.get("due") or "").strip()[:20],
            "importance": max(1.0, min(5.0, imp)),
            "confidence": max(0.0, min(1.0, conf)),
        })
    return out


def capture(store, text, role="user"):
    """把一条消息放进缓冲区。"""
    from .store import _save
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty"}
    rows = store.buffer_list()
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "role": role, "text": text[:1000]}
    with open(store.buffer, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # 只保留最近 80 条
    rows = (rows + [rec])[-80:]
    store.buffer.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                            encoding="utf-8")
    need = int(store.config_get().get("distill_min", 5))
    return {"ok": True, "buffered": len(rows), "ready": len(rows) >= need}


def distill(store, client=None, min_msgs=None, force=False, keep_rest=True):
    """抽取缓冲区里的事实并合并入库。"""
    from .store import _save
    cfg = store.config_get()
    need = int(min_msgs if min_msgs is not None else cfg.get("distill_min", 5))
    buf = store.buffer_list()
    if len(buf) < need and not force:
        return {"ok": True, "skipped": True, "buffered": len(buf), "need": need}
    if not buf:
        return {"ok": True, "skipped": True, "buffered": 0, "need": need}

    if client is None:
        c = config(store)
        if not c.get("api_key"):
            return {"ok": False, "error": "未配置模型密钥：config --llm-key <key>"}
        client = LLM(c["base_url"], c["api_key"], c["model"])

    lines = [f"{m['role']}: {m['text']}" for m in buf]
    prompt = "对话：\n" + "\n".join(lines) + "\n\n只输出 JSON 数组。"
    raw, usage = client.chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ])
    facts = parse_facts(raw)

    added, merged, skipped = [], [], []
    for f in facts:
        w = round(0.6 + 0.3 * f["importance"] + 0.2 * f["confidence"], 2)
        kind = f["kind"]
        if kind == "事件":
            item = store.event_add(f["text"], 3)
            added.append({"text": f["text"], "kind": "事件", "weight": 0, "id": item["id"]})
            continue
        if kind == "待办":
            item = store.todo_add(f["text"], f.get("due") or "")
        else:
            before = len(store.stable_list())
            item = store.stable_add(f["text"], [kind], weight=w)
            if len(store.stable_list()) == before:
                merged.append(f["text"])
                continue
            item = item["item"]
        added.append({"text": f["text"], "kind": kind, "weight": w, "id": item.get("id")})

    rest = buf[need:] if keep_rest else []
    store.buffer.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rest),
                            encoding="utf-8")
    store.log(f"distill: {len(facts)} facts, +{len(added)}, merged {len(merged)}, "
              f"tokens in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}")
    return {
        "ok": True, "facts": len(facts), "added": added, "merged": merged,
        "usage": usage, "buffer_left": len(rest),
    }
