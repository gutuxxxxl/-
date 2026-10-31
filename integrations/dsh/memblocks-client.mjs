// memblocks HTTP 客户端（Node 18+，零依赖）
// 用法：
//   import { MemoryClient } from "./memblocks-client.mjs";
//   const mem = new MemoryClient("http://127.0.0.1:8765");
//   const text = await mem.inject("用户这句话", 800);

export class MemoryClient {
  constructor(base = "http://127.0.0.1:8765") {
    this.base = base.replace(/\/$/, "");
  }

  async _post(path, body) {
    const r = await fetch(this.base + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  async _get(path) {
    const r = await fetch(this.base + path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.text();
  }

  health() {
    return this._get("/health");
  }

  /** 取注入文本；失败返回空串，保证不打断对话 */
  async inject(query, maxTokens = 800) {
    try {
      const d = await this._post("/inject", { query, max_tokens: maxTokens });
      return d.text || "";
    } catch {
      return "";
    }
  }

  addStable(text, tags = [], weight = 1.0) {
    return this._post("/stable", { text, tags, weight });
  }

  addTodo(text, due = "") {
    return this._post("/todo", { text, due });
  }

  addBlock(summary, tags = []) {
    return this._post("/block", { summary, tags });
  }

  review(query) {
    return this._post("/review", { query });
  }

  memories() {
    return this._get("/memories");
  }

  starHtml() {
    return this._get("/star");
  }
}
