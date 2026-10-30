import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path("memories")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_TL = threading.local()


class Store:
    def __init__(self, root: Path | str = ROOT):
        self.root = Path(root)
        self.stable = self.root / "stable.json"
        self.todo = self.root / "todo.json"
        self.recent = self.root / "recent.jsonl"
        self.blocks = self.root / "blocks"
        self.snapshots = self.root / "snapshots"
        self.audit = self.root / "audit.log"
        self.facts = self.root / "facts.json"
        self.config = self.root / "config.json"
        self.pending = self.root / "facts_pending.json"
        self.events = self.root / "events.jsonl"
        self.lockfile = self.root / ".lock"

    @contextmanager
    def _locked(self):
        """跨进程文件锁，同进程内可重入。"""
        depth = getattr(_TL, "depth", 0)
        _TL.depth = depth + 1
        fh = None
        try:
            if depth == 0:
                self.root.mkdir(parents=True, exist_ok=True)
                fh = open(self.lockfile, "a+")
                try:
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                except Exception:
                    pass
            yield
        finally:
            _TL.depth = depth
            if fh is not None:
                try:
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
                fh.close()

    # ---------- 初始化 ----------
    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.blocks.mkdir(exist_ok=True)
        self.snapshots.mkdir(exist_ok=True)
        if not self.stable.exists():
            _save(self.stable, [])
        if not self.todo.exists():
            _save(self.todo, [])
        if not self.facts.exists():
            _save(self.facts, [])
        if not self.pending.exists():
            _save(self.pending, [])
        if not self.config.exists():
            _save(self.config, {"owner_names": ["主人", "我", "管理员"]})
        if not self.events.exists():
            self.events.write_text("", encoding="utf-8")
        if not self.recent.exists():
            self.recent.write_text("", encoding="utf-8")
        per = self.persona()
        return {
            "ok": True,
            "root": str(self.root),
            "persona": bool(per),
            "hint": "" if per else "未检测到人设。建议先导入：python -m memblocks.cli persona set --file persona.md",
        }

    # ---------- 稳定事实 ----------
    def stable_add_raw(self, text: str, tags=None, protected: bool = False):
        data = _load(self.stable, [])
        item = {"text": text, "tags": tags or [], "protected": protected,
                "at": time.strftime("%Y-%m-%d %H:%M")}
        data.append(item)
        _save(self.stable, data)
        return item

    # ---------- 人设（接入即视为重要） ----------
    def set_persona(self, text: str):
        """人设整体替换，永久保护，不参与淘汰。"""
        data = [x for x in _load(self.stable, []) if not x.get("protected")]
        data.insert(0, {
            "text": text.strip(),
            "tags": ["人设", "身份"],
            "protected": True,
            "kind": "persona",
            "at": time.strftime("%Y-%m-%d %H:%M"),
        })
        _save(self.stable, data)
        return data[0]

    def persona(self):
        for x in _load(self.stable, []):
            if x.get("kind") == "persona":
                return x
        return None

    def stable_list(self):
        return _load(self.stable, [])

    # ---------- 待办 ----------
    def todo_add_raw(self, text: str, due: str = ""):
        data = _load(self.todo, [])
        item = {"text": text, "due": due, "done": False, "at": time.strftime("%Y-%m-%d %H:%M")}
        data.append(item)
        _save(self.todo, data)
        return item

    def todo_list(self, include_done=False):
        data = _load(self.todo, [])
        return [x for x in data if include_done or not x.get("done")]

    def todo_done(self, index: int):
        data = _load(self.todo, [])
        if 0 <= index < len(data):
            data[index]["done"] = True
            _save(self.todo, data)
            return data[index]
        return None

    # ---------- 滚动关键词 ----------
    def recent_add_raw(self, text: str, limit: int = 30):
        line = json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "text": text}, ensure_ascii=False)
        with open(self.recent, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        lines = self.recent.read_text(encoding="utf-8").splitlines()
        if len(lines) > limit:
            self.recent.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8")

    def recent_list(self, limit: int = 20):
        out = []
        for line in self.recent.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    # ---------- 人物事实（带权重，可淡忘） ----------
    def owner_names(self):
        return _load(self.config, {}).get("owner_names", ["主人", "我"])

    def fact_add_raw(self, text: str, entity: str = "", tags=None, protected=None, emotion=None):
        from .emotions import score as _emo
        emotion = emotion or _emo(text)
        if protected is None:
            protected = entity.strip() in self.owner_names()
        data = _load(self.facts, [])
        item = {
            "id": "fact-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:4],
            "text": text,
            "entity": entity,
            "tags": tags or [],
            "protected": bool(protected),
            "score": round((1.5 if (tags and tags[0] in ("生日", "职业", "关系")) else 1.0)
                           * (1 + 0.6 * emotion.get("arousal", 0)), 3),
            "emotion": emotion,
            "hits": 1,
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "last_hit": time.strftime("%Y-%m-%d %H:%M"),
        }
        # 冲突检测：同一人物 + 同一类别，新的覆盖旧的
        kind = (tags or [""])[0]
        if entity and kind and kind not in ("", "other"):
            for old in data:
                if (old.get("entity") == entity and (old.get("tags") or [""])[0] == kind
                        and not old.get("superseded") and old.get("text") != text):
                    old["superseded"] = True
                    old["superseded_by"] = item["id"]
        data.append(item)
        _save(self.facts, data)
        return item

    def fact_list(self, include_superseded=False):
        data = _load(self.facts, [])
        return data if include_superseded else [x for x in data if not x.get("superseded")]
        return _load(self.facts, [])

    def fact_hit_raw(self, fid: str):
        data = _load(self.facts, [])
        for x in data:
            if x.get("id") == fid:
                x["score"] = min(5.0, x.get("score", 1.0) + 0.5)
                x["hits"] = x.get("hits", 1) + 1
                x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                _save(self.facts, data)
                return x
        return None

    def fact_decay_raw(self, floor: float = 0.15):
        """间隔复习模型：7 天内不动，7~30 天轻降，30 天以上重降。"""
        from datetime import datetime
        data = _load(self.facts, [])
        now = datetime.now()
        keep, dropped = [], 0
        for x in data:
            if x.get("protected"):
                keep.append(x)
                continue
            try:
                last = datetime.strptime(x.get("last_hit", x.get("at", "")), "%Y-%m-%d %H:%M")
            except Exception:
                last = now
            days = (now - last).days
            emo = x.get("emotion") or {}
            if emo.get("arousal", 0) > 0.7 and days <= 30:
                pass  # 闪光灯记忆：30 天内不衰减
            elif days <= 7:
                pass
            elif days <= 30:
                x["score"] = round(float(x.get("score", 1.0)) * 0.95, 3)
            else:
                x["score"] = round(float(x.get("score", 1.0)) * 0.70, 3)
            if x["score"] < floor:
                dropped += 1
            else:
                keep.append(x)
        _save(self.facts, keep)
        return len(keep), dropped

    # ---------- 待确认队列 ----------
    def pending_add_raw(self, items):
        data = _load(self.pending, [])
        added = 0
        for it in items:
            key = (it.get("entity", ""), it.get("text", ""))
            if any((x.get("entity", ""), x.get("text", "")) == key for x in data):
                continue
            # 跨轮去重：已入库的事实不再重复入候选
            if any((x.get("entity", ""), x.get("text", "")) == key for x in _load(self.facts, [])):
                continue
            it = dict(it)
            it["id"] = "pfact-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:4]
            data.append(it)
            added += 1
        _save(self.pending, data)
        return added

    def pending_list(self):
        return _load(self.pending, [])

    def pending_approve_raw(self, pid: str):
        data = _load(self.pending, [])
        for x in data:
            if x.get("id") == pid:
                data.remove(x)
                _save(self.pending, data)
                return self.fact_add(x.get("text", ""), x.get("entity", ""), [x.get("kind", "")],
                                     protected=x.get("protected"))
        return None

    def pending_reject_raw(self, pid: str):
        data = _load(self.pending, [])
        keep = [x for x in data if x.get("id") != pid]
        _save(self.pending, keep)
        return len(data) - len(keep)

    def fact_top(self, limit: int = 10):
        return sorted(self.fact_list(), key=lambda x: -float(x.get("score", 0)))[:limit]

    # ---------- 时间线事件 ----------
    def event_add_raw(self, when: str, actor: str, action: str, obj: str = "",
                  block_id: str = "", emotion=None):
        from .emotions import score as _emo
        from .timeparse import normalize as _norm
        when_abs = _norm(when) or when
        ev = {
            "event_id": "evt-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:4],
            "when": when_abs,
            "when_raw": when,
            "actor": actor,
            "action": action,
            "object": obj,
            "block_id": block_id,
            "emotion": emotion or _emo(f"{action}{obj}"),
        }
        with open(self.events, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def timeline(self, start: str = "", end: str = "", entity: str = "", limit: int = 100):
        rows = []
        for line in self.events.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if start and ev.get("when", "") < start:
                continue
            if end and ev.get("when", "") > end:
                continue
            if entity and entity not in (ev.get("actor", "") + ev.get("object", "")):
                continue
            rows.append(ev)
        rows.sort(key=lambda x: x.get("when", ""))
        return rows[-limit:]

    # ---------- 归档块 ----------
    def block_add_raw(self, summary: str, topic: str = "", type_: str = "note",
                  objects=None, conclusion: str = "", synonyms=None, source: str = ""):
        bid = "block-" + time.strftime("%Y%m%d-%H%M%S")
        block = {
            "id": bid,
            "summary": summary,
            "tags": {
                "topic": topic,
                "objects": objects or [],
                "conclusion": conclusion,
                "type": type_,
                "synonyms": synonyms or [],
            },
            "source": source,
            "time": time.strftime("%Y-%m-%d %H:%M"),
        }
        _save(self.blocks / f"{bid}.json", block)
        return block

    def block_list(self):
        out = []
        for p in sorted(self.blocks.glob("*.json")):
            out.append(_load(p, {}))
        return [b for b in out if b]

    def block_search(self, query: str, limit: int = 3):
        from .retrieval import TfIdf
        blocks = self.block_list()
        if not blocks or not query:
            return []
        docs = [(b.get("id", ""), (b.get("summary", "") + " " + str(b.get("tags", {})))) for b in blocks]
        idx = TfIdf(docs)
        ids = idx.search(query, limit)
        by_id = {b.get("id", ""): b for b in blocks}
        return [by_id[i] for i in ids if i in by_id]

    def _match(self, query: str, blob: str) -> bool:
        q = "".join(ch for ch in (query or "") if ch.strip())
        if not q:
            return True
        grams = {q[i:i + 2] for i in range(len(q) - 1)} if len(q) > 1 else {q}
        return any(g in blob for g in grams)

    def inject(self, query: str = "", max_tokens: int = 800):
        """只读：拼装注入文本，不修改任何权重。复习请用 review()。"""
        parts = []
        per = self.persona()
        if per:
            parts.append("【人设】\n" + per["text"])
        stable = [x for x in self.stable_list() if x.get("kind") != "persona"]
        if stable:
            parts.append("【稳定记忆】\n" + "\n".join(f"- {x['text']}" for x in stable[-30:]))

        # 事件：有查询就按相关过滤，否则只给最近 3 条
        events = self.timeline(limit=30)
        if query:
            events = [e for e in events if self._match(query, e.get("actor", "") + e.get("object", "") + e.get("action", ""))]
        events = events[-3:]
        if events:
            parts.append("【最近事件】\n" + "\n".join(
                f"- {e['when']} {e['actor']}{e['action']}{e.get('object','')}" for e in events))

        # 人物事实：有查询按相关过滤，否则只给权重前 3
        facts = self.fact_top(30)
        if query:
            facts = [x for x in facts if self._match(query, x.get("entity", "") + x.get("text", ""))]
            facts = facts[:8]
        else:
            facts = facts[:3]
        if facts:
            parts.append("【关于人物】\n" + "\n".join(
                f"- {(x.get('entity') or '某人')}：{x['text']}" for x in facts))

        todos = self.todo_list()
        if todos:
            parts.append("【待办】\n" + "\n".join(
                f"- {x['text']}" + (f"（截止 {x['due']}）" if x.get("due") else "") for x in todos[:15]))

        recent = self.recent_list()
        if recent:
            parts.append("【最近】\n" + "\n".join(f"- {x['text']}" for x in recent[-15:]))

        hits = self.block_search(query) if query else []
        if hits:
            parts.append("【相关归档】\n" + "\n".join(f"- {b.get('summary','')}" for b in hits[:3]))

        if query and not parts:
            parts.append("【元记忆】\n（关于这个问题没有可靠记忆，不要编造）")
        text = "\n\n".join(parts)
        return text[:max_tokens * 4]

    def review(self, query: str = "", limit: int = 8):
        """复习：把被检索到的事实权重 +0.2（显式调用，不在 inject 里偷偷做）。"""
        facts = self.fact_top(30)
        if query:
            facts = [x for x in facts if self._match(query, x.get("entity", "") + x.get("text", ""))]
        facts = facts[:limit]
        data = _load(self.facts, [])
        ids = {x["id"] for x in facts}
        for x in data:
            if x.get("id") in ids and not x.get("protected"):
                x["score"] = min(5.0, round(float(x.get("score", 1.0)) + 0.2, 3))
                x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
        with self._locked():
            _save(self.facts, data)
        return len(ids)


    # ---------- 带锁的写操作 ----------
    def stable_add(self, *a, **k):
        with self._locked():
            return self.stable_add_raw(*a, **k)

    def todo_add(self, *a, **k):
        with self._locked():
            return self.todo_add_raw(*a, **k)

    def recent_add(self, *a, **k):
        with self._locked():
            return self.recent_add_raw(*a, **k)

    def block_add(self, *a, **k):
        with self._locked():
            return self.block_add_raw(*a, **k)

    def event_add(self, *a, **k):
        with self._locked():
            return self.event_add_raw(*a, **k)

    def fact_add(self, *a, **k):
        with self._locked():
            return self.fact_add_raw(*a, **k)

    def fact_hit(self, *a, **k):
        with self._locked():
            return self.fact_hit_raw(*a, **k)

    def fact_decay(self, *a, **k):
        with self._locked():
            return self.fact_decay_raw(*a, **k)

    def pending_add(self, *a, **k):
        with self._locked():
            return self.pending_add_raw(*a, **k)

    def pending_approve(self, *a, **k):
        with self._locked():
            return self.pending_approve_raw(*a, **k)

    def pending_reject(self, *a, **k):
        with self._locked():
            return self.pending_reject_raw(*a, **k)

    # ---------- 审计 ----------
    def log(self, msg: str):
        with open(self.audit, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    def snapshot(self):
        import shutil
        name = "snap-" + time.strftime("%Y%m%d-%H%M%S")
        dst = self.snapshots / name
        dst.mkdir(parents=True, exist_ok=True)
        for p in [self.stable, self.todo, self.recent]:
            if p.exists():
                shutil.copy2(p, dst / p.name)
        if self.blocks.exists():
            shutil.copytree(self.blocks, dst / "blocks", dirs_exist_ok=True)
        return dst
