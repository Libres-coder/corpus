# corpus

**Agents add documents. Nobody removes them. corpus tracks the pile and reports the damage.**

Ask it what you already have before you write; ask it what is wrong after. This
is the real output on a six-file demo repository:

```
$ corpus find "deploy to staging"
Closest artifacts to 'deploy to staging':
  1.00  active doc    docs/guide.md  -  Guide
  1.00  active doc    docs/guide-copy.md  -  Guide

Extend docs/guide.md instead of writing a new document.

$ corpus report --noise
6 artifacts · ~67 tokens if all loaded · 2 incorrect · 0 stale · 3 noise

## Incorrect (2)
### broken-link (1)
- `README.md` - links to missing local target(s): docs/missing.md
  - fix the link target, or remove the link
### duplicate-exact (1)
- `docs/guide-copy.md` - byte-identical to docs/guide.md
  - keep docs/guide.md, archive docs/guide-copy.md

## Noise (3)
### orphan (2)
- `docs/notes-old.md` - nothing links to it, no index names it
  - link it from an index, merge it, or archive it
### scratch (1)
- `tmp-draft.md` - looks like a scratch or draft file
  - delete it, or rename it if it is real

$ corpus check
corpus check: 2 finding(s) block this commit
  [incorrect] README.md: links to missing local target(s): docs/missing.md
  [incorrect] docs/guide-copy.md: byte-identical to docs/guide.md
```

## Why

Every agent-written document is cheap to create and expensive to maintain. In a
few weeks a repo accumulates: two plans for the same feature, a README
describing an API that moved, research notes whose conclusion already shipped,
and forty files nothing links to. Each one still looks authoritative.

Adjacent tools cover the edges: linters check style and external links, memory
tools dedupe facts, spec frameworks add *another* directory. None of them track
the population - what exists, what replaced what, what nobody reads.

## Install

Standard library only, Python 3.8+.

```bash
pip install git+https://github.com/Libres-coder/corpus
```

As a Claude Code skill:

```bash
git clone https://github.com/Libres-coder/corpus ~/.claude/skills/corpus
pip install ~/.claude/skills/corpus        # or run with PYTHONPATH=~/.claude/skills/corpus
```

## Commands

| command | for |
|---|---|
| `corpus find "topic"` | before writing: is there already a document? |
| `corpus report` | what is incorrect or stale (`--noise` for the rest, `--json` for machines) |
| `corpus check` | CI gate: exit 1 on anything incorrect (`--strict` also fails on stale) |
| `corpus dupes` | duplicate pairs, naming the copy to keep |
| `corpus supersede OLD --by NEW` | record that NEW replaced OLD |
| `corpus archive PATH` / `restore PATH` | retire / un-retire a document |
| `corpus retired` | the decisions you recorded |
| `corpus scan` | rebuild `.corpus/index.json` (a cache; nothing else is written) |

`--repo` picks the repository (default: cwd). `--glob` adds a pattern to the
default `**/*.md`; `--ignore` adds a directory to skip.

## Severity

| severity | meaning | examples | gate |
|---|---|---|---|
| **incorrect** | a reader is misled | broken local link, byte-identical copy, near-duplicate >= 85%, active doc linking a retired one, a backticked path git deleted | fails `check` |
| **stale** | true when written, not now | the code it names changed a week later; near-duplicate 70-85% | fails `check --strict` |
| **noise** | nothing wrong, too much | orphan, scratch file, directory with no index | reported |

Three deliberate exceptions: a broken link in a `note`/`report`-kind file (under
`research/`, `notes/`, `drafts/`, `examples/`, `vendor/`) is noise, because those
files quote other projects; `links-retired` only looks at active sources; and a
deleted path still listed in `.gitignore` is runtime state a document may name
on purpose, not a document that went missing.

## The state it keeps

One small file, meant to be committed:

```json
// .corpus/status.json
{"paths": {"docs/plan-v1.md": {"status": "superseded", "by": "docs/plan-v2.md"}}}
```

Everything else - the index, the link graph, the duplicate scores - is derived
on every run. `.corpus/index.json` is a cache and belongs in `.gitignore`.

## What it does not do

- It does not delete, move, rename or rewrite files. It reports; you decide.
- It does not check external links, prose style or factual accuracy.
- It does not find two documents that say the same thing in different words:
  near-duplicate detection is shingle-based and skips files under 400
  characters. The report says "none found at this threshold", never "no
  duplicates exist".
- It does not scan agent state (`.claude/`, `.cursor/`, `.projtruth/`,
  `.remember/`) or fixtures by default; those are a separate corpus.
- It does not report a backticked path that no longer exists - only one that
  changed after the document.

## Design notes

- **Prevention before cleanup.** `find` is the first command for a reason: the
  cheapest document to maintain is the one that was never written.
- **Correct beats tidy.** A duplicate that misleads is a gate failure; an orphan
  is a suggestion. Tools that gate on tidiness get switched off.
- **Decisions are data.** `supersede`/`archive` are recorded, so "this was
  replaced" survives the session that decided it.
- **Zero dependencies**, so it runs in any repo, on any CI, without a lockfile.

## Related

- [projtruth](https://github.com/Libres-coder/projtruth) - requirements and
  evidence: is it built, and is the proof still valid?
- [skill-audit](https://github.com/Libres-coder/skill-audit) - the same question
  for an installed skill collection: overlapping triggers, unused skills.
- [verify-first](https://github.com/Libres-coder/verify-first) - the pipeline
  that produces the evidence projtruth reads.

## License

MIT
