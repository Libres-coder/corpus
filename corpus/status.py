"""corpus status: the only hand-maintained state - what is superseded or archived.

Everything else in corpus is derived from the files themselves; nothing to keep
in sync. This file records the one thing a scan cannot infer: a human or agent
decided that document A is no longer the truth, and B is.
"""
import json
import os
import tempfile
import time

STATE_DIR = ".corpus"
STATUS_NAME = "status.json"
VALID = ("superseded", "archived")


def state_dir(repo):
    return os.path.join(repo, STATE_DIR)


def _path(repo):
    return os.path.join(state_dir(repo), STATUS_NAME)


def _norm(rel):
    """Repo-relative, with one leading './' removed.

    Not lstrip('./'): that turns '.github/x.md' into 'github/x.md' and '../x'
    into 'x', aliasing two different files onto one entry.
    """
    rel = str(rel).replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return rel


def _valid_entry(entry):
    return (isinstance(entry, dict) and entry.get("status") in VALID
            and (entry.get("by") is None or isinstance(entry.get("by"), str)))


def load(repo):
    try:
        with open(_path(repo), encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {"paths": {}}
    except ValueError:
        return {"paths": {}}          # a damaged status file is not a crash
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        return {"paths": {}}
    # Drop entries that would raise later: this file is hand-edited sometimes.
    paths = dict((k, v) for k, v in data["paths"].items() if _valid_entry(v))
    return {"paths": paths}


def save(repo, data):
    os.makedirs(state_dir(repo), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".status-", suffix=".tmp", dir=state_dir(repo))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, _path(repo))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_status(repo, rel, status, by=None):
    rel = _norm(rel)
    if status not in VALID:
        return False, "invalid status %r (valid: %s)" % (status, ", ".join(VALID))
    if ".." in rel.split("/"):
        return False, "status paths must stay inside the repo: %s" % rel
    data = load(repo)
    entry = {"status": status, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if by:
        entry["by"] = _norm(by)
    data["paths"][rel] = entry
    save(repo, data)
    return True, "%s -> %s%s" % (rel, status, (" (by %s)" % entry["by"]) if by else "")


def clear(repo, rel):
    rel = _norm(rel)
    data = load(repo)
    if rel not in data["paths"]:
        return False, "no status recorded for %s" % rel
    del data["paths"][rel]
    save(repo, data)
    return True, "%s is active again" % rel


def status_of(data, rel):
    entry = data.get("paths", {}).get(_norm(rel))
    return entry["status"] if entry else "active"
