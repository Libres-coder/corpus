"""corpus scan: inventory every text artifact in a repo and the links between them.

What is an artifact? Any file a person or an agent wrote and might later read as
truth: docs, plans, specs, skills, reports, notes. Code is not an artifact here
(it has its own structure tooling); the tool records code *references* so a doc
can be checked against the code it describes.
"""
import fnmatch
import hashlib
import os
import re

DEFAULT_GLOBS = ("**/*.md",)
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
               "build", "target", ".next", ".cache", ".corpus", "graphify-out",
               ".idea", ".vscode", "vendor", "third_party", "site-packages"}
# Files that are part of a project's skeleton: they are never "orphans", and a
# duplicate of one of them is always a copy problem.
CANONICAL_NAMES = ("README.md", "SKILL.md", "LICENSE", "CHANGELOG.md",
                   "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md", "index.md",
                   "INDEX.md")
SKIP_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt")

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
CODE_RE = re.compile(r"`([^`\n]+)`")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
PATHY_RE = re.compile(r"[A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9]{1,8}$")
PATHY_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
             ".sh", ".ps1", ".md", ".json", ".yml", ".yaml", ".toml", ".ini",
             ".cfg", ".txt", ".css", ".scss", ".html", ".sql", ".c", ".h",
             ".cpp", ".hpp", ".cs", ".php", ".kt", ".swift"}

KIND_RULES = [
    ("readme", lambda p: os.path.basename(p).upper().startswith("README")),
    ("skill", lambda p: os.path.basename(p) == "SKILL.md"),
    ("changelog", lambda p: os.path.basename(p).upper().startswith("CHANGELOG")),
    ("contributing", lambda p: os.path.basename(p).upper().startswith("CONTRIBUTING")),
    ("plan", lambda p: "/plans/" in p or "/plan/" in p or
     os.path.basename(p).lower().startswith(("plan", "roadmap", "todo"))),
    ("spec", lambda p: "/specs/" in p or os.path.basename(p).lower().startswith("spec")),
    ("report", lambda p: os.path.basename(p).lower().startswith(("report", "research", "audit"))),
    ("note", lambda p: any(seg in p for seg in ("/notes/", "/drafts/", "/research/",
                                                "/scratch/", "/examples/", "/samples/",
                                                "/vendor/", "/archive/"))
     or "research" in p or os.path.basename(p).lower().startswith(
         ("note", "draft", "scratch", "wip"))),
]


def kind_of(path):
    p = path.replace("\\", "/").lower()
    for name, rule in KIND_RULES:
        if rule(p):
            return name
    return "doc"


def is_scratch(path):
    base = os.path.basename(path).lower()
    return base.startswith(("tmp", "temp", "scratch", "wip", "draft", "copy", "old",
                            "backup", "untitled")) or "-copy" in base or " copy" in base


def sha_of(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def parse_frontmatter(text):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        fm[key.strip().lower()] = value.strip().strip("'\"")
    return fm, text[m.end():]


def title_of(rel, body, fm):
    for key in ("title", "name"):
        if fm.get(key):
            return fm[key]
    m = HEADING_RE.search(body)
    if m:
        return m.group(1).strip()
    return os.path.splitext(os.path.basename(rel))[0]


def _resolve(src_rel, target):
    """A markdown link target -> repo-relative path, or None if external."""
    t = target.strip().strip("<>").strip()
    if not t or t.startswith("#") or SCHEME_RE.match(t):
        return None
    t = t.split("#", 1)[0].split("?", 1)[0]
    t = t.replace("\\", "/")
    if not t:
        return None
    base = os.path.dirname(src_rel).replace("\\", "/")
    joined = t.lstrip("/") if t.startswith("/") else os.path.join(base, t)
    return os.path.normpath(joined).replace("\\", "/")


def _refs(body):
    """Backticked code identifiers that look like repo paths."""
    out = []
    for raw in CODE_RE.findall(body):
        t = raw.strip().replace("\\", "/")
        if not t or " " in t or t.startswith("-") or len(t) > 120:
            continue
        ext = os.path.splitext(t)[1].lower()
        if ext in PATHY_EXT and PATHY_RE.match(t):
            # strip one "./" - not every leading dot: ".projtruth/x.json" is a
            # real path, and lstrip("./") would mangle it into "projtruth/...".
            out.append(t[2:] if t.startswith("./") else t)
    return sorted(set(out))


def _match(rel, base, glob):
    """fnmatch's '**/*.md' requires a slash, so root-level files never match it."""
    pats = [glob]
    if glob.startswith("**/"):
        pats.append(glob[3:])
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) for p in pats)


def iter_files(repo, globs=DEFAULT_GLOBS, extra_ignore=()):
    ignore = set(IGNORE_DIRS) | set(extra_ignore)
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in ignore)
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), repo).replace("\\", "/")
            base = os.path.basename(rel)
            if base in SKIP_NAMES or base.upper().startswith("LICENSE"):
                continue
            if any(_match(rel, base, g) for g in globs):
                yield rel


def scan(repo, globs=DEFAULT_GLOBS, extra_ignore=()):
    """Return {"root", "artifacts": {rel: record}, "by_sha": {sha: [rel]}}."""
    artifacts = {}
    for rel in iter_files(repo, globs, extra_ignore):
        text = read_text(os.path.join(repo, rel))
        if text is None:
            continue
        fm, body = parse_frontmatter(text)
        rec = {
            "path": rel,
            "title": title_of(rel, body, fm),
            "kind": kind_of(rel),
            "sha": sha_of(text),
            "chars": len(text),
            "lines": text.count("\n") + 1,
            "mtime": os.path.getmtime(os.path.join(repo, rel)),
            "scratch": is_scratch(rel),
            "links_out": [],
            "refs": _refs(body),
        }
        # A link inside a fenced block is sample output, not a link.
        for target in LINK_RE.findall(FENCE_RE.sub(" ", body)):
            resolved = _resolve(rel, target)
            if resolved:
                rec["links_out"].append(resolved)
        rec["links_out"] = sorted(set(rec["links_out"]))
        artifacts[rel] = rec
    by_sha = {}
    for rel, rec in artifacts.items():
        by_sha.setdefault(rec["sha"], []).append(rel)
    return {"root": os.path.abspath(repo), "artifacts": artifacts, "by_sha": by_sha}


def _ref_targets(src, rec, arts):
    """Backticked path mentions that name another artifact.

    SKILL.md and README files often write `references/x.md` in prose instead of
    a markdown link; counting only links made every reference file an orphan.
    """
    out = []
    base = os.path.dirname(src)
    for ref in rec.get("refs", []):
        for cand in (ref, os.path.normpath(os.path.join(base, ref)).replace("\\", "/")):
            if cand in arts:
                out.append(cand)
                break
    return out


def inbound(index):
    """{path: [source paths that link to or name it]} - edges inside the corpus."""
    arts = index["artifacts"]
    back = dict((p, []) for p in arts)
    for src, rec in arts.items():
        edges = list(rec["links_out"]) + _ref_targets(src, rec, arts)
        for dst in edges:
            if dst in back and dst != src:
                back[dst].append(src)
    for p in back:
        back[p] = sorted(set(back[p]))
    return back


def broken_links(index, repo):
    """{path: [missing targets]} - *links* whose local target does not exist.

    Only markdown links count. A backticked name in prose is usually an example
    ("name the file R3-x.md"), and treating those as broken made the first
    dogfood run 90% false positives.
    """
    out = {}
    for rel, rec in index["artifacts"].items():
        missing = []
        for dst in rec["links_out"]:
            if not os.path.exists(os.path.join(repo, dst)):
                missing.append(dst)
        if missing:
            out[rel] = missing
    return out
