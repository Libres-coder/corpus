"""corpus CLI.

  corpus scan                      rebuild the artifact index (.corpus/index.json)
  corpus report [--json]           what is duplicate, broken, stale or orphaned
  corpus find "topic" [--limit N]  before writing a new doc: what already covers it?
  corpus dupes [--threshold 0.7]   near-duplicate pairs, with which one to keep
  corpus supersede OLD --by NEW    record that NEW replaced OLD
  corpus archive PATH              record that PATH is no longer truth
  corpus restore PATH              undo supersede/archive
  corpus retired                   list the recorded decisions
  corpus check [--strict]          gate: exit 1 on anything *incorrect*

Exit codes: 0 ok, 1 gate failure, 2 usage.
"""
import argparse
import json
import os
import sys

from . import report as reportmod
from . import scan as scanmod
from . import sim, status as statusmod

DEFAULT_IGNORE = ()


def _utf8():
    rec = getattr(sys.stdout, "reconfigure", None)
    if rec:
        try:
            rec(encoding="utf-8")
        except Exception:
            pass


def _index_path(repo):
    return os.path.join(repo, statusmod.STATE_DIR, "index.json")


def _save_index(repo, index):
    os.makedirs(os.path.join(repo, statusmod.STATE_DIR), exist_ok=True)
    with open(_index_path(repo), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=1, sort_keys=True)


def cmd_scan(repo, args):
    index = scanmod.scan(repo, args.glob, args.ignore)
    _save_index(repo, index)
    m = reportmod.metrics({"findings": [], "index": index,
                           "status": statusmod.load(repo)})
    print("indexed %d artifacts (%d chars, ~%d tokens) -> %s"
          % (m["artifacts"], m["chars"], m["reading_tokens"],
             os.path.relpath(_index_path(repo), repo)))
    return 0


def cmd_report(repo, args):
    result = reportmod.analyze(repo, status_data=statusmod.load(repo),
                               threshold=args.threshold, stale_days=args.stale_days)
    # report never writes into the scanned tree; `corpus scan` is the only writer.
    if args.json:
        _utf8()
        payload = {"metrics": reportmod.metrics(result),
                   "findings": result["findings"]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _utf8()
    print(reportmod.render(result, show_noise=args.noise))
    return 0


def cmd_find(repo, args):
    index = scanmod.scan(repo, args.glob, args.ignore)
    status_data = statusmod.load(repo)
    scored = []
    for rel in index["artifacts"]:
        text = scanmod.read_text(os.path.join(repo, rel))
        if text is None:
            continue
        scored.append((sim.score_against(args.query, text), rel))
    scored.sort(reverse=True)
    hits = [s for s in scored if s[0] > 0][:args.limit]
    if not hits:
        print("No artifact covers %r. A new document is justified." % args.query)
        return 0
    _utf8()
    print("Closest artifacts to %r:" % args.query)
    for score, rel in hits:
        rec = index["artifacts"][rel]
        st = statusmod.status_of(status_data, rel)
        print("  %.2f  %-4s %-6s %s  -  %s"
              % (score, st[:4], rec["kind"], rel, rec["title"]))
    top = hits[0][0]
    if top >= 0.6:
        print("\nExtend %s instead of writing a new document." % hits[0][1])
    elif top >= 0.3:
        print("\nRelated work exists; say in the new document what it adds.")
    else:
        print("\nOnly loosely related - a new document is reasonable.")
    return 0


def cmd_dupes(repo, args):
    index = scanmod.scan(repo, args.glob, args.ignore)
    result = {"findings": [], "index": index, "status": statusmod.load(repo)}
    exact = reportmod._exact_duplicates(index)
    near = reportmod._near_duplicates(index, args.threshold)
    _utf8()
    if not exact and not near:
        print("No duplicate artifacts at threshold %.2f." % args.threshold)
        return 0
    for f in exact:
        print("[exact] %s == %s" % (f["path"], f["other"]))
    for f in near:
        print("[%.2f] %s  ~  %s" % (f["score"], f["path"], f["other"]))
    print("\n%d exact, %d near-duplicate pair(s)." % (len(exact), len(near)))
    return 0


def cmd_supersede(repo, args):
    if not os.path.exists(os.path.join(repo, args.by)):
        return _err("replacement does not exist: %s" % args.by)
    ok, msg = statusmod.set_status(repo, args.old, "superseded", by=args.by)
    print(msg)
    return 0 if ok else 1


def cmd_archive(repo, args):
    ok, msg = statusmod.set_status(repo, args.path, "archived")
    print(msg)
    return 0 if ok else 1


def cmd_restore(repo, args):
    ok, msg = statusmod.clear(repo, args.path)
    print(msg)
    return 0 if ok else 1


def cmd_retired(repo, args):
    data = statusmod.load(repo)
    _utf8()
    if not data["paths"]:
        print("No retired artifacts recorded.")
        return 0
    for rel in sorted(data["paths"]):
        e = data["paths"][rel]
        print("%-10s %s%s" % (e["status"], rel,
                              ("  (by %s)" % e["by"]) if e.get("by") else ""))
    return 0


def cmd_check(repo, args):
    result = reportmod.analyze(repo, status_data=statusmod.load(repo),
                               threshold=args.threshold, stale_days=args.stale_days)
    findings = result["findings"]
    incorrect = [f for f in findings if f["severity"] == reportmod.INCORRECT]
    stale = [f for f in findings if f["severity"] == reportmod.STALE]
    failing = incorrect + (stale if args.strict else [])
    _utf8()
    if not failing:
        print("corpus check: ok (%d incorrect, %d stale, %d noise)"
              % (0, len(stale),
                 len([f for f in findings if f["severity"] == reportmod.NOISE])))
        return 0
    print("corpus check: %d finding(s) block this commit" % len(failing))
    for f in failing:
        print("  [%s] %s: %s" % (f["severity"], f["path"], f["detail"]))
        print("       -> %s" % f["action"])
    if not args.strict and stale:
        print("\n(%d stale artifact(s) reported, not blocking; use --strict to gate them)"
              % len(stale))
    return 1


def _err(msg):
    sys.stderr.write("corpus: %s\n" % msg)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="corpus")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--glob", action="append", default=None,
                    help="artifact glob (repeatable, default **/*.md)")
    ap.add_argument("--ignore", action="append", default=[],
                    help="extra directory to skip (repeatable)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan")
    p = sub.add_parser("report"); p.add_argument("--json", action="store_true")
    p.add_argument("--noise", action="store_true", help="also list orphans, notes, scratch")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--stale-days", type=int, default=7)
    p = sub.add_parser("find"); p.add_argument("query"); p.add_argument("--limit", type=int, default=8)
    p = sub.add_parser("dupes"); p.add_argument("--threshold", type=float, default=0.7)
    p = sub.add_parser("supersede"); p.add_argument("old"); p.add_argument("--by", required=True)
    p = sub.add_parser("archive"); p.add_argument("path")
    p = sub.add_parser("restore"); p.add_argument("path")
    sub.add_parser("retired")
    p = sub.add_parser("check"); p.add_argument("--strict", action="store_true")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--stale-days", type=int, default=7)

    args = ap.parse_args(argv)
    _utf8()
    if args.glob is None:
        args.glob = list(scanmod.DEFAULT_GLOBS)
    repo = os.path.abspath(args.repo)

    handlers = {"scan": cmd_scan, "report": cmd_report, "find": cmd_find,
                "dupes": cmd_dupes, "supersede": cmd_supersede,
                "archive": cmd_archive, "restore": cmd_restore,
                "retired": cmd_retired, "check": cmd_check}
    return handlers[args.cmd](repo, args)


if __name__ == "__main__":
    sys.exit(main())
