"""三层记忆存储：稳定区（有上限、按权重淘汰）/ 待办 / 归档块。"""
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

STABLE_CAP = 100
SNAPSHOT_KEEP = 3


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(text):
    import re
    t = (text or "").strip().lower().replace("号", "日").replace("是", "").replace("为", "")
    t = re.sub(r"[\s\u3000]+", "", t)
    return re.sub(r"[，。,.、；;：:！!？?\-—_()（）\[\]【】]", "", t)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.stable = self.root / "stable.json"
        self.todo = self.root / "todo.json"
        self.blocks = self.root / "blocks"
        self.snapshots = self.root / "snapshots"
        self.archive = self.root / "archive.jsonl"
        self.audit = self.root / "audit.log"
        self.lock = self.root / ".lock"

    # ---------- 基础 ----------
    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.blocks.mkdir(exist_ok=True)
        self.snapshots.mkdir(exist_ok=True)
        for p, d in ((self.stable, []), (self.todo, [])):
            if not p.exists():
                _save(p, d)
        if not self.archive.exists():
            self.archive.write_text("", encoding="utf-8")
        return {"ok": True, "root": str(self.root), "stable_cap": STABLE_CAP}

    def log(self, msg):
        with open(self.audit, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock, "a+")
        try:
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except ImportError:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                try:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            except Exception:
                pass
            fh.close()

    def _check(self, text, limit, kind):
        t = (text or "").strip()
        if not t:
            raise ValueError(f"{kind} 不能为空")
        if len(t) > limit:
            self.log(f"warn: {kind} 超长 {len(t)}>{limit}，已截断")
            t = t[:limit]
        return t

    # ---------- 稳定区 ----------
    def stable_add(self, text, tags=None, weight=1.0, protected=False):
        text = self._check(text, 200, "稳定记忆")
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                if _norm(x.get("text")) == _norm(text):
                    x["weight"] = round(float(x.get("weight", 1.0)) + 0.2, 2)
                    x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                    _save(self.stable, data)
                    return {"item": x, "merged": True}

            item = {
                "id": "st-" + uuid.uuid4().hex[:8],
                "text": text,
                "tags": tags or [],
                "weight": float(weight),
                "protected": bool(protected),
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "last_hit": time.strftime("%Y-%m-%d %H:%M"),
            }
            data.append(item)
            evicted = []
            # 写满后按权重淘汰最老的（同权重先淘汰老的）
            while len(data) > STABLE_CAP:
                pool = [x for x in data if not x.get("protected")] or data
                victim = min(pool, key=lambda x: (float(x.get("weight", 1.0)), x.get("at", "")))
                data.remove(victim)
                evicted.append(victim)
                self.log(f"warn: 稳定区超过 {STABLE_CAP} 条，淘汰 {victim['text'][:30]}")
            _save(self.stable, data)
            return {"item": item, "evicted": evicted, "count": len(data)}

    def stable_list(self):
        return _load(self.stable, [])

    def stable_hit(self, sid):
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                if x.get("id") == sid:
                    x["weight"] = round(float(x.get("weight", 1.0)) + 0.2, 2)
                    x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                    _save(self.stable, data)
                    return x
        return None

    # ---------- 待办 ----------
    def todo_add(self, text, due=""):
        from .timeparse import normalize
        text = self._check(text, 200, "待办")
        with self._locked():
            data = _load(self.todo, [])
            item = {
                "id": "td-" + uuid.uuid4().hex[:8],
                "text": text,
                "due": normalize(due) or due,
                "done": False,
                "at": time.strftime("%Y-%m-%d %H:%M"),
            }
            data.append(item)
            _save(self.todo, data)
            return item

    def todo_list(self, include_done=False):
        data = _load(self.todo, [])
        return data if include_done else [x for x in data if not x.get("done")]

    def todo_done(self, tid):
        with self._locked():
            data = _load(self.todo, [])
            for x in data:
                if x.get("id") == tid:
                    x["done"] = True
                    x["done_at"] = time.strftime("%Y-%m-%d %H:%M")
                    _save(self.todo, data)
                    return x
        return None

    # ---------- 归档块 ----------
    def block_add(self, summary, tags=None, source=""):
        summary = self._check(summary, 2000, "块")
        bid = "blk-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        blocks = []
        if len(summary) > 800:
            blocks = [
                {"id": bid, "summary": summary[:600] + "…", "tags": tags or [], "source": source,
                 "time": time.strftime("%Y-%m-%d %H:%M"), "split": True},
                {"id": bid + "-b", "summary": "…" + summary[600:], "tags": tags or [], "source": source,
                 "time": time.strftime("%Y-%m-%d %H:%M"), "split": True},
            ]
        else:
            blocks = [{"id": bid, "summary": summary, "tags": tags or [], "source": source,
                       "time": time.strftime("%Y-%m-%d %H:%M")}]
        with self._locked():
            for b in blocks:
                _save(self.blocks / f"{b['id']}.json", b)
        return blocks[0]

    def block_list(self):
        return [_load(p, {}) for p in sorted(self.blocks.glob("*.json"))]

    # ---------- 注入 ----------
    def inject(self, query="", max_tokens=800):
        budget = max(120, int(max_tokens)) * 2
        stable = sorted(self.stable_list(), key=lambda x: -float(x.get("weight", 1.0)))
        todos = self.todo_list()
        hits = []
        if query:
            q = _norm(query)
            grams = {q[i:i + 2] for i in range(len(q) - 1)} if len(q) > 1 else {q}
            for b in self.block_list():
                blob = _norm(b.get("summary", "") + " " + " ".join(map(str, b.get("tags") or [])))
                if any(g in blob for g in grams):
                    hits.append(b)
        parts, used = [], 0

        def add(title, lines, ratio=0.5):
            nonlocal used
            if not lines:
                return
            cap = int(budget * ratio)
            seg, seg_len = [], 0
            for ln in lines:
                room = min(cap - seg_len, budget - used - len(title) - 2)
                if room <= 0:
                    break
                seg.append(ln[:max(1, room - 1)] + ("…" if len(ln) > room else ""))
                seg_len += len(ln) + 1
            if seg:
                block = title + "\n" + "\n".join(seg)
                parts.append(block)
                used += len(block)

        add("【稳定记忆】", [f"- {x['text']}" for x in stable], 0.5)
        add("【待办】", [f"- {x['text']}" + (f"（截止 {x['due']}）" if x.get("due") else "")
                        for x in todos], 0.3)
        add("【相关归档】", [f"- {b.get('summary', '')}" for b in hits[:3]], 0.3)
        if not parts:
            return "【元记忆】\n（没有可靠记忆，不要编造）"
        return "\n\n".join(parts)

    # ---------- 快照 ----------
    def snapshot(self):
        import shutil
        dst = self.snapshots / ("snap-" + time.strftime("%Y%m%d-%H%M%S"))
        dst.mkdir(parents=True, exist_ok=True)
        for p in (self.stable, self.todo):
            if p.exists():
                shutil.copy2(p, dst / p.name)
        if self.blocks.exists():
            shutil.copytree(self.blocks, dst / "blocks", dirs_exist_ok=True)
        snaps = sorted([x for x in self.snapshots.iterdir() if x.is_dir()])
        for old in snaps[:-SNAPSHOT_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        return dst

    def restore(self, snap):
        import shutil
        src = Path(snap)
        if not src.exists():
            raise FileNotFoundError(snap)
        for p in (self.stable, self.todo):
            if (src / p.name).exists():
                shutil.copy2(src / p.name, p)
        if (src / "blocks").exists():
            shutil.copytree(src / "blocks", self.blocks, dirs_exist_ok=True)
        return {"ok": True, "from": str(src)}
