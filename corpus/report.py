"""corpus report: what is wrong with this body of documents, worst first.

Severity, borrowed from how people actually triage documentation:

    incorrect  something is wrong - a broken link, two copies of the same text,
               an active document that points at a retired one
    stale      nothing is wrong yet, but the document no longer matches the
               code it describes, or another document says almost the same thing
    noise      nothing is broken; there is just too much of it - orphans,
               scratch files, directories with no entry point

Only `incorrect` is ever a hard gate. The rest is judgement, reported with an
action so a human or agent can decide quickly.
"""
import os
import re
import subprocess
import time

from . import scan as scanmod
from . import sim, status as statusmod

INCORRECT, STALE, NOISE = "incorrect", "stale", "noise"
SEVERITY_ORDER = {INCORRECT: 0, STALE: 1, NOISE: 2}
INDEX_NAMES = ("readme.md", "index.md", "readme", "index")
MIN_NEAR_DUP_CHARS = 400          # shorter files collide by accident


def _is_index(rel):
    return os.path.basename(rel).lower() in INDEX_NAMES


def _keep(paths, back):
    """Which copy to keep: the most linked one, then non-scratch, then shortest."""
    return sorted(paths, key=lambda p: (-len(back.get(p, [])),
                                        scanmod.is_scratch(p), len(p), p))[0]


def _exact_duplicates(index, back):
    out = []
    for paths in index["by_sha"].values():
        if len(paths) < 2:
            continue
        keep = _keep(paths, back)
        for p in sorted(paths):
            if p != keep:
                out.append({"severity": INCORRECT, "kind": "duplicate-exact",
                            "path": p, "other": keep,
                            "detail": "byte-identical to %s" % keep,
                            "action": "keep %s, archive %s" % (keep, p)})
    return out


def _near_duplicates(index, threshold, back):
    if len(index["artifacts"]) < 2:
        return []
    texts = {}
    for rel in index["artifacts"]:
        text = scanmod.read_text(os.path.join(index["root"], rel))
        if text is not None and len(text) > MIN_NEAR_DUP_CHARS:
            texts[rel] = text
    out = []
    for a, b, score in sim.near_duplicates(texts, threshold):
        if index["artifacts"][a]["sha"] == index["artifacts"][b]["sha"]:
            continue                                   # already reported exactly
        keep = _keep([a, b], back)
        drop = b if keep == a else a
        sev = INCORRECT if score >= 0.85 else STALE
        out.append({"severity": sev, "kind": "duplicate-near", "path": drop,
                    "other": keep, "score": score,
                    "detail": "%.0f%% similar to %s" % (score * 100, keep),
                    "action": "merge %s into %s, then supersede %s --by %s"
                              % (drop, keep, drop, keep)})
    return out


def _orphans(index, back, status_data):
    index_texts = []
    for rel in index["artifacts"]:
        if _is_index(rel):
            text = scanmod.read_text(os.path.join(index["root"], rel)) or ""
            index_texts.append(text)
    out = []
    for rel, rec in index["artifacts"].items():
        if _is_index(rel) or rec["kind"] in ("readme", "skill", "changelog", "contributing"):
            continue
        if statusmod.status_of(status_data, rel) != "active":
            continue
        if back.get(rel):
            continue
        base = os.path.basename(rel)
        # A bare substring match made "plan.md" mentioned by "masterplan.md".
        rx = re.compile(r"(?<![\w.-])%s(?![\w.-])" % re.escape(base))
        if any(rx.search(text) for text in index_texts):
            continue
        out.append({"severity": NOISE, "kind": "orphan", "path": rel,
                    "detail": "nothing links to it, no index names it",
                    "action": "link it from an index, merge it, or archive it"})
    return out


def _stale(index, days=7):
    """A document older than the code it points at, by at least `days`.

    Same-day drift is usually work in progress; a week of silence is drift.
    Changelogs are historical by nature and never count. A reference that no
    longer exists is not reported here - only a reference that changed.
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
            # doc-relative first: a doc in docs/ that says `config.md` means
            # docs/config.md, not the root config.md.
            for cand in (os.path.normpath(os.path.join(os.path.dirname(rel), ref))
                         .replace("\\", "/"),
                         os.path.normpath(ref).replace("\\", "/")):
                absolute = (cand if os.path.isabs(cand)
                            else os.path.join(index["root"], *cand.split("/")))
                if os.path.isabs(cand) or cand == ".." or cand.startswith("../"):
                    found = os.path.exists(absolute)
                else:
                    found = scanmod.exists_exact(index["root"], cand)
                if found:
                    exists += 1
                    try:
                        newest = max(newest, os.path.getmtime(absolute))
                    except OSError:
                        pass
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
                    "action": ("fix the link target, or archive the note if it was "
                               "copied from another project" if note else
                               "fix the link target, or remove the link")})
    return out


def _deleted_paths(repo):
    """Every path git has ever deleted. The precise evidence that a reference
    points at something that used to exist, rather than at an example."""
    try:
        p = subprocess.run(["git", "-C", repo, "log", "--all", "--pretty=format:",
                            "--name-only", "--diff-filter=D"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set()
    if p.returncode != 0:
        return set()
    return set(line.strip().replace("\\", "/")
               for line in (p.stdout or "").splitlines() if line.strip())


def _ignored_refs(repo, refs):
    """Paths the repository tells git to ignore.

    A document may name runtime state on purpose - "the reading is recorded to
    `.lifecycle/context.json`". If that path once existed in history and was
    later ignored, it is not a document that went missing, and on a machine
    where the file does not happen to exist the check must not call it one.
    """
    if not refs:
        return set()
    try:
        p = subprocess.run(["git", "-C", repo, "check-ignore", "--no-index",
                            "--stdin"],
                           input="\n".join(sorted(refs)),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return set()
    if p.returncode not in (0, 1):
        return set()
    return set(line.strip() for line in (p.stdout or "").splitlines()
               if line.strip())


def _missing_refs(index, repo):
    """A backticked path the repository deleted, still named by a document.

    Judged only against files git says once existed: a README that says "put
    your file at `src/foo.py`" has broken no promise, and the first version of
    this check flagged exactly that. A document that points at a file deleted
    from the repository sends the reader to a dead end. A gitignored runtime
    path is not that: it was never meant to be in the repository.
    """
    deleted = _deleted_paths(repo)
    if not deleted:
        return []
    candidates = []
    for rel, rec in index["artifacts"].items():
        base = os.path.dirname(rel)
        for ref in rec.get("refs") or []:
            if ref not in deleted:
                continue
            if any(scanmod.exists_exact(d, ref)
                   for d in (repo, base)):
                continue                     # deleted once, restored since
            if ref in (rec.get("links_out") or []):
                continue                     # the link check already reports it
            candidates.append((rel, rec, ref))
    ignored = _ignored_refs(repo, set(ref for _, _, ref in candidates))
    out = []
    for rel, rec, ref in candidates:
        if ref in ignored:
            continue
        out.append({"severity": INCORRECT, "kind": "missing-ref", "path": rel,
                    "other": ref,
                    "detail": "refers to `%s`, which was deleted from the "
                              "repository" % ref,
                    "action": "update the reference, or restore the file - a "
                              "document that points at a deleted file sends "
                              "the reader to a dead end"})
    seen, uniq = set(), []
    for f in out:
        key = (f["path"], f["other"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def _links_to_retired(index, status_data):
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
    for rel in index["artifacts"]:
        dirs.setdefault(os.path.dirname(rel) or ".", []).append(rel)
    out = []
    for d, paths in sorted(dirs.items()):
        if len(paths) < min_docs or any(_is_index(p) for p in paths):
            continue
        out.append({"severity": NOISE, "kind": "no-index", "path": d,
                    "detail": "%d documents, none of them an index" % len(paths),
                    "action": "add README.md or INDEX.md listing them"})
    return out


def analyze(repo, index=None, status_data=None, threshold=0.7, stale_days=7,
            globs=None, ignore=()):
    repo = os.path.abspath(repo)
    if index is None:
        if globs:
            index = scanmod.scan(repo, globs, ignore)
        else:
            index = scanmod.scan(repo, extra_ignore=ignore)
    status_data = status_data or statusmod.load(repo)
    back = scanmod.inbound(index)
    findings = []
    findings += _exact_duplicates(index, back)
    findings += _near_duplicates(index, threshold, back)
    findings += _broken(index, repo)
    findings += _missing_refs(index, repo)
    findings += _links_to_retired(index, status_data)
    findings += _stale(index, stale_days)
    findings += _orphans(index, back, status_data)
    findings += _scratch(index)
    findings += _sprawl(index)
    # One file, one finding: a duplicate that is also an orphan and a scratch
    # file is three lines saying "deal with this copy".
    duplicated = set(f["path"] for f in findings if f["kind"].startswith("duplicate"))
    findings = [f for f in findings
                if not (f["path"] in duplicated and f["kind"] in ("orphan", "scratch"))]
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
        "reading_tokens": int(total_chars / 4.0),
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
