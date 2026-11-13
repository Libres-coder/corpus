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
import urllib.parse

DEFAULT_GLOBS = ("**/*.md",)
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
               "build", "target", ".next", ".cache", ".corpus", "graphify-out",
               ".idea", ".vscode", "vendor", "third_party", "site-packages",
               # agent state and machine-produced evidence are not documents a
               # human maintains; scanning them produced a wall of fake orphans
               ".claude", ".cursor", ".agents", ".projtruth", ".remember",
               "testdata", "fixtures"}
SKIP_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "SOURCE.md")

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REF_DEF_RE = re.compile(r"^[ \t]*\[(?!\^)[^\]]+\]:[ \t]*(\S+)", re.MULTILINE)
HREF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
CODE_RE = re.compile(r"`([^`\n]+)`")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
BAD_PATH_CHARS = re.compile(r"[\s\"'<>|*?]")
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
    """A temporary-looking name. Deliberately conservative: "copy" is not in the
    list, because copy-voice.md and api-status-copy.md are real documents - a
    copy is caught by duplicate detection, not by its name."""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    return stem.startswith(("tmp", "temp", "scratch", "wip", "draft", "old",
                            "backup", "untitled"))


def sha_of(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def parse_frontmatter(text):
    """A leading --- block, but only if it closes within 40 lines and looks like
    key: value. A document that opens with a thematic rule then has another ---
    later must not be eaten as frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, min(len(lines), 40)):
        if lines[i].strip() == "---":
            block = lines[1:i]
            if not any(":" in line for line in block if line.strip()):
                return {}, text
            fm = {}
            for line in block:
                if ":" not in line or line.lstrip().startswith("#"):
                    continue
                key, _, value = line.partition(":")
                fm[key.strip().lower()] = value.strip().strip("'\"")
            return fm, "\n".join(lines[i + 1:])
    return {}, text


def title_of(rel, body, fm):
    for key in ("title", "name"):
        if fm.get(key):
            return fm[key]
    m = HEADING_RE.search(body)
    if m:
        return m.group(1).strip()
    return os.path.splitext(os.path.basename(rel))[0]


def _resolve(src_rel, target):
    """A link target -> repo-relative path, or None if external / outside the repo."""
    t = target.strip()
    if t.startswith("<") and ">" in t:
        t = t[1:t.index(">")]
    else:
        # `(path "title")` - strip a trailing quoted title, but keep spaces that
        # are part of the path (people write [x](my file.md) and it links).
        m = re.match(r'^(.*?)\s+["\']([^"\']*)["\']$', t)
        if m:
            t = m.group(1)
    t = urllib.parse.unquote(t)
    if not t or "[" in t or "]" in t:
        return None                  # a placeholder: [Author/Org]
    if t.startswith("#") or SCHEME_RE.match(t):
        return None
    t = t.split("#", 1)[0].split("?", 1)[0]
    t = t.replace("\\", "/")
    if not t:
        return None
    base = os.path.dirname(src_rel).replace("\\", "/")
    joined = t.lstrip("/") if t.startswith("/") else os.path.join(base, t)
    joined = os.path.normpath(joined).replace("\\", "/")
    if joined == ".." or joined.startswith("../"):
        return None                      # another checkout or a parent repo
    return joined


def _refs(body):
    """Backticked paths that look like repo files (ASCII or CJK, no spaces)."""
    out = []
    for raw in CODE_RE.findall(body):
        t = raw.strip().replace("\\", "/")
        if not t or len(t) > 120 or BAD_PATH_CHARS.search(t):
            continue
        if os.path.splitext(t)[1].lower() in PATHY_EXT:
            # strip one "./" - not every leading dot: ".projtruth/x.json" is a
            # real path, and lstrip("./") would mangle it into "projtruth/...".
            out.append(t[2:] if t.startswith("./") else t)
    return sorted(set(out))


def _link_targets(body):
    """Every local-link candidate: markdown links, reference definitions, HTML.

    Fenced blocks and inline code are blanked first - a link inside a sample is
    an example, not a link, and reporting it as broken was the first dogfood's
    biggest false positive.
    """
    text = INLINE_CODE_RE.sub(" ", FENCE_RE.sub(" ", body))
    return LINK_RE.findall(text) + REF_DEF_RE.findall(text) + HREF_RE.findall(text)


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
            full = os.path.join(root, f)
            if os.path.islink(full):
                continue                 # a symlinked copy is not a second document
            rel = os.path.relpath(full, repo).replace("\\", "/")
            base = os.path.basename(rel)
            if base in SKIP_NAMES or base.upper().startswith("LICENSE"):
                continue
            if any(_match(rel, base, g) for g in globs):
                yield rel


def scan(repo, globs=DEFAULT_GLOBS, extra_ignore=()):
    """Return {"root", "artifacts": {rel: record}, "by_sha": {sha: [rel]}}."""
    artifacts = {}
    for rel in iter_files(repo, globs, extra_ignore):
        full = os.path.join(repo, rel)
        text = read_text(full)
        if text is None:
            continue
        try:
            mtime = os.path.getmtime(full)
        except OSError:
            continue                 # vanished between listing and stat
        fm, body = parse_frontmatter(text)
        rec = {
            "path": rel,
            "title": title_of(rel, body, fm),
            "kind": kind_of(rel),
            "sha": sha_of(text),
            "chars": len(text),
            "lines": text.count("\n") + 1,
            "mtime": mtime,
            "scratch": is_scratch(rel),
            "links_out": [],
            "refs": _refs(body),
        }
        targets = []
        for target in _link_targets(body):
            resolved = _resolve(rel, target)
            if resolved:
                targets.append(resolved)
        rec["links_out"] = sorted(set(targets))
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

    Only links count (markdown, reference definitions, HTML). A backticked name
    in prose is usually an example ("name the file R3-x.md").
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
