"""规则式人物事实抽取（可选 LLM 增强）。

从对话文本里抽取「关于人物」的候选事实，先入待确认队列，
确认后才写进长期记忆。主人相关自动标记为保护。
"""
import re

OWNER_WORDS = ("我", "主人", "管理员", "老板")

PATTERNS = [
    # 生日
    (r"(?:我|主人|管理员)?的?生日(?:是|在)?\s*([0-9]{1,2}\s*月\s*[0-9]{1,2}\s*[日号])", "生日"),
    # 职业
    (r"(?:我|主人|管理员)?(?:在[^，。,\n]{0,8})?(?:是|做|当|从事)([^，。,\n]{0,10}?(?:律师|医生|老师|程序员|设计师|会计|警察|工程师|老板|学生))", "职业"),
    # 位置（要求地名后缀，且排除小区/门口这类非地名）
    (r"(?:我|主人|管理员)?(?:在|住在|来自)([^，。,\n]{1,8}?(?:市|县|区|镇|省|城|州))", "位置"),
    # 关系
    (r"([\u4e00-\u9fa5]{2,4})(?:是|叫)(?:我|主人)的?(同事|朋友|客户|家人|同学|合伙人)", "关系"),
    # 偏好（要求 2~10 字，排除指代词）
    (r"(?:我|主人|管理员)?(不喜欢|喜欢|讨厌)([^，。,\n]{2,10})", "偏好"),
]


def _entity_of(line: str) -> str:
    for w in OWNER_WORDS:
        if re.search(r"(?:^|[，。,\s])" + re.escape(w) + r"(?:的|是|在|喜欢|不喜欢|讨厌|生日)", line):
            return "主人"
    m = re.match(r"([\u4e00-\u9fa5]{2,4}?)(?:的|是|叫)", line.strip())
    if m and m.group(1) not in OWNER_WORDS:
        return m.group(1)
    return ""


def extract(text: str):
    """返回候选事实列表。"""
    out = []
    for line in re.split(r"[。！？\n]", text):
        line = line.strip()
        if not line:
            continue
        entity = _entity_of(line)
        for pattern, kind in PATTERNS:
            m = re.search(pattern, line)
            if not m:
                continue
            value = m.group(1).strip()
            if kind == "生日":
                value = re.sub(r"\s+", "", value)
            if kind == "生日":
                text_out = f"生日是 {value}"
            elif kind == "职业":
                text_out = f"职业是{value}"
            elif kind == "位置":
                if any(bad in value for bad in ("小区", "门口", "家", "店", "公司", "学校", "医院", "路上")):
                    continue
                text_out = f"在{value}"
            elif kind == "关系":
                who = entity or "某人"
                text_out = f"{who}的关系：{m.group(2)}"
            else:
                verb = m.group(1)
                val = m.group(2)
                if any(bad in val for bad in ("这个", "那个", "上次", "这次", "这样", "那种")):
                    continue
                text_out = f"{verb}{val}"
            out.append({
                "text": text_out,
                "entity": entity or "",
                "kind": kind,
                "protected": entity in ("主人",) or (not entity and "主人" in line),
                "source": line[:120],
            })
    # 去重
    seen, uniq = set(), []
    for x in out:
        key = (x["entity"], x["text"])
        if key not in seen:
            seen.add(key)
            uniq.append(x)
    return uniq


EXTRACT_PROMPT = """从下面的对话里抽取关于人物的长期事实，输出 JSON 数组。
要求：
- 每条包含 text（事实）、entity（人物名，主人/管理员写"主人"）、kind（生日/职业/位置/关系/偏好）
- 只抽长期有效的信息，闲聊、情绪、一次性事件不要
- 不确定的不要编

对话：
{text}
"""
