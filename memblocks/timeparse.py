"""相对时间归一化：把「上周三」「三个月前」在写入时就换算成绝对日期。"""
import re
from datetime import date, timedelta

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _num(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    return CN_NUM.get(s, 0)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def normalize(text: str, ref: date | None = None) -> str:
    """返回归一化后的日期 YYYY-MM-DD；解析失败返回空串。"""
    ref = ref or date.today()
    t = (text or "").strip()
    if not t:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return t

    # 今天/昨天/前天/大前天/明天/后天
    simple = {"今天": 0, "今日": 0, "昨天": -1, "昨日": -1, "前天": -2, "大前天": -3,
              "明天": 1, "后天": 2, "大后天": 3}
    for k, off in simple.items():
        if k in t:
            return (ref + timedelta(days=off)).isoformat()

    # X 天/周/个月/年 前
    m = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*(天|周|个?月|年)前", t)
    if m:
        n = _num(m.group(1))
        unit = m.group(2)
        if unit == "天":
            return (ref - timedelta(days=n)).isoformat()
        if unit == "周":
            return (ref - timedelta(weeks=n)).isoformat()
        if "月" in unit:
            return (ref - timedelta(days=30 * n)).isoformat()
        if unit == "年":
            return (ref - timedelta(days=365 * n)).isoformat()

    # 上周三 / 这周三 / 上上周三
    m = re.search(r"(上上周|上周|这周|本周|下周)([一二三四五六日天])", t)
    if m:
        which, wd = m.group(1), m.group(2)
        base = _monday(ref)
        offset_week = {"上上周": -2, "上周": -1, "这周": 0, "本周": 0, "下周": 1}[which]
        return (base + timedelta(weeks=offset_week, days=WEEKDAY[wd])).isoformat()

    # 上个月 X 号
    m = re.search(r"上个?月\s*(\d+|[一二三四五六七八九十]+)\s*[日号]", t)
    if m:
        n = _num(m.group(1))
        y, mo = ref.year, ref.month - 1
        if mo == 0:
            y, mo = y - 1, 12
        return date(y, mo, min(n, 28)).isoformat()

    # X 月 X 日/号
    m = re.search(r"(\d{1,2}|[一二三四五六七八九十]+)\s*月\s*(\d{1,2}|[一二三四五六七八九十]+)\s*[日号]", t)
    if m:
        mo, dd = _num(m.group(1)), _num(m.group(2))
        if 1 <= mo <= 12 and 1 <= dd <= 31:
            try:
                d = date(ref.year, mo, dd)
                if d > ref + timedelta(days=1):
                    d = date(ref.year - 1, mo, dd)
                return d.isoformat()
            except ValueError:
                return ""

    # 去年 / 前年
    if "去年" in t:
        return date(ref.year - 1, ref.month, ref.day).isoformat()
    if "前年" in t:
        return date(ref.year - 2, ref.month, ref.day).isoformat()

    return ""
