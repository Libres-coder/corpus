---
name: corpus
description: >-
  Tracks the documents an agent writes into a repository - docs, plans, specs,
  notes, reports - and finds the damage: near duplicates, orphans, broken local
  links, documents older than the code they describe, and links to documents
  that were retired. Answers "does this already exist?" before a second document
  is written, records which document replaced which, and gates CI on the
  findings that mislead a reader. Use when the docs are a mess, when there are
  too many markdown files, when the agent keeps adding documents, when a doc may
  be out of date, or when the user asks where something should go or to tidy or
  audit the documentation (整理文档, 文档太多, 清理文档, 重复的文档, 过时文档,
  该写在哪, 仓库太乱, 文档治理, 屎山, 内容越堆越乱). Not for: free-form memory
  files (remember:consolidate-memory), CLAUDE.md quality (claude-md-improver),
  skill trigger conflicts (skill-audit), requirements and evidence (projtruth),
  code structure (graphify), or prose style (writing-standards,
  tech-doc-style-chinese).
---

# corpus

Agents add documents. Nobody removes them. After a few weeks a repo has three
plans for the same feature, a README describing an API that moved, and forty
notes nothing links to. `corpus` indexes that pile, reports what is wrong, and
records what replaced what.

It never deletes, moves or rewrites a file. It reports, and it remembers
decisions.

## Run it

The skill directory is a checkout, not an installed package. Pick one:

```bash
pip install git+https://github.com/Libres-coder/corpus          # a command on PATH
pip install ~/.claude/skills/corpus                             # same, from the checkout
PYTHONPATH=~/.claude/skills/corpus python -m corpus --repo . report   # no install
```

Then, from the repository you are working on:

```bash
corpus --repo . find "如何部署到 staging"
corpus --repo . report
```

`--repo` defaults to the current directory. `--glob` **adds** a pattern to the
default `**/*.md` (it does not replace it); `--ignore` adds a directory to skip.

## Before writing: does it already exist?

```bash
$ corpus find "deploy to staging"
Closest artifacts to 'deploy to staging':
  1.00  active doc    docs/guide.md  -  Guide
  1.00  active doc    docs/guide-copy.md  -  Guide

Extend docs/guide.md instead of writing a new document.
```

The score is the share of the query's terms that the document contains, not
document similarity: a one-word query saturates at 1.00, a long query is diluted
by every term it adds. So:

- above ~0.6 - extend the existing document;
- 0.3 - 0.6 - related work exists; say in the new document what it adds;
- below 0.3 - no shared terms; a new document is reasonable.

Search twice with different wording before concluding "nothing exists", and run
`corpus dupes` after drafting. The command prefers active documents; if every
match is retired it says so instead of recommending one.

## Read the report

```bash
corpus report              # incorrect + stale
corpus report --noise      # also orphans, scratch files, directories without an index
corpus report --json       # machine-readable
corpus check               # gate: exit 1 on incorrect
corpus check --strict      # also exit 1 on stale
```

Three severities, in the order you should care:

| severity | what it means | examples |
|---|---|---|
| **incorrect** | a reader is misled | broken local link, byte-identical copy, near-duplicate >= 85%, active doc linking a retired one |
| **stale** | true when written, not now | the code it names changed a week later; near-duplicate 70-85% |
| **noise** | nothing is wrong, there is too much | orphan, scratch file, a directory of 12 docs with no index |

`check` fails on incorrect only, by default. Two exceptions are deliberate:

- a broken link inside a `note`/`report`-kind file (anything under
  `research/`, `notes/`, `drafts/`, `examples/`, `vendor/`) is **noise** - those
  files quote other projects and their relative links were never true here;
- `links-retired` applies to active sources only.

## Then: say when something stops being true

```bash
corpus supersede docs/plan-v1.md --by docs/plan-v2.md
corpus archive docs/old-notes.md
corpus restore docs/old-notes.md      # undo
corpus retired                        # what you recorded
```

That is the only state corpus keeps (`.corpus/status.json`, commit it).
Everything else is recomputed on every run; `.corpus/index.json` is a cache and
belongs in `.gitignore`.

## Triage a pile

When the user asks to clean up documentation, work in this order and report what
you did:

1. `corpus report --noise` and read the counts. Never start by editing files.
2. **incorrect.** Exact duplicates and near-duplicates >= 85% both block: merge
   the content, then `corpus supersede the-copy --by the-keeper` (the report
   names the keeper it chose - most linked, then non-scratch, then shortest).
   Fix broken links. Point retired links at the replacement.
3. **stale.** For each, read the code and update the document, or archive it if
   it no longer describes anything real.
4. **noise, one decision per item.** An orphan is worth linking from an index,
   merging, or archiving. Deleting is the user's call: ask before deleting
   anything you did not create this session.
5. Record every retirement, so the next session does not resurrect it.
6. `corpus check` must exit 0 before you call the cleanup done.

More: [references/findings.md](references/findings.md),
[references/consolidation.md](references/consolidation.md).

## What it looks at

Every `**/*.md` outside build, VCS and agent-state directories. `.claude/`,
`.cursor/`, `.projtruth/`, `.remember/`, `testdata/` and `fixtures/` are skipped:
they hold skills, requirements and machine-produced evidence, which have their
own tools and are a separate corpus - scan them on purpose (`--repo
~/.claude/skills`) if that is what you want.

Code is not an artifact, but a document's backticked paths are checked against
the filesystem: a path that *changed* makes the document stale. With git, the
comparison uses commit times, so a fresh clone - where every mtime is the
checkout time - still reports a document its code has outgrown. A path that no
longer exists at all is not reported - the document may legitimately describe
something that was removed.

## Limits, stated honestly

- Near-duplicates are shingle-based and skip files under 400 characters; two
  documents that say the same thing in different words score low.
- `find` is lexical. Synonyms and paraphrases ("怎么算" vs "如何计算") score low;
  the score is query-term recall, not semantic similarity.
- Only links that point inside the repo are checked; external URLs are not
  fetched.
- A prose mention (`see references/x.md`) counts as a reference, which lowers
  the orphan rate rather than raising false alarms.
- Staleness uses git commit times for tracked paths and mtimes for uncommitted
  edits and non-git trees, with a 7-day grace period (`--stale-days`); a
  document touched for an unrelated reason can still look fresh.
- It does not merge, split, move or delete anything, and it does not judge
  whether a document is correct - only whether it is linked, duplicated, or out
  of date.
