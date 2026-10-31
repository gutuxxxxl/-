import argparse
import json
from pathlib import Path

from .store import Store, STABLE_CAP
from .janitor import Janitor


def main():
    try:
        return _main()
    except ValueError as e:
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

    cfg = sub.add_parser("config")
    cfg.add_argument("--star", choices=["on", "off"])
    cfg.add_argument("--show", action="store_true")

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
            st.config_set(star_enabled=bool(choice), first_run=False)
            print("\n星图：" + ("已启用，运行 python -m memblocks.cli star --out memory-map.html" if choice else "未启用，可用 config --star on 开启"))
        print(json.dumps({"root": str(st.root), "cap": STABLE_CAP,
                          "star_enabled": bool(st.config_get().get("star_enabled"))}, ensure_ascii=False))
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
        cfgd = st.config_get()
        print(json.dumps(cfgd, ensure_ascii=False, indent=2))
    elif args.cmd == "star":
        from .star import render
        print(render(st, args.out))
    elif args.cmd == "inject":
        print(st.inject(args.query, args.max_tokens))
    elif args.cmd == "janitor":
        print(json.dumps(Janitor(st, args.dry_run).run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
