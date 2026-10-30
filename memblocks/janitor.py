from datetime import date, datetime

from .store import Store


class Janitor:
    """记忆维护：只读报告 + 低风险自动修复。"""

    MAX_CHANGES = 10

    def __init__(self, store: Store, dry_run: bool = False, purge_days: int = 3):
        self.s = store
        self.dry_run = dry_run
        self.purge_days = purge_days
        self.changes = 0
        self.report = {
            "blocks": 0, "stable": 0, "todos": 0, "recent": 0,
            "expired_todos": 0, "orphans": 0, "duplicate_tags": [],
            "large_blocks": 0, "warnings": [],
        }

    def _change(self, msg: str):
        if self.changes >= self.MAX_CHANGES:
            self.report["warnings"].append("达到单次修改上限，停止：" + msg)
            return False
        self.changes += 1
        if not self.dry_run:
            self.s.log(msg)
        return True

    def _parse_due(self, due: str):
        try:
            return datetime.strptime(due, "%Y-%m-%d").date()
        except Exception:
            return None

    def consolidate(self):
        """巩固：合并重复事实，保留权重最高的那条。"""
        from .store import _load, _save
        data = _load(self.s.facts, [])
        best = {}
        merged = 0
        from .store import _norm_text
        for x in data:
            key = (x.get("entity", ""), _norm_text(x.get("text", "")))
            if key not in best or float(x.get("score", 0)) > float(best[key].get("score", 0)):
                if key in best:
                    merged += 1
                best[key] = x
            else:
                merged += 1
        if merged and not self.dry_run:
            _save(self.s.facts, list(best.values()))
        return merged

    def run(self):
        if not self.dry_run:
            self.report["snapshot"] = str(self.s.snapshot())
        blocks = self.s.block_list()
        stable = self.s.stable_list()
        todos = self.s.todo_list()
        recent = self.s.recent_list()

        self.report.update(blocks=len(blocks), stable=len(stable), todos=len(todos), recent=len(recent))

        # 1. 过期待办 → 归档
        today = date.today()
        keep, expired = [], []
        for t in todos:
            d = self._parse_due(t.get("due", ""))
            if d and d < today and not t.get("done"):
                expired.append(t)
            else:
                keep.append(t)
        self.report["expired_todos"] = len(expired)
        from .store import _save
        if expired and not self.dry_run:
            if self._change(f"归档过期待办 {len(expired)} 条"):
                for t in expired:
                    t["done"] = True
                _save(self.s.todo, keep + expired)

        # 1b. 短期记忆：过期待办超过 purge_days 天后自动删除
        all_todos = self.s.todo_list(True)
        alive = []
        purged_items = []
        for t in all_todos:
            d = self._parse_due(t.get("due", ""))
            if t.get("done") and d and (today - d).days >= self.purge_days:
                purged_items.append(t)
                continue
            alive.append(t)
        self.report["purged_todos"] = len(purged_items)
        if purged_items and not self.dry_run:
            import json as _json
            with open(self.s.root / "todo_archive.jsonl", "a", encoding="utf-8") as f:
                for t in purged_items:
                    f.write(_json.dumps(t, ensure_ascii=False) + "\n")
            if self._change(f"删除过期 {self.purge_days} 天的待办 {len(purged_items)} 条（已归档）"):
                _save(self.s.todo, alive)

        # 2. 孤儿引用
        for b in blocks:
            src = (b.get("source") or "").strip()
            if src and not (self.s.root / src).exists():
                self.report["orphans"] += 1

        # 3. 重复标签（简单按 topic 统计）
        topics = {}
        for b in blocks:
            t = (b.get("tags") or {}).get("topic", "").strip()
            if t:
                topics[t] = topics.get(t, 0) + 1
        for t, n in sorted(topics.items(), key=lambda x: -x[1]):
            if n > 1:
                self.report["duplicate_tags"].append({"topic": t, "count": n})

        # 4. 超大块
        split = 0
        for b in blocks:
            if len(b.get("summary", "")) > 800 and not self.dry_run:
                from .store import _save
                head, tail = b["summary"][:600], b["summary"][600:]
                b["summary"] = head + "…"
                b["split"] = True
                _save(self.s.blocks / f"{b['id']}.json", b)
                new = dict(b)
                new["id"] = b["id"] + "-b"
                new["summary"] = "…" + tail
                _save(self.s.blocks / f"{new['id']}.json", new)
                split += 1
            elif len(b.get("summary", "")) > 800:
                split += 1
        self.report["large_blocks"] = split

        # 5. 稳定事实膨胀
        if len(stable) > 50:
            self.report["warnings"].append(f"稳定事实 {len(stable)} 条，超过建议上限 50，建议合并")

        # 6. 人物事实衰减（非保护）
        if not self.dry_run:
            left, dropped = self.s.fact_decay()
            self.report["facts_left"] = left
            self.report["facts_decayed"] = dropped
        else:
            self.report["facts_left"] = len(self.s.fact_list())
            self.report["facts_decayed"] = 0

        # 7. 巩固：合并重复事实
        consolidated = self.consolidate()
        self.report["consolidated"] = consolidated
        if consolidated and not self.dry_run:
            self._change(f"巩固合并重复事实 {consolidated} 条")

        if self.changes >= self.MAX_CHANGES:
            self.report["stopped_early"] = True
        if not self.dry_run and self.changes:
            self.report["changes"] = self.changes
        return self.report
