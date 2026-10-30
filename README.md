# memblocks

> 三层记忆：稳定区 / 待办 / 归档。给长期对话用的最小实现。

## 这是什么

一个零依赖的 Python 记忆包，用来替代「把整段聊天历史塞进上下文」：

| 层 | 内容 | 规则 |
| --- | --- | --- |
| **稳定区** | 长期事实（身份、偏好、约定） | 上限 100 条，写满按权重淘汰最老的，并写告警 |
| **待办** | 短期任务 | 带截止日期，过期归档后删除 |
| **归档块** | 对话摘要 | 超 800 字自动拆块 |

没有人物事实、没有时间线、没有自动抽取——那三块修了几轮仍有 bug，不如不做。

## 安装

纯标准库，Python 3.10+，不用 pip。

```bash
git clone https://github.com/gutuxxxxl/-.git memblocks
cd memblocks
python -m memblocks.cli init
```

## 用法

```bash
# 稳定区
python -m memblocks.cli stable add "我在邹城做律师" --tags 身份
python -m memblocks.cli stable add "人设：你是小鲸" --weight 9
python -m memblocks.cli stable list

# 待办（支持「下周三」「一个月后」「十二月二十八号」）
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

> 注意：淘汰发生在 `stable_add` 写入时；`janitor` 只在异常情况下兜底，
> 所以它的报告里 `stable_trimmed` 通常是 0，这不是 bug。

## 超长直接报错

单条超过上限（稳定/待办 200 字、块 2000 字）不再静默截断，直接抛 `ValueError`。

```bash
$ python -m memblocks.cli stable add "$(python -c 'print("x"*201)')"
{"error": "稳定记忆 超长：201 > 200 字，请先拆分"}
```

## 快照

每次 `janitor` 前自动快照，保留**最近 3 份**，目录名带 uuid 防同秒覆盖。

```python
store.restore("memories/snapshots/snap-20261031-060000-ab12")
```

## 健壮性

- JSON 损坏不静默：改名为 `.bad-时间戳` 并抛错
- 快照包含全部数据文件
- 块先按 800 字切分，再逐块校验
- 支持中文数字日期：「十二月二十八号」→ 2026-12-28
- 写入加文件锁（Windows `msvcrt` / Linux `fcntl`）

## 测试

```bash
python -m unittest discover -s tests -v
# 37 tests OK
```

覆盖：去重合并、上限淘汰、人设保护、过期待办归档、dry-run、块拆分、
注入预算、相对时间、JSON 损坏、快照完整性。

## 目录

```
memblocks/
  store.py      三层 + 上限淘汰 + 锁 + 快照
  janitor.py    清理 / 合并 / 淘汰
  cli.py        命令行
  timeparse.py  相对时间
tests/
  test_lite.py    基础功能（16）
  test_stress.py  同秒 300 块 / 5000 字 / 4 进程 / 坏 JSON / 快照保留（10）
  test_edge.py    中文路径 / emoji / 快照并发 / 恢复 / CLI 退出码（11）
```

## 许可证

MIT
