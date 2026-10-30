# dsh-memory-blocks

> 给 AI 装上"分层记忆"：重要的事不忘，琐事自动淡忘。

## 这是什么

`dsh-memory-blocks` 是一套**分层记忆工具**，用来替代"整段聊天历史全塞进上下文"的做法。

它把对话整理成四层，每轮只注入几百 token：

| 层 | 内容 | 特点 |
| --- | --- | --- |
| **稳定区** | 重要事实（身份、偏好、约定、长期项目） | 永久保留，不衰减 |
| **待办** | 承诺、未完成的事、时间点 | 过期自动归档 |
| **临时重要** | 当前会话的关键决定 | 会话结束清空 |
| **滚动关键词** | 最近 N 条的摘要钩子 | 自动淘汰 |

## 为什么需要它

- 聊得越久，上下文越长 → 回复变慢、变贵、最后撑爆
- 重要的事（"我是律师，在邹城"）会和闲聊一起被冲淡
- 待办记不住
- 自动压缩会丢细节，而且不可控

## 核心设计

```
写入时重（后台慢慢建块、打标、维护）
读取时轻（每轮只注入 200~800 token）
```

### 分块

每 20 轮或换话题时切一块，生成：

```json
{
  "id": "block-2026-10-31-001",
  "summary": "讨论分层记忆方案，决定先做稳定区+动态尾部的最小版",
  "tags": {
    "topic": "上下文管理",
    "objects": ["DSH", "QQ机器人"],
    "conclusion": "采用分层记忆",
    "type": "decision",
    "synonyms": ["记忆分块", "RAG"]
  },
  "source": "blocks/2026-10-31-001.md",
  "time": "2026-10-31 04:44"
}
```

### 检索

- 关键词命中 → 精准
- 向量相似度 → 兜底
- 原文指针 → 需要细节时回查

## 安装

```bash
pip install -r requirements.txt
```

或直接当脚本用，无第三方依赖（标准库实现）。

## 快速开始

```bash
# 初始化
python -m memblocks.cli init

# 添加重要事实（永久）
python -m memblocks.cli stable add "用户在邹城做律师" --tags 身份,地域

# 添加待办
python -m memblocks.cli todo add "给每日视频加字幕" --due 2026-11-01

# 记录一块对话（摘要 + 标签）
python -m memblocks.cli block add --summary "讨论记忆架构" --topic 上下文管理 --type decision

# 生成注入文本（给 LLM 用）
python -m memblocks.cli inject --query "记忆怎么做的" --max-tokens 800

# 健康检查（只读）
python -m memblocks.cli janitor --dry-run

# 自动维护（低风险修复）
python -m memblocks.cli janitor
```

## 自动维护（memory janitor）

| 检查 | 自动处理 |
| --- | --- |
| 待办过期 | 归档 |
| 孤儿引用 | 标记 |
| 重复标签 | 合并到受控词表 |
| 区块过大 | 拆分 |
| 稳定事实过多 | 告警（不自动改） |

每次运行：先快照 → 最多改 10 处 → 输出审计日志 → 支持回滚。

## 目录结构

```
memories/
  stable.md        重要事实
  todo.json        待办
  recent.jsonl     滚动关键词
  blocks/          归档块
  snapshots/       维护前快照
```

## 成本

| 动作 | token |
| --- | --- |
| 建块 + 打标 | 300～500 / 块 |
| 每轮注入 | 200～800 |
| 维护 | 0（纯规则） |

对比全量历史，节省 90% 以上上下文。

## 适用场景

- 长期陪聊 / 陪伴型 AI
- 个人助理（记住你的偏好和待办）
- 工程对话（跨会话延续项目）

## 不适用

- 单次问答
- 一次性任务

## 许可证

MIT

## 人设自动转重要（接入即生效）

人格设定直接写进稳定区，**永久保护、不参与淘汰**，每轮 inject 排在最前面：

```bash
# 从文件导入（推荐）
python -m memblocks.cli persona set --file persona.md

# 或直接写
python -m memblocks.cli persona set "你是小鲸，一只蓝发鲸鱼娘……"
```

输出顺序固定为：

```
【人设】
【稳定记忆】
【待办】
【最近】
【相关归档】
```

人设放在最前，保证缓存前缀稳定，不会每轮抖动。

## 接入自检

`init` 会检查人设是否已导入：

```bash
python -m memblocks.cli init
# {"ok": true, "persona": false, "hint": "未检测到人设。建议先导入：..."}
```

没设置人设时会直接给出提示命令，避免"装了但没生效"。

## 短期记忆：待办过期自动删除

待办就是短期记忆，可以随时在聊天里加：

```bash
python -m memblocks.cli todo add "明天下午给客户回电话" --due 2026-11-01
```

维护程序（janitor）会：

1. 过期当天的待办 → 标记完成
2. 超过 `--purge-days`（默认 3 天）→ **自动删除**，不留垃圾

```bash
python -m memblocks.cli janitor              # 自动维护
python -m memblocks.cli janitor --dry-run    # 只看不改
python -m memblocks.cli doctor               # 只读体检
```

## 人物事实：谁会留下，谁会淡忘

关于人的信息单独存一层，带权重：

```bash
# 主人 / 管理员 → 自动永久保护
python -m memblocks.cli fact add --text "生日是 5 月 20 日" --entity "主人"

# 路人 → 默认不保护，会随时间衰减
python -m memblocks.cli fact add --text "生日是 3 月 3 日" --entity "张三"
```

规则：

| 对象 | 行为 |
| --- | --- |
| 主人 / 管理员 / 我 | `protected: true`，永不淡忘 |
| 其他人 | 权重 1.0 起，每次维护 ×0.85，低于 0.15 自动删除 |
| 再被提到 | `fact hit --id <id>` 权重 +0.5，越常提越牢 |

主人名单在 `memories/config.json` 的 `owner_names` 里，可以自己改。

注入时会在【关于人物】里列出当前权重最高的事实。

## 自动提取（候选制）

从聊天记录里抽人物事实，先入候选队列，你确认后入库：

```bash
python -m memblocks.cli extract --file chat.txt
# 或
python -m memblocks.cli extract --text "我的生日是5月20日。张三是我同事。"

python -m memblocks.cli fact pending          # 看候选
python -m memblocks.cli fact approve --id pfact-xxx
python -m memblocks.cli fact reject --id pfact-xxx
```

规则：

- 「我 / 主人 / 管理员」相关 → 自动 `protected`
- 其他人 → 进候选，默认不保护，会随时间衰减
- 同一事实去重

内置规则抽取（生日、职业、位置、关系、偏好），不依赖模型；
如需更准，`memblocks/extract.py` 里留了 `EXTRACT_PROMPT`，可接任意 OpenAI 兼容接口。
