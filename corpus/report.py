"""corpus report: what is wrong with this body of documents, worst first.

Severity, borrowed from how people actually triage documentation:

    incorrect  something is wrong - a broken reference, two copies of the same
               text, an active document that points at a retired one
    stale      nothing is wrong yet, but the document no longer matches the
               code it describes, or another document says almost the same thing
    noise      nothing is broken; there is just too much of it - orphans,
               scratch files, directories with no entry point

Only `incorrect` is ever a hard gate. The rest is judgement, reported with an
action so a human or agent can decide quickly.
"""
import os
import time

from . import scan as scanmod
from . import sim, status as statusmod

INCORRECT, STALE, NOISE = "incorrect", "stale", "noise"
SEVERITY_ORDER = {INCORRECT: 0, STALE: 1, NOISE: 2}
INDEX_NAMES = ("readme.md", "index.md", "readme", "index")


def _is_index(rel):
    return os.path.basename(rel).lower() in INDEX_NAMES


def _reading_cost(chars):
    return int(chars / 4.0)


def _exact_duplicates(index):
    out = []
    for sha, paths in index["by_sha"].items():
        if len(paths) < 2:
            continue
        paths = sorted(paths)
        keep = next((p for p in paths if not scanmod.is_scratch(p)), paths[0])
        for p in paths:
            if p != keep:
                out.append({"severity": INCORRECT, "kind": "duplicate-exact",
                            "path": p, "other": keep,
                            "detail": "byte-identical to %s" % keep,
                            "action": "delete %s, keep %s" % (p, keep)})
    return out


def _near_duplicates(index, threshold):
    if len(index["artifacts"]) < 2:
        return []
    texts = {}
    for rel in index["artifacts"]:
        text = scanmod.read_text(os.path.join(index["root"], rel))
        if text is not None and len(text) > 400:      # short files collide by accident
            texts[rel] = text
    out = []
    for a, b, score in sim.near_duplicates(texts, threshold):
        if index["artifacts"][a]["sha"] == index["artifacts"][b]["sha"]:
            continue                                   # already reported exactly
        keep, drop = sorted([a, b], key=lambda p: (-index["artifacts"][p]["chars"], p))
        sev = INCORRECT if score >= 0.85 else STALE
        out.append({"severity": sev, "kind": "duplicate-near", "path": drop,
                    "other": keep, "score": score,
                    "detail": "%.0f%% similar to %s" % (score * 100, keep),
                    "action": "merge %s into %s, then archive %s" % (drop, keep, drop)})
    return out


def _orphans(index, back, status_data):
    mentioned = []
    for rel, rec in index["artifacts"].items():
        if _is_index(rel) and not index["artifacts"][rel]["scratch"]:
            text = scanmod.read_text(os.path.join(index["root"], rel)) or ""
            mentioned.append((rel, text))
    out = []
    for rel, rec in index["artifacts"].items():
        if _is_index(rel) or rec["kind"] in ("readme", "skill", "changelog", "contributing"):
            continue
        if statusmod.status_of(status_data, rel) != "active":
            continue
        if back.get(rel):
            continue
        base = os.path.basename(rel)
        if any(base in text or rel in text for _src, text in mentioned):
            continue
        out.append({"severity": NOISE, "kind": "orphan", "path": rel,
                    "detail": "nothing links to it, no index mentions it",
                    "action": "link it from an index, merge it, or archive it"})
    return out


def _stale(index, days=7):
    """A document older than the code it points at, by at least `days`.

    Same-day drift is usually work in progress; a week of silence is drift.
    Changelogs are historical by nature and never count.
    """
    out = []
    arts = index["artifacts"]
    gap = max(1, days) * 86400
    for rel, rec in arts.items():
        if not rec["refs"] or rec["kind"] == "changelog":
            continue
        newest = 0.0
        exists = 0
        for ref in rec["refs"]:
            for cand in (os.path.join(index["root"], ref),
                         os.path.join(index["root"], os.path.dirname(rel), ref)):
                if os.path.exists(cand):
                    exists += 1
                    newest = max(newest, os.path.getmtime(cand))
                    break
        if exists and newest > rec["mtime"] + gap:
            out.append({"severity": STALE, "kind": "stale", "path": rel,
                        "detail": "code it references changed after the document "
                                  "(%s)" % time.strftime("%Y-%m-%d", time.localtime(newest)),
                        "action": "re-read the code and update the document"})
    return out


def _broken(index, repo):
    """Broken local links. In a note or a research file they are usually links
    copied from the upstream project - noise, not a broken promise."""
    out = []
    for rel, missing in scanmod.broken_links(index, repo).items():
        note = index["artifacts"][rel]["kind"] in ("note", "report")
        out.append({"severity": NOISE if note else INCORRECT,
                    "kind": "broken-link", "path": rel,
                    "detail": "links to missing local target(s): %s"
                              % ", ".join(missing[:5]),
                    "action": "fix the link target, or archive the note if it was "
                              "copied from another project"})
    return out


def _links_to_retired(index, back, status_data):
    out = []
    for rel, rec in index["artifacts"].items():
        if statusmod.status_of(status_data, rel) != "active":
            continue
        for dst in rec["links_out"]:
            st = statusmod.status_of(status_data, dst)
            if st != "active":
                out.append({"severity": INCORRECT, "kind": "links-retired", "path": rel,
                            "other": dst,
                            "detail": "links to %s, which is %s" % (dst, st),
                            "action": "point it at the document that replaced it"})
    return out


def _scratch(index):
    return [{"severity": NOISE, "kind": "scratch", "path": rel,
             "detail": "looks like a scratch or draft file",
             "action": "delete it, or rename it if it is real"}
            for rel, rec in index["artifacts"].items() if rec["scratch"]]


def _sprawl(index, min_docs=8):
    dirs = {}
    for rel, rec in index["artifacts"].items():
        d = os.path.dirname(rel) or "."
        dirs.setdefault(d, []).append(rel)
    out = []
    for d, paths in sorted(dirs.items()):
        if len(paths) < min_docs:
            continue
        has_index = any(_is_index(p) for p in paths)
        if has_index:
            continue
        out.append({"severity": NOISE, "kind": "no-index", "path": d,
                    "detail": "%d documents, none of them an index" % len(paths),
                    "action": "add README.md or INDEX.md listing them"})
    return out


def analyze(repo, index=None, status_data=None, threshold=0.7, stale_days=7):
    repo = os.path.abspath(repo)
    index = index or scanmod.scan(repo)
    status_data = status_data or statusmod.load(repo)
    back = scanmod.inbound(index)
    findings = []
    findings += _exact_duplicates(index)
    findings += _near_duplicates(index, threshold)
    findings += _broken(index, repo)
    findings += _links_to_retired(index, back, status_data)
    findings += _stale(index, stale_days)
    findings += _orphans(index, back, status_data)
    findings += _scratch(index)
    findings += _sprawl(index)
    for f in findings:
        if statusmod.status_of(status_data, f["path"]) != "active" and f["severity"] != INCORRECT:
            f["severity"] = NOISE
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["kind"], f["path"]))
    return {"findings": findings, "index": index, "status": status_data, "inbound": back}


def metrics(result):
    index = result["index"]
    arts = index["artifacts"]
    findings = result["findings"]
    total_chars = sum(r["chars"] for r in arts.values())
    return {
        "artifacts": len(arts),
        "chars": total_chars,
        "reading_tokens": _reading_cost(total_chars),
        "kinds": _counts(r["kind"] for r in arts.values()),
        "severity": _counts(f["severity"] for f in findings),
        "orphan_rate": round(len([f for f in findings if f["kind"] == "orphan"]) /
                             float(max(1, len(arts))), 3),
        "retired": len([p for p in result["status"].get("paths", {})
                        if p in arts]),
    }


def _counts(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def render(result, show_noise=False, per_kind=5):
    m = metrics(result)
    lines = ["# corpus report (%s)" % time.strftime("%Y-%m-%d %H:%M"), "",
             "%d artifacts · ~%d tokens if all loaded · %d incorrect · %d stale · %d noise"
             % (m["artifacts"], m["reading_tokens"], m["severity"].get(INCORRECT, 0),
                m["severity"].get(STALE, 0), m["severity"].get(NOISE, 0)),
             ""]
    shown = [INCORRECT, STALE] + ([NOISE] if show_noise else [])
    any_shown = False
    for sev, title in ((INCORRECT, "Incorrect"), (STALE, "Stale"), (NOISE, "Noise")):
        if sev not in shown:
            continue
        group = [f for f in result["findings"] if f["severity"] == sev]
        if not group:
            continue
        any_shown = True
        lines.append("## %s (%d)" % (title, len(group)))
        by_kind = {}
        for f in group:
            by_kind.setdefault(f["kind"], []).append(f)
        for kind in sorted(by_kind):
            items = by_kind[kind]
            lines.append("### %s (%d)" % (kind, len(items)))
            for f in items[:per_kind]:
                lines.append("- `%s` - %s" % (f["path"], f["detail"]))
                lines.append("  - %s" % f["action"])
            if len(items) > per_kind:
                lines.append("- ... and %d more %s" % (len(items) - per_kind, kind))
            lines.append("")
    if not any_shown:
        lines.append("Nothing incorrect or stale.")
    if not show_noise and m["severity"].get(NOISE):
        lines.append("")
        lines.append("%d noise finding(s) hidden - run `corpus report --noise`."
                     % m["severity"][NOISE])
    return "\n".join(lines)
