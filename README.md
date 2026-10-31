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
# 48 tests OK
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

## 性能基线（1000 块）

```bash
python bench.py
```

| 指标 | 数值 |
| --- | --- |
| 建 1000 块 | 0.57s（0.6 ms/块） |
| 首次 `block_list` | 1.56s（冷读 1000 个文件） |
| `inject` 平均 | 76 ms（p95 80 ms） |
| `janitor` | 0.64s |
| 磁盘 | 0.50 MB |
| 块文件数 | 1000 |

结论：

- 1000 块以内，注入 76 ms，完全够用
- 冷读 `block_list` 是瓶颈（文件系统元数据），热读后很快
- 超过 3000 块建议按年月归档，否则冷读会到 4~5 秒

这个基线顺带测出一个 bug：块 ID 后缀只有 4 位十六进制，
1000 个块里撞了 6 个（994 而不是 1000）。已改为 10 位。

## 注入按命中位置取窗口

长块被预算截断时，不再从头截：

- 命中关键词 → 围绕命中位置取窗口（前 1/3、后 2/3）
- 没命中 → 正常从头截

这样「块拆开能搜到，但注不进去」的问题不会出现。

## 日期支持的写法

| 写法 | 结果（ref=2026-10-31） |
| --- | --- |
| 12月28号 / 12月28日 / 12月28 | 2026-12-28 |
| 二十八号 / 28号 | 2026-10-28 |
| 十二月二十八 | 2026-12-28 |

## 记忆星图（会遗忘的那种）

![记忆星图](docs/star.png)

```bash
python -m memblocks.cli star --out memory-map.html
```

打开 HTML 即可，无依赖、无服务器。

**它不是静态图**：

- 每颗星按遗忘曲线变暗、变小（`R = exp(-天数 / τ)`，τ 随权重变大）
- 越久没被想起，越暗，还会慢慢往外飘
- **点一下 = 提到它**：权重 +0.6，星立刻变亮复位
- 「复习全部」= 一次想起所有事
- 底部可以调时间流速（0.05 ~ 2 天/秒），看着记忆一个个暗下去

颜色：稳定区青色、待办琥珀、归档紫色。连线表示共享关键词。

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

## 性能基线（1000 块）

```bash
python bench.py
```

| 指标 | 数值 |
| --- | --- |
| 建 1000 块 | 0.57s（0.6 ms/块） |
| 首次 `block_list` | 1.56s（冷读 1000 个文件） |
| `inject` 平均 | 76 ms（p95 80 ms） |
| `janitor` | 0.64s |
| 磁盘 | 0.50 MB |
| 块文件数 | 1000 |

结论：

- 1000 块以内，注入 76 ms，完全够用
- 冷读 `block_list` 是瓶颈（文件系统元数据），热读后很快
- 超过 3000 块建议按年月归档，否则冷读会到 4~5 秒

这个基线顺带测出一个 bug：块 ID 后缀只有 4 位十六进制，
1000 个块里撞了 6 个（994 而不是 1000）。已改为 10 位。

## 注入按命中位置取窗口

长块被预算截断时，不再从头截：

- 命中关键词 → 围绕命中位置取窗口（前 1/3、后 2/3）
- 没命中 → 正常从头截

这样「块拆开能搜到，但注不进去」的问题不会出现。

## 日期支持的写法

| 写法 | 结果（ref=2026-10-31） |
| --- | --- |
| 12月28号 / 12月28日 / 12月28 | 2026-12-28 |
| 二十八号 / 28号 | 2026-10-28 |
| 十二月二十八 | 2026-12-28 |

## 记忆星图

![记忆星图](docs/star.png)

把三层记忆画成一张可交互的星图（单文件 HTML，无依赖）：

```bash
python -m memblocks.cli star --out memory-map.html
# 打开 memory-map.html 即可，无需服务器
```

- 稳定区：青色（大小 = 权重）
- 待办：琥珀色
- 归档：紫色
- 连线：共享关键词（2 字片段）
- 交互：悬停看详情、滚轮缩放、拖拽旋转

适合放到面板里当"记忆概览"，也适合发截图。

## 首次安装会问你一句

第一次运行 `init` 时，会先介绍三层记忆，再问要不要启用记忆星图：

```
=== memblocks 首次安装 ===
三层记忆已就绪：稳定区 / 待办 / 归档

另外它还有一个「记忆星图」：把记忆画成会变暗的星，
点一下就重新变亮，用来直观看到哪些事快被忘记了。

是否启用记忆星图？[y/N]
```

- 非交互环境（脚本、CI）不会卡住，默认不启用并提示后续怎么开
- 也可以直接用参数：`init --star` / `init --no-star`
- 之后随时改：`config --star on|off`，`config --show` 看当前配置
- 选择记在 `config.json`，只问一次

### 引导的边界（都测过）

| 场景 | 行为 |
| --- | --- |
| 全新安装 | 询问一次 |
| 已有记忆的老用户升级 | **不再询问**，自动视为已启用过 |
| 非交互 / 脚本 | 不卡住，默认关闭并提示 |
| `--star` 与 `--no-star` 同时给 | 后者生效 |
| 配置文件损坏 | 报错退出（退出码 2），不静默重建 |
| 星图关闭时运行 star | 照常生成，但提示 `config --star on` |
| 重复 init | 不再打印横幅 |
