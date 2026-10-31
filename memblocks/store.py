"""三层记忆存储：稳定区（有上限、按权重淘汰）/ 待办 / 归档块。"""
import json
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

STABLE_CAP = 100
SNAPSHOT_KEEP = 3


def _load(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        bad = p.with_suffix(p.suffix + ".bad-" + time.strftime("%Y%m%d-%H%M%S"))
        try:
            p.rename(bad)
        except Exception:
            pass
        raise RuntimeError(f"记忆文件损坏，已备份到 {bad.name}，请检查后重新初始化")


def _save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(text):
    import re
    t = (text or "").strip().lower().replace("号", "日").replace("是", "").replace("为", "")
    t = re.sub(r"[\s\u3000]+", "", t)
    return re.sub(r"[，。,.、；;：:！!？?\-—_()（）\[\]【】]", "", t)


_PROC_LOCK = threading.RLock()


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
        self.config = self.root / "config.json"

    # ---------- 基础 ----------
    def init(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.blocks.mkdir(exist_ok=True)
            self.snapshots.mkdir(exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"无法创建数据目录 {self.root}：{e.strerror or e}。请换一个有写权限的路径（--root）")
        for p, d in ((self.stable, []), (self.todo, [])):
            if not p.exists():
                _save(p, d)
        try:
            if not self.archive.exists():
                self.archive.write_text("", encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"无法写入 {self.root}：{e.strerror or e}。请检查目录权限")
        cfg = self.config_get()
        has_data = bool(_load(self.stable, [])) or bool(_load(self.todo, [])) or any(self.blocks.glob("*.json"))
        first_run = ("first_run" not in cfg) and not has_data
        if first_run:
            cfg.setdefault("star_enabled", False)
            cfg["first_run"] = True
            self.config_set(**cfg)
        return {"ok": True, "root": str(self.root), "stable_cap": STABLE_CAP,
                "first_run": first_run, "star_enabled": bool(cfg.get("star_enabled"))}

    def config_get(self):
        return _load(self.config, {})

    def config_set(self, **kw):
        cfg = self.config_get()
        cfg.update(kw)
        _save(self.config, cfg)
        return cfg

    def log(self, msg):
        with open(self.audit, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with _PROC_LOCK:
            fh = open(self.lock, "a+")
            try:
                try:
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                except ImportError:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                except OSError:
                    # 同进程多线程争锁时 Windows 会报 deadlock avoided，
                    # 进程内已有 RLock 保序，这里直接放行
                    pass
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
            # 不再静默截断：超长直接报错，调用方自己决定怎么处理
            raise ValueError(f"{kind} 超长：{len(t)} > {limit} 字，请先拆分")
        return t

    # ---------- 稳定区 ----------
    def stable_add(self, text, tags=None, weight=1.0, protected=False, permanent=False,
                   display_only=False):
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
                "permanent": bool(permanent),
                "display_only": bool(display_only),
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "last_hit": time.strftime("%Y-%m-%d %H:%M"),
            }
            data.append(item)
            evicted = []
            # 写满后按权重淘汰最老的（同权重先淘汰老的）
            while len(data) > STABLE_CAP:
                pool = [x for x in data if not x.get("protected") and not x.get("permanent")
                        and not x.get("display_only")] or data
                victim = min(pool, key=lambda x: (float(x.get("weight", 1.0)), x.get("at", "")))
                data.remove(victim)
                evicted.append(victim)
                self.log(f"warn: 稳定区超过 {STABLE_CAP} 条，淘汰 {victim['text'][:30]}")
            _save(self.stable, data)
            return {"item": item, "evicted": evicted, "count": len(data)}

    def stable_pin(self, sid, on=True):
        """把某条记忆设为恒星（永久）或取消。"""
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                if x.get("id") == sid:
                    x["permanent"] = bool(on)
                    _save(self.stable, data)
                    return x
        return None

    def stable_display_only(self, sid, on=True):
        """把记忆设为"仅展示"：进星图，但不注入上下文。"""
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                if x.get("id") == sid:
                    x["display_only"] = bool(on)
                    _save(self.stable, data)
                    return x
        return None

    def stable_list(self):
        return _load(self.stable, [])

    def stable_hit(self, sid):
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                if x.get("id") == sid:
                    x["weight"] = round(min(9.0, float(x.get("weight", 1.0)) + 0.2), 2)
                    x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                    _save(self.stable, data)
                    return x
        return None

    def review(self, query=""):
        """复习：把与查询相关的稳定项加权 +0.2（显式调用，inject 不改权重）。"""
        q = _norm(query or "")
        grams = {q[i:i + 2] for i in range(len(q) - 1)} if len(q) > 1 else ({q} if q else set())
        boosted = 0
        with self._locked():
            data = _load(self.stable, [])
            for x in data:
                blob = _norm(x.get("text", "") + " " + " ".join(map(str, x.get("tags") or [])))
                if not grams or any(g in blob for g in grams):
                    x["weight"] = round(min(9.0, float(x.get("weight", 1.0)) + 0.2), 2)
                    x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                    boosted += 1
            if boosted:
                _save(self.stable, data)
        return boosted

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
        summary = (summary or "").strip()
        if not summary:
            raise ValueError("块 不能为空")
        bid = "blk-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:10]
        # 先按 800 字切块，再逐块校验，不先截断
        chunks = [summary[i:i + 800] for i in range(0, len(summary), 800)]
        blocks = []
        for i, c in enumerate(chunks):
            c = self._check(c, 2000, "块")
            blocks.append({
                "id": bid if i == 0 else f"{bid}-{i}",
                "summary": c + ("…" if i < len(chunks) - 1 else ""),
                "tags": tags or [],
                "source": source,
                "time": time.strftime("%Y-%m-%d %H:%M"),
                "split": len(chunks) > 1,
            })
        with self._locked():
            for b in blocks:
                _save(self.blocks / f"{b['id']}.json", b)
        return blocks[0]

    def block_list(self):
        return [_load(p, {}) for p in sorted(self.blocks.glob("*.json"))]

    # ---------- 注入 ----------
    @staticmethod
    def _window(line, query, room):
        """超预算时，围绕查询命中的位置取窗口，而不是从头截。"""
        if room <= 1 or len(line) <= room:
            return line
        q = _norm(query or "")
        grams = {q[i:i + 2] for i in range(len(q) - 1)} if len(q) > 1 else {q}
        pos = -1
        low = _norm(line)
        for g in grams:
            if g and g in low:
                pos = low.find(g)
                break
        if pos < 0:
            return line[:room - 1] + "…"
        start = max(0, pos - room // 3)
        end = min(len(line), start + room - 1)
        return ("…" if start > 0 else "") + line[start:end] + ("…" if end < len(line) else "")

    def inject(self, query="", max_tokens=800):
        budget = max(120, int(max_tokens)) * 2
        stable = sorted([x for x in self.stable_list() if not x.get("display_only")],
                        key=lambda x: -float(x.get("weight", 1.0)))
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
                seg.append(self._window(ln, query, max(2, room)))
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
        dst = self.snapshots / ("snap-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:10])
        dst.mkdir(parents=True, exist_ok=True)
        for p in self.root.glob("*.json*"):
            if p.is_file() and not p.name.startswith(".lock") and ".bad-" not in p.name:
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
        for p in src.glob("*.json*"):
            if p.is_file() and ".bad-" not in p.name:
                shutil.copy2(p, self.root / p.name)
        if (src / "blocks").exists():
            shutil.copytree(src / "blocks", self.blocks, dirs_exist_ok=True)
        return {"ok": True, "from": str(src)}
