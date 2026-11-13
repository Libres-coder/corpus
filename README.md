# corpus

**Agents add documents. Nobody removes them. corpus governs the pile.**

Ask it what you already have before you write, ask it what is wrong after:

```
$ corpus find "how to deploy to staging"
Closest artifacts to 'how to deploy to staging':
  0.71  active readme skill-audit/README.md  - Audit installed Claude Code skills
  0.43  active doc    projtruth/README.md    - projtruth
Extend skill-audit/README.md instead of writing a new document.

$ corpus report
292 artifacts · ~528888 tokens if all loaded · 1 incorrect · 1 stale · 19 noise

## Incorrect (1)
### broken-link (1)
- `markdown-mermaid-writing/references/markdown_style_guide.md` - links to missing local target(s): .../images/architecture_overview.png
  - fix the link target, or remove the link

$ corpus check          # exit 1 - the broken link has to go
```

That second output is a real run over a 292-document tree.

## Why

Every agent-written artifact is cheap to create and expensive to maintain. In a
few weeks a repo accumulates: two plans for the same feature, a README describing
an API that moved, research notes whose conclusion already shipped, and forty
files nothing links to. Each one still looks authoritative.

Existing tools cover the edges: linters check style and external links, memory
tools dedupe facts, spec frameworks add *another* directory. None of them govern
the population - what exists, what replaced what, what nobody reads.

## Install

Standard library only, Python 3.8+.

```bash
pip install git+https://github.com/Libres-coder/corpus
```

As a Claude Code skill:

```bash
git clone https://github.com/Libres-coder/corpus ~/.claude/skills/corpus
```

## Commands

| command | for |
|---|---|
| `corpus find "topic"` | before writing: is there already a document? |
| `corpus report` | what is incorrect or stale (add `--noise` for the rest) |
| `corpus check` | CI gate: exit 1 on anything incorrect (`--strict` also fails on stale) |
| `corpus dupes` | near-duplicate pairs, with which one to keep |
| `corpus supersede OLD --by NEW` | record that NEW replaced OLD |
| `corpus archive PATH` / `restore PATH` | retire / un-retire a document |
| `corpus retired` | the decisions you recorded |
| `corpus scan` | rebuild `.corpus/index.json` (a cache; nothing else is written) |

## Severity

| severity | meaning | examples | gate |
|---|---|---|---|
| **incorrect** | a reader is misled | broken local link, byte-identical copy, link to a retired doc | fails `check` |
| **stale** | true when written, not now | the code it names changed a week later | fails `check --strict` |
| **noise** | nothing wrong, too much | orphan, scratch file, directory with no index | reported |

Only *incorrect* fails a commit by default. The rest is judgement, reported with
one suggested action per finding.

## The state it keeps

One small file, meant to be committed:

```json
// .corpus/status.json
{"paths": {"docs/plan-v1.md": {"status": "superseded", "by": "docs/plan-v2.md",
                               "at": "2026-11-13 18:20:00"}}}
```

Everything else - the index, the link graph, the duplicate scores - is derived
from the files themselves on every run. There is nothing to keep in sync.

## What it does not do

- It does not delete, move, rename or rewrite files. It reports; you decide.
- It does not check external links, prose style or factual accuracy.
- It does not find two documents that say the same thing in different words -
  near-duplicate detection is shingle-based and skips files under 400
  characters; the report says "none found at this threshold", never "no
  duplicates exist".
- It does not scan agent state (`.claude/`, `.cursor/`, `.projtruth/`,
  `.remember/`) or fixtures by default; those are a separate corpus.
- It does not replace `git`. Every decision is also a commit message.

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
