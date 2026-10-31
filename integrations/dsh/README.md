# 在 DSH 里接入 memblocks

memblocks 本体是 Python，DSH 插件是 Node。两者通过 **HTTP 接口**对接，
不需要把 Python 装进 DSH，也不需要改 DSH 源码。

## 启动接口

```bash
python -m memblocks.cli --root "~/.memlite" serve --port 8765
```

```
GET  /health
POST /inject   {"query": "...", "max_tokens": 800}   → {"text": "..."}
POST /stable   {"text": "...", "tags": ["身份"], "weight": 1.0}
POST /todo     {"text": "...", "due": "下周三"}
POST /block    {"summary": "...", "tags": ["记忆"]}
POST /review   {"query": "..."}
GET  /memories
GET  /star
```

## 方式一：DSH 里加一个 shell 工具（最简单）

在 DSH 的工具配置里加：

```bash
curl -s -X POST http://127.0.0.1:8765/inject \
  -H "Content-Type: application/json" \
  -d '{"query":"{{用户这句话}}","max_tokens":800}'
```

把返回的 `text` 拼到系统提示末尾即可。

## 方式二：Node 客户端（写在 DSH 插件里）

`memblocks-client.mjs` 是一个零依赖的小客户端：

```js
import { MemoryClient } from "./memblocks-client.mjs";

const mem = new MemoryClient("http://127.0.0.1:8765");

// 注入前：拿记忆
const text = await mem.inject(userMessage, 800);

// 回复后：复习被用到的记忆（可选）
await mem.review(userMessage);

// 记录待办
await mem.addTodo("明天给客户回电话", "明天");
```

在 DSH 插件里，把它接到 `on_llm_request` 之类的钩子上：

```js
export function apply(ctx) {
  const mem = new MemoryClient("http://127.0.0.1:8765");
  ctx.on("llm/request", async (req) => {
    const text = await mem.inject(req.prompt || "", 800);
    if (text) req.systemPrompt = (req.systemPrompt || "") + "\n\n" + text;
  });
}
```

> 钩子名以你当前 DSH 版本的 API 为准；这里只演示调用方式。

## 方式三：AstrBot（已在用）

仓库根目录的 `astrbot_adapter/` 是 AstrBot 插件模板，
`on_llm_request` 注入、`on_llm_response` 复习，路径改一下就能装。

## 安全

接口默认只监听 `127.0.0.1`，不对外暴露。要跨机器用请自己加鉴权和 HTTPS：

```bash
python -m memblocks.cli serve --host 0.0.0.0 --port 8765   # 不推荐直接这样开
```

## 为什么不直接做 DSH 插件

DSH 插件要跟着宿主 API 走，版本一变就可能失效。
HTTP 接口是稳定的，任何语言、任何宿主都能接——DSH、n8n、脚本、命令行都行。
