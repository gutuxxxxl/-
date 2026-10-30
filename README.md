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
- TF-IDF（字符二元组）相似度 → 兜底，纯标准库实现，无 numpy
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

## 类人记忆：复习、冲突、元记忆、巩固

### 1. 间隔复习（7 天 / 30 天）

事实不再"一存就慢慢死"，而是按复习节奏走：

| 距上次被想起 | 权重变化 |
| --- | --- |
| ≤ 7 天 | 不变（还在短期记忆里） |
| 7～30 天 | ×0.95 |
| > 30 天 | ×0.70 |

每次 `inject` 被选中，权重 +0.2，并刷新 `last_hit`——相当于"又想起了一次"。

### 2. 冲突检测

同一人物 + 同一类别，新事实自动覆盖旧的：

```
旧：张三 职业是老师   → superseded
新：张三 职业是律师   → 生效
```

旧记录不删，标记 `superseded`，可追溯。

### 3. 元记忆

检索不到内容时，注入会明确说：

```
【元记忆】
（关于这个问题没有可靠记忆，不要编造）
```

### 4. 巩固

`janitor` 每次会合并重复事实，保留权重最高的一条，避免同一个信息存多份。

### 5. 显著性

生日、职业、关系这类重要类别，初始权重 1.5，普通偏好 1.0。

## 情绪与时间线

### 情绪权重

每条事实/事件带 `emotion`：

```json
{"valence": -0.9, "arousal": 0.9, "label": "高唤醒-负"}
```

- 权重 = 基础值 × (1 + 0.6 × arousal)
- **闪光灯记忆**：arousal > 0.7 的事件，30 天内不衰减
- 关键词表在 `memblocks/emotions.py`，可替换成模型打分

### 时间线

事件单独存 `events.jsonl`：

```bash
python -m memblocks.cli event add --when 2026-10-30 --actor 主人 --do 决定 --object "做分层记忆插件"

python -m memblocks.cli timeline --from 2026-10-01 --to 2026-10-31
python -m memblocks.cli timeline --entity 张三
```

注入时会附上【最近事件】（最近 5 条），按时间正序。

### 设计原则

只记**有意义的节点**：决定、承诺、冲突、转折、情绪高峰。
日常琐事不记，避免退化成聊天记录。

## 相对时间归一化（写入时就换算）

记忆里不存"上周三"，存具体日期：

```bash
python -m memblocks.cli event add --when "上周三" --actor 张三 --do 签了 --object "一份合同"
# 实际存：{"when": "2026-10-21", "when_raw": "上周三"}
```

支持的说法：

| 说法 | 结果（以 2026-10-31 为参考） |
| --- | --- |
| 昨天 / 前天 / 大前天 | 2026-10-30 / 29 / 28 |
| 上周三 | 2026-10-21 |
| 这周五 / 下周一 | 2026-10-30 / 2026-11-02 |
| 三个月前 | 2026-07-31（自然月） |
| 10月20日 | 2026-10-20 |
| 上个月5号 | 2026-09-05 |

命令行也能单独测：

```bash
python -m memblocks.cli when "上周三" "三个月前" --ref 2026-10-31
```

原始说法保留在 `when_raw` 里，方便回溯"当时是怎么说的"。

## 三个修复（0.2 起）

- `inject` 改为**纯读**，不再偷偷加权重
- 复习单独命令：`review --query "..."`（被检索到的事实 +0.2）
- 注入按查询相关过滤：查不到就只给权重前 3，避免无关事实泄漏
- 写操作加**文件锁**，多进程同时写不会互相覆盖

## 测试

```bash
python -m unittest discover -s tests -v
# 11 tests OK
```

覆盖：人设保护、冲突覆盖、inject 只读、review 加权、间隔衰减、
闪光灯记忆、janitor dry-run、过期清理、抽取审批、相对时间。

## AstrBot 适配（模板，未安装）

`astrbot_adapter/` 里是一层薄适配：

- `on_llm_request` → 把 `inject` 文本拼到系统提示末尾
- `on_llm_response` → 调 `review` 更新权重

需要改 `CONFIG` 里的两个路径（memories 目录、memblocks 库目录），
然后放到 AstrBot 的 `data/plugins/` 下启用。**仓库里的这份没有安装。**

## 情绪词表的边界

「起诉」「坐牢」「欠债」这类词已从极端负面里移出：

| 文本 | 判定 |
| --- | --- |
| 张三被起诉了 | 当事人-负（arousal 0.8） |
| 今天讲起诉流程 | 职业中性（arousal 0.25） |

判据是出现「我 / 本人 / 被」才按当事人视角处理。
更准的做法是让模型打标，`emotions.py` 里留了替换点。

## 预算与优先级（0.3 起）

`inject(query, max_tokens)` 现在真的按预算裁剪，顺序固定：

```
人设 → 重要（protected）→ 稳定记忆 → 待办 → 最近事件 → 关于人物 → 最近 → 相关归档
```

- 预算 = `max_tokens × 2` 字符（粗略折算）
- **保护性内容（人设、重要事实）优先，不会因为查询不相关被筛掉**
- 稳定区不再静默截断 30 条，而是按预算装，装不下会少给后面层级

## 修过的坑（0.3）

- Linux 上锁失效：`msvcrt` 换 `fcntl` 回退
- 写入时重复事实：同 entity+text 直接加权，不再追加
- `pending_add` 传单个 dict 会崩：已兼容
- 衰减时间解析失败静默：改为告警并记录
- 过期待办直接删：改为先写 `todo_archive.jsonl` 再删
- janitor 快照没生成：现在每次自动快照，并新增 `restore` 恢复
- 大块只报不拆：超 800 字自动拆成两块
- 检索把字段名当关键词：只索引 summary/topic/objects/synonyms，同义词双倍权重
- CLI 默认目录跟当前路径走：改为 `~/.memblocks`

## 并发回归测试

```bash
python -m unittest tests.test_concurrency -v
```

4 个进程各写 60 条事实，断言最终 240 条一条不少、且无重复。

- Windows：`msvcrt` 文件锁
- Linux：`fcntl.flock` 回退

本地 Windows 实测通过（3.9s / 240 条）。
