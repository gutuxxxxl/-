import argparse
import json
from pathlib import Path

from .store import Store, STABLE_CAP
from .janitor import Janitor


def main():
    try:
        return _main()
    except (ValueError, RuntimeError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(2)


def _main():
    ap = argparse.ArgumentParser(prog="memlite", description="三层记忆（稳定/待办/归档）")
    ap.add_argument("--root", default=str(Path.home() / ".memlite"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    ini = sub.add_parser("init")
    ini.add_argument("--star", dest="star", action="store_true", default=None,
                     help="首次安装时直接启用记忆星图")
    ini.add_argument("--no-star", dest="star", action="store_false", default=None)
    ini.add_argument("--dsh", dest="dsh", action="store_true", default=None,
                     help="首次安装时标记接入 DSH")
    ini.add_argument("--no-dsh", dest="dsh", action="store_false", default=None)

    cfg = sub.add_parser("config")
    cfg.add_argument("--star", choices=["on", "off"])
    cfg.add_argument("--dsh", choices=["on", "off"])
    cfg.add_argument("--show", action="store_true")

    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default="127.0.0.1")

    d = sub.add_parser("dsh")
    d.add_argument("--json", action="store_true", help="输出机器可读的集成信息")

    s = sub.add_parser("stable")
    s.add_argument("action", choices=["add", "list", "hit"])
    s.add_argument("text", nargs="?")
    s.add_argument("--tags", default="")
    s.add_argument("--weight", type=float, default=1.0)
    s.add_argument("--id", default="")

    t = sub.add_parser("todo")
    t.add_argument("action", choices=["add", "list", "done"])
    t.add_argument("text", nargs="?")
    t.add_argument("--due", default="")
    t.add_argument("--id", default="")

    b = sub.add_parser("block")
    b.add_argument("action", choices=["add", "list"])
    b.add_argument("--summary", default="")
    b.add_argument("--tags", default="")

    stp = sub.add_parser("star")
    stp.add_argument("--out", default="memory-map.html")

    i = sub.add_parser("inject")
    i.add_argument("--query", default="")
    i.add_argument("--max-tokens", type=int, default=800)

    j = sub.add_parser("janitor")
    j.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    st = Store(args.root)
    init_info = st.init()

    def tags(v):
        return [x.strip() for x in v.split(",") if x.strip()]

    if args.cmd == "init":
        import sys
        info = init_info
        if info["first_run"]:
            print("\n=== memblocks 首次安装 ===")
            print("三层记忆已就绪：稳定区 / 待办 / 归档")
            print("\n另外它还有一个「记忆星图」：把记忆画成会变暗的星，")
            print("点一下就重新变亮，用来直观看到哪些事快被忘记了。")
            choice = getattr(args, "star", None)
            if choice is None:
                if sys.stdin.isatty():
                    ans = input("\n是否启用记忆星图？[y/N] ").strip().lower()
                    choice = ans in ("y", "yes", "是", "1")
                else:
                    choice = False
                    print("\n（非交互环境，默认不启用；之后可用 init --star 或 config --star on）")
            # 第二个问题：是否接入 DSH
            dsh_choice = getattr(args, "dsh", None)
            if dsh_choice is None:
                if sys.stdin.isatty():
                    ans2 = input("是否接入 DSH（DeepSeek Harness）？会把记忆注入到 DSH 的对话里 [y/N] ").strip().lower()
                    dsh_choice = ans2 in ("y", "yes", "是", "1")
                else:
                    dsh_choice = False
            st.config_set(star_enabled=bool(choice), dsh_enabled=bool(dsh_choice), first_run=False)
            print("\n星图：" + ("已启用，运行 python -m memblocks.cli star --out memory-map.html" if choice else "未启用，可用 config --star on 开启"))
            if dsh_choice:
                print("DSH：已标记接入。运行 python -m memblocks.cli dsh 看接入方式")
            else:
                print("DSH：未接入。之后可用 config --dsh on 开启")
        print(json.dumps({"root": str(st.root), "cap": STABLE_CAP,
                          "star_enabled": bool(st.config_get().get("star_enabled")),
                          "dsh_enabled": bool(st.config_get().get("dsh_enabled"))}, ensure_ascii=False))
    elif args.cmd == "stable":
        if args.action == "add":
            r = st.stable_add(args.text, tags(args.tags), args.weight)
            print(json.dumps({"item": r["item"], "merged": r.get("merged", False),
                              "evicted": [x["text"] for x in r.get("evicted", [])],
                              "count": r.get("count")}, ensure_ascii=False, indent=2))
        elif args.action == "hit":
            print(json.dumps(st.stable_hit(args.id), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(st.stable_list(), ensure_ascii=False, indent=2))
    elif args.cmd == "todo":
        if args.action == "add":
            print(json.dumps(st.todo_add(args.text, args.due), ensure_ascii=False, indent=2))
        elif args.action == "done":
            print(json.dumps(st.todo_done(args.id), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(st.todo_list(True), ensure_ascii=False, indent=2))
    elif args.cmd == "block":
        if args.action == "add":
            print(json.dumps(st.block_add(args.summary, tags(args.tags)), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(st.block_list(), ensure_ascii=False, indent=2))
    elif args.cmd == "config":
        if args.star:
            st.config_set(star_enabled=(args.star == "on"))
        if args.dsh:
            st.config_set(dsh_enabled=(args.dsh == "on"))
        cfgd = st.config_get()
        print(json.dumps(cfgd, ensure_ascii=False, indent=2))
    elif args.cmd == "serve":
        from .serve import serve
        httpd = serve(st.root, args.port, args.host)
        print(f"memblocks HTTP 接口: http://{args.host}:{args.port}  (root={st.root})")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    elif args.cmd == "dsh":
        info = {
            "enabled": bool(st.config_get().get("dsh_enabled")),
            "root": str(st.root),
            "inject_cmd": f'python -m memblocks.cli --root "{st.root}" inject --query "<用户这句话>" --max-tokens 800',
            "steps": [
                "1. 在 DSH 里加一个 shell 工具，执行上面的 inject_cmd，把输出拼到系统提示末尾",
                "2. 回复后可选执行 review --query，让被用到的记忆加权",
                "3. 每天跑一次 janitor，清理过期待办、合并重复项",
            ],
        }
        print(json.dumps(info, ensure_ascii=False, indent=2) if args.json else
              "DSH 接入方式：\n" + "\n".join(info["steps"]) +
              "\n\n要执行的命令：\n  " + info["inject_cmd"] +
              "\n\n当前状态：" + ("已启用" if info["enabled"] else "未启用（config --dsh on 开启）"))
    elif args.cmd == "star":
        from .star import render
        if not st.config_get().get("star_enabled"):
            print("提示：星图未启用，现在是临时生成；要长期用请先 config --star on")
        print(render(st, args.out))
    elif args.cmd == "inject":
        print(st.inject(args.query, args.max_tokens))
    elif args.cmd == "janitor":
        print(json.dumps(Janitor(st, args.dry_run).run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
