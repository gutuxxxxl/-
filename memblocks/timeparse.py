"""相对时间归一化：写入时把「下周三」「三个月前」换成绝对日期。"""
import re
from datetime import date, timedelta

CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
      "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
NUM = r"(\d{1,2}|[一二三四五六七八九十]+)"


def _n(s):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN:
        return CN[s]
    if "十" in s:
        head, _, tail = s.partition("十")
        tens = CN.get(head, 1) if head else 1
        ones = CN.get(tail, 0) if tail else 0
        return tens * 10 + ones
    return 0


def _shift_months(d, n):
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    days = [31, 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, days))


def normalize(text, ref=None):
    ref = ref or date.today()
    t = (text or "").strip()
    if not t:
        return ""

    # 2026-1-5
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", t):
        y, m, d = [int(x) for x in t.split("-")]
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            return ""

    simple = {"今天": 0, "今日": 0, "昨天": -1, "昨日": -1, "前天": -2, "大前天": -3,
              "明天": 1, "后天": 2, "大后天": 3,
              "一会": 0, "一会儿": 0, "待会": 0, "待会儿": 0, "马上": 0, "马上去": 0}
    for k, off in sorted(simple.items(), key=lambda x: -len(x[0])):
        if k in t:
            return (ref + timedelta(days=off)).isoformat()

    # X 天/周/个月/年 前|后
    m = re.search(NUM + r"\s*(天|周|个?月|年)(前|后|以后|之后)", t)
    if m:
        n, unit, direction = _n(m.group(1)), m.group(2), m.group(3)
        back = direction == "前"
        if unit == "天":
            return (ref - timedelta(days=n) if back else ref + timedelta(days=n)).isoformat()
        if unit == "周":
            return (ref - timedelta(weeks=n) if back else ref + timedelta(weeks=n)).isoformat()
        if "月" in unit:
            return _shift_months(ref, n if back else -n).isoformat()
        if unit == "年":
            try:
                return ref.replace(year=ref.year - n if back else ref.year + n).isoformat()
            except ValueError:
                return ref.replace(year=ref.year - n if back else ref.year + n, day=28).isoformat()

    # 上周三 / 这周三 / 下周三
    m = re.search(r"(上上周|上周|这周|本周|下周)([一二三四五六日天])", t)
    if m:
        base = ref - timedelta(days=ref.weekday())
        off = {"上上周": -2, "上周": -1, "这周": 0, "本周": 0, "下周": 1}[m.group(1)]
        return (base + timedelta(weeks=off, days=WD[m.group(2)])).isoformat()

    # X 月 X 日（后缀可省）
    m = re.search(NUM + r"\s*月\s*" + NUM + r"\s*(?:[日号])?", t)
    if m:
        mo, dd = _n(m.group(1)), _n(m.group(2))
        if 1 <= mo <= 12 and 1 <= dd <= 31:
            try:
                return date(ref.year, mo, dd).isoformat()
            except ValueError:
                return ""

    # 只有日：二十八号 / 28 日
    m = re.search(r"(?<!月)" + NUM + r"\s*(?:日|号)", t)
    if m:
        dd = _n(m.group(1))
        try:
            return date(ref.year, ref.month, dd).isoformat()
        except ValueError:
            return ""

    return ""
