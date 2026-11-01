# -*- coding: utf-8 -*-
"""稳定区的近重复合并：说法相近的记忆合成一条。"""
import json
from difflib import SequenceMatcher

from .store import _norm, _save


def dedupe_store(store, threshold=0.82):
    items = store.stable_list()
    kept, removed = [], []
    for x in items:
        if x.get("protected"):
            kept.append(x)
            continue
        tx = _norm(x.get("text"))
        tag = (x.get("tags") or [""])[0]
        hit = None
        if len(tx) >= 12 and tag:
            for y in kept:
                if y.get("protected") or (y.get("tags") or [""])[0] != tag:
                    continue
                ty = _norm(y.get("text"))
                if abs(len(tx) - len(ty)) > max(len(tx), len(ty)) * 0.6:
                    continue
                if SequenceMatcher(None, tx, ty).ratio() >= threshold:
                    hit = y
                    break
        if hit is None:
            kept.append(x)
            continue
        # 留信息量更大的那条，权重合并
        if len(tx) > len(_norm(hit.get("text"))):
            hit["text"] = x.get("text")
        hit["weight"] = min(9.0, round(float(hit.get("weight", 1.0)) + float(x.get("weight", 1.0)) * 0.3, 2))
        hit["merged_from"] = int(hit.get("merged_from") or 0) + 1
        removed.append({"merged_into": hit.get("id"), **x})

    if removed:
        root = getattr(store, "root", None)
        if root:
            try:
                with open(root / "archive.jsonl", "a", encoding="utf-8") as f:
                    for r in removed:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except Exception:
                pass
        _save(store.stable, kept)
    return {"merged": len(removed), "before": len(items), "after": len(kept)}
