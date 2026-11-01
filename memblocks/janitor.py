"""维护：清理过期待办、合并重复稳定项、执行上限淘汰。"""
import json
from datetime import date

from .store import STABLE_CAP, _norm, _save


class Janitor:
    MAX_CHANGES = 10

    def __init__(self, store, dry_run=False, purge_days=3):
        self.s = store
        self.dry_run = dry_run
        self.purge_days = purge_days
        self.changes = 0
        self.report = {}

    def _due(self, s):
        try:
            return date.fromisoformat(s)
        except Exception:
            return None

    def run(self):
        r = {"stable": 0, "todos": 0, "expired": 0, "purged": 0,
             "stable_merged": 0, "stable_trimmed": 0, "warnings": [],
             "cap_note": "上限 100 条在 stable_add 写入时执行，janitor 只做兜底"}
        if not self.dry_run:
            r["snapshot"] = str(self.s.snapshot())

        today = date.today()
        todos = self.s.todo_list(True)

        # 1) 过期未完成 → 标记 done（同一次运行内就能继续走清理）
        changed = 0
        for t in todos:
            d = self._due(t.get("due", ""))
            if d and d < today and not t.get("done"):
                t["done"] = True
                t["done_at"] = today.isoformat()
                changed += 1
        r["expired"] = changed

        # 2) 已完成的、超过 purge_days 的 → 归档后删除
        #    没有截止日期的待办：按遗忘曲线衰减
        keep, drop = [], []
        faded = 0
        for t in todos:
            d = self._due(t.get("due", ""))
            if t.get("done") and d and (today - d).days >= self.purge_days:
                drop.append(t)
            elif not d and not t.get("done"):
                # 没有截止日期：按遗忘曲线衰减，淡到 0.2 以下才消失
                decayed = None
                try:
                    from datetime import datetime
                    base = t.get("last_decay") or (t.get("at", "") or "")[:10]
                    days = max(0, (today - datetime.strptime(base, "%Y-%m-%d").date()).days)
                    w = float(t.get("weight", 1.0)) * (0.85 ** days)
                    t["weight"] = round(w, 3)
                    t["last_decay"] = today.isoformat()
                    decayed = w
                except Exception:
                    pass
                if decayed is not None and decayed < 0.2:
                    drop.append(t)
                    continue
                if decayed is not None:
                    faded += 1
                keep.append(t)
            else:
                keep.append(t)
        r["purged"] = len(drop)
        r["todos_decayed"] = faded

        # 3) 近期事件：超过 ttl 就清掉
        gone = self.s.event_purge()
        r["events_purged"] = len(gone)
        if gone and not self.dry_run:
            with open(self.s.archive, "a", encoding="utf-8") as f:
                for ev in gone:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")

        if (changed or drop or faded) and not self.dry_run:
            if drop:
                with open(self.s.archive, "a", encoding="utf-8") as f:
                    for t in drop:
                        f.write(json.dumps(t, ensure_ascii=False) + "\n")
            _save(self.s.todo, keep)
            self.changes += 1

        # 稳定区：近重复合并（精确命中 或 相似度 >= 0.82，同 tag）
        import difflib
        kept, exact, fuzzy = [], 0, 0
        for x in self.s.stable_list():
            tx = _norm(x.get("text"))
            tag = (x.get("tags") or [""])[0]
            hit = None
            for y in kept:
                ty = _norm(y.get("text"))
                if tx and tx == ty:
                    hit, exact = y, exact + 1
                    break
                if x.get("protected") or y.get("protected"):
                    continue
                if len(tx) < 12 or not tag or (y.get("tags") or [""])[0] != tag:
                    continue
                if abs(len(tx) - len(ty)) > max(len(tx), len(ty)) * 0.6:
                    continue
                if difflib.SequenceMatcher(None, tx, ty).ratio() >= 0.82:
                    hit, fuzzy = y, fuzzy + 1
                    break
            if hit is not None:
                hit["weight"] = round(min(9.0, float(hit.get("weight", 1.0))
                                          + float(x.get("weight", 1.0)) * 0.25), 2)
            else:
                kept.append(x)
        r["stable_merged"] = exact + fuzzy
        r["stable_fuzzy_merged"] = fuzzy
        if (exact or fuzzy) and not self.dry_run:
            _save(self.s.stable, kept)
            self.s.log(f"janitor: 合并重复 {exact + fuzzy} 条（精确 {exact} / 相似 {fuzzy}）")
            self.changes += 1

        # 稳定区：超上限按权重淘汰
        stable = self.s.stable_list()
        evicted = 0
        if len(stable) > STABLE_CAP:
            pool = stable
            while len(pool) > STABLE_CAP:
                victim = min(pool, key=lambda x: (float(x.get("weight", 1.0)), x.get("at", "")))
                if victim.get("protected"):
                    break
                pool.remove(victim)
                evicted += 1
            if evicted and not self.dry_run:
                _save(self.s.stable, pool)
                self.s.log(f"warn: 稳定区超限，淘汰 {evicted} 条")
                self.changes += 1
        r["stable_trimmed"] = evicted
        if len(stable) >= STABLE_CAP:
            r["warnings"].append(f"稳定区 {len(stable)}/{STABLE_CAP}，接近或达到上限")

        r.update(stable=len(self.s.stable_list()), todos=len(self.s.todo_list()))
        if self.changes >= self.MAX_CHANGES:
            r["stopped_early"] = True
        return r
