"""corpus status: the only hand-maintained state - what is superseded or archived.

Everything else in corpus is derived from the files themselves; nothing to keep
in sync. This file records the one thing a scan cannot infer: a human or agent
decided that document A is no longer the truth, and B is.
"""
import json
import os
import time

STATE_DIR = ".corpus"
STATUS_NAME = "status.json"
VALID = ("superseded", "archived")


def state_dir(repo):
    return os.path.join(repo, STATE_DIR)


def _path(repo):
    return os.path.join(state_dir(repo), STATUS_NAME)


def _norm(rel):
    return rel.replace("\\", "/").lstrip("./")


def load(repo):
    try:
        with open(_path(repo), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"paths": {}}
    if not isinstance(data, dict) or not isinstance(data.get("paths", {}), dict):
        return {"paths": {}}
    data.setdefault("paths", {})
    return data


def save(repo, data):
    os.makedirs(state_dir(repo), exist_ok=True)
    tmp = _path(repo) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, _path(repo))


def set_status(repo, rel, status, by=None):
    rel = _norm(rel)
    if status not in VALID:
        return False, "invalid status %r (valid: %s)" % (status, ", ".join(VALID))
    data = load(repo)
    entry = {"status": status, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if by:
        entry["by"] = _norm(by)
    data["paths"][rel] = entry
    save(repo, data)
    return True, "%s -> %s%s" % (rel, status, (" (by %s)" % by) if by else "")


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
