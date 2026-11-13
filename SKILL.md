---
name: corpus
description: >-
  Governs the documents an agent writes into a repository - docs, plans, specs,
  notes, reports, skills. Answers "does this already exist?", finds near
  duplicates, orphans, broken local links and documents older than the code they
  describe, and records which document replaced which. Use before creating a new
  markdown file, when a repo has accumulated too many stale or duplicated docs,
  when consolidating notes, plans or research, or when the user asks to tidy or
  audit the documentation (整理文档, 重复的文档, 文档过期, 该写在哪, 仓库太乱,
  文档治理, 屎山, 内容越堆越乱). Not for: code structure (graphify), skill trigger
  conflicts (skill-audit), requirements and evidence (projtruth), or prose style
  (writing-standards / tech-doc-style-chinese).
---

# corpus

Agents add documents. Nobody removes them. After a few weeks a repo has three
plans for the same feature, a README that describes an API that moved, and
forty notes nothing links to. `corpus` is the governor for that pile: it
indexes every document, finds what is wrong, and records what replaced what.

It never deletes or moves a file. It reports, and it remembers decisions.

## The one rule that prevents sprawl

**Before writing a new document, ask what already covers it.**

```bash
python -m corpus find "how to deploy to staging"
```

```
Closest artifacts to 'how to deploy to staging':
  0.71  active readme skill-audit/README.md  - Audit installed Claude Code skills
  0.43  active doc    projtruth/README.md    - projtruth
Extend skill-audit/README.md instead of writing a new document.
```

A second document on the same topic is how the pile starts. If the score is
above ~0.6, extend the existing file; between 0.3 and 0.6, write only if you can
say in the new document what it adds; below 0.3, a new file is justified.

## Then: say when something stops being true

```bash
python -m corpus supersede docs/plan-v1.md --by docs/plan-v2.md
python -m corpus archive docs/old-notes.md
python -m corpus restore docs/old-notes.md      # undo
```

That is the only state corpus keeps (`.corpus/status.json`). Everything else it
recomputes from the files. A document that links to a superseded one is then
reported as **incorrect** - the reader would follow it to something that is no
longer true.

## Read the report

```bash
python -m corpus report              # incorrect + stale only
python -m corpus report --noise      # also orphans, scratch files, dirs without an index
python -m corpus check               # gate: fails on incorrect
python -m corpus check --strict      # also fails on stale
```

Three severities, in the order you should care:

| severity | what it means | examples |
|---|---|---|
| **incorrect** | someone reading this is misled | broken local link, two copies of the same text, link to a retired document |
| **stale** | true when written, not now | the code it names changed a week later |
| **noise** | nothing is wrong, there is just too much | orphan (nothing links to it), scratch file, a directory of 12 docs with no index |

Only `incorrect` fails a commit. Stale and noise are judgement calls, reported
with a suggested action.

## Triage a pile

When the user asks to clean up documentation, do this in order - and report what
you did, not what you could do:

1. `corpus report --noise` and read the counts. Never start by editing files.
2. **incorrect first.** Merge exact duplicates (keep the one that is linked),
   fix broken links, point retired links at the replacement.
3. **stale second.** For each, read the code and update the document, or archive
   it if the document no longer describes anything real.
4. **noise last, and only with a decision per item.** An orphan is either worth
   linking from an index, worth merging, or worth archiving. Deleting is the
   user's call, not yours - ask when the file has content you did not write.
5. Record every retirement with `corpus supersede` / `corpus archive`, so the
   next session does not resurrect it.
6. `corpus check` must exit 0 before you call the cleanup done.

More: [references/findings.md](references/findings.md),
[references/consolidation.md](references/consolidation.md).

## What it looks at

Every `**/*.md` outside build/VCS directories, by default. Add globs with
`--glob` (`--glob "**/*.mdx"`), skip directories with `--ignore`. Code is not an
artifact, but a document's backticked paths are checked against the filesystem,
so a document naming code that moved shows up as stale.

`report`, `find`, `dupes` and `check` never write into the scanned tree;
`corpus scan` writes `.corpus/index.json`, which is a cache - commit it or
ignore it.

## Limits, stated honestly

- Near-duplicates are shingle-based; two documents that say the same thing in
  different words score low and will be missed. The report never claims
  "no duplicates anywhere", only "none found at this threshold".
- Only links that point inside the repo are checked. External links are not
  fetched (that is `lychee`'s job).
- A prose mention (`see references/x.md`) counts as a reference, so a file named
  in an example can look "linked". It lowers the orphan rate rather than raising
  false alarms - the safer direction.
- Staleness is mtime-based with a grace period (7 days by default,
  `--stale-days`); a document edited for an unrelated reason looks fresh.
- It does not move, rename or delete anything, and it does not rewrite
  documents. Merging text is the agent's job, guided by the findings.
