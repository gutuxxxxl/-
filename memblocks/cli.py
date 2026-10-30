import argparse
import json

from .store import Store
from .janitor import Janitor


def main():
    ap = argparse.ArgumentParser(prog="memblocks", description="分层记忆工具")
    ap.add_argument("--root", default="memories")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    per = sub.add_parser("persona")
    per.add_argument("action", choices=["set", "show"])
    per.add_argument("text", nargs="?")
    per.add_argument("--file", default="")

    s = sub.add_parser("stable")
    s.add_argument("action", choices=["add", "list"])
    s.add_argument("text", nargs="?")
    s.add_argument("--tags", default="")

    t = sub.add_parser("todo")
    t.add_argument("action", choices=["add", "list", "done"])
    t.add_argument("text", nargs="?")
    t.add_argument("--due", default="")
    t.add_argument("--index", type=int, default=-1)

    b = sub.add_parser("block")
    b.add_argument("action", choices=["add", "list", "search"])
    b.add_argument("--summary", default="")
    b.add_argument("--topic", default="")
    b.add_argument("--type", dest="type_", default="note")
    b.add_argument("--conclusion", default="")
    b.add_argument("--objects", default="")
    b.add_argument("--synonyms", default="")
    b.add_argument("--source", default="")
    b.add_argument("--query", default="")

    r = sub.add_parser("recent")
    r.add_argument("action", choices=["add", "list"])
    r.add_argument("text", nargs="?")

    i = sub.add_parser("inject")
    i.add_argument("--query", default="")
    i.add_argument("--max-tokens", type=int, default=800)

    d = sub.add_parser("doctor")
    d.add_argument("--purge-days", type=int, default=3)

    j = sub.add_parser("janitor")
    j.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    st = Store(args.root)
    st.init()

    def tags(v):
        return [x.strip() for x in v.split(",") if x.strip()]

    if args.cmd == "init":
        info = st.init()
        print(json.dumps(info, ensure_ascii=False))
        if info.get("hint"):
            print(info["hint"])
    elif args.cmd == "stable":
        if args.action == "add":
            print(json.dumps(st.stable_add(args.text, tags(args.tags)), ensure_ascii=False))
        else:
            print(json.dumps(st.stable_list(), ensure_ascii=False, indent=2))
    elif args.cmd == "persona":
        if args.action == "set":
            text = args.text or ""
            if args.file:
                from pathlib import Path as _P
                text = _P(args.file).read_text(encoding="utf-8")
            print(json.dumps(st.set_persona(text), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(st.persona(), ensure_ascii=False, indent=2))
    elif args.cmd == "todo":
        if args.action == "add":
            print(json.dumps(st.todo_add(args.text, args.due), ensure_ascii=False))
        elif args.action == "done":
            print(json.dumps(st.todo_done(args.index), ensure_ascii=False))
        else:
            print(json.dumps(st.todo_list(True), ensure_ascii=False, indent=2))
    elif args.cmd == "block":
        if args.action == "add":
            print(json.dumps(st.block_add(
                args.summary, args.topic, args.type_, tags(args.objects),
                args.conclusion, tags(args.synonyms), args.source), ensure_ascii=False, indent=2))
        elif args.action == "search":
            print(json.dumps(st.block_search(args.query), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(st.block_list(), ensure_ascii=False, indent=2))
    elif args.cmd == "recent":
        if args.action == "add":
            st.recent_add(args.text)
            print("ok")
        else:
            print(json.dumps(st.recent_list(), ensure_ascii=False, indent=2))
    elif args.cmd == "inject":
        print(st.inject(args.query, args.max_tokens))
    elif args.cmd == "doctor":
        from .janitor import Janitor as _J
        print(json.dumps(_J(st, True).run(), ensure_ascii=False, indent=2))
    elif args.cmd == "janitor":
        if not args.dry_run:
            snap = st.snapshot()
            print("snapshot:", snap)
        print(json.dumps(Janitor(st, args.dry_run).run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
