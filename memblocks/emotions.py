"""情绪打分：valence（正负）与 arousal（强弱）。规则版，可替换为模型。"""

HIGH_NEG = ("去世", "死亡", "车祸", "离婚", "被骗", "打架", "住院", "手术", "自杀", "家暴", "失业", "分手")
# 法律职业高频词：单独出现不该算极端情绪，只有当事人视角才算
LEGAL = ("起诉", "坐牢", "欠债", "判刑", "打官司", "被诉", "被告", "案子", "开庭")
HIGH_POS = ("结婚", "升职", "考上", "中奖", "生了", "买房", "录取", "加薪", "和好")
MID_NEG = ("吵架", "辞职", "搬家", "生病", "迟到", "吵架")
MID_POS = ("旅行", "聚会", "礼物", "表白")


def score(text: str):
    t = text or ""
    for w in LEGAL:
        if w in t:
            personal = any(x in t for x in ("我", "主人", "本人", "自己", "被"))
            if personal:
                return {"valence": -0.7, "arousal": 0.8, "label": "当事人-负"}
            return {"valence": 0.0, "arousal": 0.25, "label": "职业中性"}
    for w in HIGH_NEG:
        if w in t:
            return {"valence": -0.9, "arousal": 0.9, "label": "高唤醒-负"}
    for w in HIGH_POS:
        if w in t:
            return {"valence": 0.9, "arousal": 0.9, "label": "高唤醒-正"}
    for w in MID_NEG:
        if w in t:
            return {"valence": -0.5, "arousal": 0.6, "label": "中唤醒-负"}
    for w in MID_POS:
        if w in t:
            return {"valence": 0.5, "arousal": 0.6, "label": "中唤醒-正"}
    return {"valence": 0.0, "arousal": 0.1, "label": "平静"}
