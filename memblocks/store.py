import json
import time
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
        if not self.config.exists():
            _save(self.config, {"owner_names": ["主人", "我", "管理员"]})
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
    def stable_add(self, text: str, tags=None, protected: bool = False):
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
    def todo_add(self, text: str, due: str = ""):
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
    def recent_add(self, text: str, limit: int = 30):
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

    def fact_add(self, text: str, entity: str = "", tags=None, protected=None):
        if protected is None:
            protected = entity.strip() in self.owner_names()
        data = _load(self.facts, [])
        item = {
            "id": "fact-" + time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:4],
            "text": text,
            "entity": entity,
            "tags": tags or [],
            "protected": bool(protected),
            "score": 1.0,
            "hits": 1,
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "last_hit": time.strftime("%Y-%m-%d %H:%M"),
        }
        data.append(item)
        _save(self.facts, data)
        return item

    def fact_list(self):
        return _load(self.facts, [])

    def fact_hit(self, fid: str):
        data = _load(self.facts, [])
        for x in data:
            if x.get("id") == fid:
                x["score"] = min(5.0, x.get("score", 1.0) + 0.5)
                x["hits"] = x.get("hits", 1) + 1
                x["last_hit"] = time.strftime("%Y-%m-%d %H:%M")
                _save(self.facts, data)
                return x
        return None

    def fact_decay(self, rate: float = 0.85, floor: float = 0.15):
        """非保护事实按次衰减，低于阈值删除。返回 (剩余, 删除数)。"""
        data = _load(self.facts, [])
        keep, dropped = [], 0
        for x in data:
            if x.get("protected"):
                keep.append(x)
                continue
            x["score"] = round(float(x.get("score", 1.0)) * rate, 3)
            if x["score"] < floor:
                dropped += 1
            else:
                keep.append(x)
        _save(self.facts, keep)
        return len(keep), dropped

    def fact_top(self, limit: int = 10):
        return sorted(self.fact_list(), key=lambda x: -float(x.get("score", 0)))[:limit]

    # ---------- 归档块 ----------
    def block_add(self, summary: str, topic: str = "", type_: str = "note",
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
        q = (query or "").lower()
        scored = []
        for b in self.block_list():
            blob = json.dumps(b, ensure_ascii=False).lower()
            score = sum(1 for ch in set(q) if ch.strip() and ch in blob)
            if score:
                scored.append((score, b))
        scored.sort(key=lambda x: -x[0])
        return [b for _, b in scored[:limit]]

    # ---------- 注入 ----------
    def inject(self, query: str = "", max_tokens: int = 800):
        parts = []
        per = self.persona()
        if per:
            parts.append("【人设】\n" + per["text"])
        stable = [x for x in self.stable_list() if not x.get("kind") == "persona"]
        if stable:
            parts.append("【稳定记忆】\n" + "\n".join(f"- {x['text']}" for x in stable[-30:]))
        todos = self.todo_list()
        if todos:
            parts.append("【待办】\n" + "\n".join(
                f"- {x['text']}" + (f"（截止 {x['due']}）" if x.get("due") else "") for x in todos[:15]))
        recent = self.recent_list()
        if recent:
            parts.append("【最近】\n" + "\n".join(f"- {x['text']}" for x in recent[-15:]))
        facts = self.fact_top(12)
        if facts:
            lines = []
            for x in facts:
                who = x.get("entity") or "某人"
                lines.append(f"- {who}：{x['text']}")
            parts.append("【关于人物】\n" + "\n".join(lines))
        hits = self.block_search(query) if query else []
        if hits:
            parts.append("【相关归档】\n" + "\n".join(f"- {b.get('summary','')}" for b in hits))
        text = "\n\n".join(parts)
        # 粗略按 4 字符 ≈ 1 token 截断
        limit = max_tokens * 4
        return text[:limit]

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
