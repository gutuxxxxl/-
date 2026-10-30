# memblocks-lite

> 三层记忆，够用就好。稳定区 / 待办 / 归档块。

这是 `dsh-memory-blocks` 的精简版：砍掉人物事实、时间线、自动抽取，
只保留能长期站住的内核。

## 三层

| 层 | 内容 | 规则 |
| --- | --- | --- |
| **稳定区** | 长期事实（身份、偏好、约定） | 上限 100 条，写满按权重淘汰最老的，并告警 |
| **待办** | 短期任务 | 带截止日期，过期归档后删除 |
| **归档块** | 对话摘要 | 超 800 字自动拆两块 |

## 为什么砍

v0.x 里的人物事实、时间线、规则抽取，三个功能各带出两条以上 bug，
修下去是补丁追补丁。砍掉之后，剩下的三层每一条都能说清楚行为边界。

## 安装

无第三方依赖，Python 3.10+。

```bash
git clone https://github.com/gutuxxxxl/-.git
cd -/lite
python -m memlite.cli init
```

## 用法

```bash
# 稳定区
python -m memblocks.cli stable add "我在邹城做律师" --tags 身份
python -m memblocks.cli stable add "人设：你是小鲸" --weight 9 --tags 人设
python -m memblocks.cli stable list

# 待办（截止日期支持「下周三」「一个月后」）
python -m memblocks.cli todo add "给客户回电话" --due 下周三
python -m memblocks.cli todo done --id td-xxxx

# 归档块
python -m memblocks.cli block add --summary "讨论分层记忆方案" --tags 上下文

# 生成注入文本
python -m memblocks.cli inject --query "记忆" --max-tokens 800

# 维护
python -m memblocks.cli janitor --dry-run
python -m memblocks.cli janitor
```

## 稳定区上限

写满 100 条后：

1. 新增照常写入
2. 淘汰**权重最低、时间最老**的一条
3. 写 warn 到 `audit.log`
4. `protected: true` 的人设不参与淘汰

不会直接拒绝写入——拒绝会让人当场卡住。

## 快照

每次 `janitor` 前自动快照，只保留**最近 3 份**。

```python
store.restore("memories/snapshots/snap-20261031-060000")
```

## 测试

```bash
python -m unittest discover -s tests -v
# 11 tests OK
```

覆盖：去重合并、上限淘汰、人设保护、过期待办归档、dry-run、
块拆分、注入预算、相对时间。

## 目录

```
memblocks/
  store.py      三层 + 上限淘汰 + 锁 + 快照
  janitor.py    清理 / 合并 / 淘汰
  cli.py        命令行
  timeparse.py  相对时间
tests/
  test_lite.py  11 个测试
```

## 不做什么

- 不抽人物事实（规则抽取覆盖不够，模型打标更合适）
- 不建时间线（事件层需要更多设计）
- 不自动从对话里抽内容（同上）

## 许可证

MIT
