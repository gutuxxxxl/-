"""轻量检索：字符二元组 + TF-IDF，纯标准库，无 numpy 依赖。"""
import math
import re
from collections import Counter


def tokens(text: str):
    t = re.sub(r"[^\w\u4e00-\u9fa5]+", "", (text or "").lower())
    if not t:
        return []
    if len(t) == 1:
        return [t]
    return [t[i:i + 2] for i in range(len(t) - 1)]


class TfIdf:
    def __init__(self, docs):
        """docs: list[(key, text)]"""
        self.keys = [k for k, _ in docs]
        self.tfs = [Counter(tokens(t)) for _, t in docs]
        df = Counter()
        for tf in self.tfs:
            for term in tf:
                df[term] += 1
        n = max(1, len(docs))
        self.idf = {term: math.log((1 + n) / (1 + c)) + 1 for term, c in df.items()}
        self.norms = []
        for tf in self.tfs:
            s = math.sqrt(sum((c * self.idf.get(t, 1)) ** 2 for t, c in tf.items())) or 1.0
            self.norms.append(s)

    def search(self, query, limit=3):
        q = Counter(tokens(query))
        if not q:
            return []
        scores = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            for term, c in q.items():
                if term in tf:
                    s += c * tf[term] * (self.idf.get(term, 1) ** 2)
            if s > 0:
                scores.append((s / self.norms[i], self.keys[i]))
        scores.sort(key=lambda x: -x[0])
        return [k for _, k in scores[:limit]]
