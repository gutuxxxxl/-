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


def _norm_text(text: str) -> str:
    import re
    t = (text or "").strip().lower()
    t = t.replace("号", "日").replace("是", "").replace("为", "")
    t = re.sub(r"[\s\u3000]+", "", t)
    t = re.sub(r"[，。,.、；;：:！!？?\-—_()（）\[\]【】]", "", t)
    t = re.sub(r"([0-9]{1,2})月([0-9]{1,2})日", lambda m: f"{int(m.group(1))}月{int(m.group(2))}日", t)
    return t


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
                except ImportError:
                    try:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                    except Exception:
                        pass
            yield
        finally:
            _TL.depth = depth
            if fh is not None:
                try:
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except ImportError:
                    try:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
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
    def _check(self, text, limit, kind):
        text = (text or "").strip()
        if not text:
            raise ValueError(f"{kind} 不能为空")
        if len(text) > limit:
            self.log(f"warn: {kind} 超长 {len(text)}>{limit}，已截断")
            text = text[:limit]
        return text

    def stable_add_raw(self, text: str, tags=None, protected: bool = False):
        text = self._check(text, 200, "稳定记忆")
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
        from .timeparse import normalize as _norm
        text = self._check(text, 200, "待办")
        if due:
            due = _norm(due) or due
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
        self._rotate(self.recent)
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
        text = self._check(text, 200, "事实")
        from .emotions import score as _emo
        emotion = emotion or _emo(text)
        if protected is None:
            protected = entity.strip() in self.owner_names()
        data = _load(self.facts, [])
        # 冲突检测：同一人物 + 同一类别，新的覆盖旧的
        kind = (tags or [""])[0]
        if not kind:
            for kw, k in (("生日", "生日"), ("职业是", "职业"), ("住在", "位置"), ("在", "位置"),
                          ("喜欢", "偏好"), ("不喜欢", "偏好")):
                if kw in text:
                    kind = k
                    break
        item = {
            "id": "fact-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:4],
            "text": text,
            "entity": entity,
            "tags": tags or [],
            "kind": kind,
            "protected": bool(protected),
            "score": round((1.5 if (tags and tags[0] in ("生日", "职业", "关系")) else 1.0)
                           * (1 + 0.6 * emotion.get("arousal", 0)), 3),
            "emotion": emotion,
            "hits": 1,
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "last_hit": time.strftime("%Y-%m-%d %H:%M"),
        }
        # 完全重复：直接加权返回，不再追加
        for old in data:
            if (old.get("entity") == entity and old.get("text") == text and not old.get("superseded")):
                old["score"] = round(float(old.get("score", 1.0)) + 0.1, 3)
                old["hits"] = old.get("hits", 1) + 1
                old["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                _save(self.facts, data)
                return old

        if entity and kind and kind not in ("", "other"):
            for old in data:
                old_kind = old.get("kind") or (old.get("tags") or [""])[0]
                if (old.get("entity") == entity and old_kind == kind
                        and not old.get("superseded") and old.get("text") != text):
                    old["superseded"] = True
                    old["superseded_by"] = item["id"]
        data.append(item)
        _save(self.facts, data)
        return item

    def fact_list(self, include_superseded=False):
        data = _load(self.facts, [])
        return data if include_superseded else [x for x in data if not x.get("superseded")]

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
            last = None
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    last = datetime.strptime(x.get("last_hit", x.get("at", "")), fmt)
                    break
                except Exception:
                    continue
            if last is None:
                self.log(f"warn: bad time for {x.get('id')}, treated as today")
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
        if isinstance(items, (dict, str)):
            items = [items]
        data = _load(self.pending, [])
        added = 0
        for it in items:
            if isinstance(it, str):
                it = {"text": it, "entity": "", "kind": "其他"}
            it = dict(it)
            key = (it.get("entity", ""), it.get("text", ""))
            if any((x.get("entity", ""), x.get("text", "")) == key for x in data):
                continue
            # 跨轮去重：已入库的事实不再重复入候选
            if any((x.get("entity", ""), x.get("text", "")) == key for x in _load(self.facts, [])):
                continue
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
        summary = self._check(summary, 2000, "块")
        bid = "block-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:6]
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
        if len(summary) > 800:
            mid = 600
            self.block_add_raw("…" + summary[mid:], topic, type_, objects, conclusion, synonyms, source)
            block["summary"] = summary[:mid] + "…"
            block["split"] = True
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
        def doc_of(b):
            t = b.get("tags") or {}
            objs = " ".join(t.get("objects") or [])
            syn = " ".join(t.get("synonyms") or [])
            return (b.get("summary", "") + " " + t.get("topic", "") + " " + objs + " " +
                    " ".join([syn] * 2))
        docs = [(b.get("id", ""), doc_of(b)) for b in blocks]
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
        """只读：按优先级拼装，每段有配额，段内按行裁剪。"""
        budget = max(120, int(max_tokens)) * 2  # 字符 ≈ token × 2
        parts = []
        used = 0

        def add(title, lines, ratio=0.5):
            nonlocal used
            lines = [ln for ln in lines if ln]
            if not lines:
                return
            cap = int(budget * ratio)
            seg, seg_len = [], 0
            for ln in lines:
                room = min(cap - seg_len, budget - used - len(title) - 2)
                if room <= 0:
                    break
                if len(ln) > room:
                    seg.append(ln[:max(0, room - 1)] + "…")
                    seg_len += room
                    break
                seg.append(ln)
                seg_len += len(ln) + 1
            if not seg:
                return
            block = title + "\n" + "\n".join(seg)
            parts.append(block)
            used += len(block)

        per = self.persona()
        if per:
            add("【人设】", [per["text"]], 0.35)

        facts = self.fact_list()
        protected = [f for f in facts if f.get("protected")]
        if protected:
            add("【重要】", [f"- {(f.get('entity') or '主人')}：{f['text']}" for f in protected], 0.45)

        stable = [x for x in self.stable_list() if x.get("kind") != "persona"]
        if stable:
            add("【稳定记忆】", [f"- {x['text']}" for x in stable], 0.45)

        todos = self.todo_list()
        if todos:
            add("【待办】", [f"- {x['text']}" + (f"（截止 {x['due']}）" if x.get("due") else "")
                            for x in todos], 0.30)

        events = self.timeline(limit=10)
        if query:
            events = [e for e in events
                      if self._match(query, e.get("actor", "") + e.get("object", "") + e.get("action", ""))]
        add("【最近事件】", [f"- {e['when']} {e['actor']}{e['action']}{e.get('object','')}"
                            for e in events[-3:]], 0.25)

        others = [f for f in self.fact_top(20) if not f.get("protected")]
        if query:
            others = [f for f in others if self._match(query, f.get("entity", "") + f.get("text", ""))]
        else:
            others = others[:3]
        add("【关于人物】", [f"- {(f.get('entity') or '某人')}：{f['text']}" for f in others], 0.30)

        recent = self.recent_list()
        add("【最近】", [f"- {x['text']}" for x in recent[-8:]], 0.20)

        hits = self.block_search(query, 3) if query else []
        add("【相关归档】", [f"- {b.get('summary','')}" for b in hits], 0.25)

        if not parts:
            return "【元记忆】\n（关于这个问题没有可靠记忆，不要编造）"
        return "\n\n".join(parts)

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
    def _rotate(self, path, max_bytes: int = 1_048_576):
        try:
            if path.exists() and path.stat().st_size > max_bytes:
                for i in range(4, 0, -1):
                    src = path.with_suffix(path.suffix + f".{i}")
                    dst = path.with_suffix(path.suffix + f".{i+1}")
                    if src.exists():
                        if dst.exists():
                            dst.unlink()
                        src.rename(dst)
                path.rename(path.with_suffix(path.suffix + ".1"))
        except Exception:
            pass

    def log(self, msg: str):
        self._rotate(self.audit)
        with open(self.audit, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    def export_zip(self, out_path):
        import zipfile
        out = Path(out_path)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in self.root.rglob("*"):
                if p.is_file() and not p.name.startswith(".lock"):
                    z.write(p, p.relative_to(self.root))
        return str(out)

    def restore(self, snapshot_dir):
        """从快照恢复（覆盖当前记忆文件）。"""
        import shutil
        src = Path(snapshot_dir)
        if not src.exists():
            raise FileNotFoundError(snapshot_dir)
        for name in ("stable.json", "todo.json", "facts.json", "events.jsonl", "recent.jsonl"):
            p = src / name
            if p.exists():
                shutil.copy2(p, self.root / name)
        blocks = src / "blocks"
        if blocks.exists():
            shutil.copytree(blocks, self.blocks, dirs_exist_ok=True)
        return {"ok": True, "restored_from": str(src)}

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
        snaps = sorted([x for x in self.snapshots.iterdir() if x.is_dir()])
        for old in snaps[:-10]:
            shutil.rmtree(old, ignore_errors=True)
        return dst
