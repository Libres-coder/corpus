# Consolidating a pile

A worked session. The goal is not "fewer files" - it is that every document has
a reader, a purpose, and a place in the index.

## 0. Measure first

```bash
python -m corpus report --noise
```

```
292 artifacts · ~528888 tokens if all loaded · 1 incorrect · 1 stale · 19 noise
```

Write the three numbers down. You will compare against them at the end; without
that, "tidied" is an opinion.

If the repository has never had an index, expect a high orphan rate. Treat that
as the starting point, not a failure.

## 1. Incorrect

Handle every one. They are small and they are the only things that actively
mislead.

- **exact duplicates** - pick the survivor by which path is linked from
  somewhere else, or by the shorter path. `git log --follow` on both says which
  one is a copy. Merge, fix links, delete.
- **broken links** - open the file, read the sentence around the link, decide:
  fix the path, or delete the clause. A link to a document that no longer exists
  is a claim that used to be true.
- **links to retired docs** - the replacement is recorded in
  `.corpus/status.json`; point the link there.

Re-run `corpus check` after each batch. It must reach zero.

## 2. Stale

For each finding: read the referenced code, then either update the document or
archive it.

Archiving is the honest choice when the document describes something that no
longer exists. `corpus archive path` keeps the file; it stops being treated as
truth, and links to it become incorrect, which forces the next cleanup to deal
with them.

Do not "refresh" a document by touching its mtime. The check compares against the
code it names, and a fake touch is exactly the kind of lie this tool exists to
catch.

## 3. Noise, one decision at a time

Nine out of ten orphans are one of:

| shape | decision |
|---|---|
| research notes whose conclusion already shipped | archive the whole directory; cite the commit that shipped it |
| a draft superseded by the real document | `corpus supersede draft --by real` |
| a reference file only reachable from a SKILL.md | nothing - it is already referenced; check you scanned the root |
| a one-off report | archive, or move it under `docs/reports/` with a date |
| genuinely useful, unreferenced | link it from the nearest README |

Anything you cannot classify, leave alone and list for the user. "I did not
understand this file" is a valid outcome; deleting it is not.

## 4. Leave an index, not a rule

For every directory that had `no-index`, write a README.md:

```markdown
# docs/protocols

- [handshake.md](handshake.md) - the wire format, updated 2026-10
- [errors.md](errors.md) - error codes clients can receive
- [legacy/](legacy/) - pre-2.0, kept for the migration guide only
```

Three lines per directory beat any policy document, because the next agent reads
the README before inventing a fourth file.

## 5. Close the loop

```bash
python -m corpus check --strict
```

Compare the three numbers with step 0. Record the decisions you made in the
commit message: which files were archived and why. That message is the only
memory a future session will have.

## What not to do

- Do not delete documents in bulk to make the numbers look good.
- Do not merge unrelated documents into one "everything.md" - one reader, one
  goal, one document. Splitting is as valid as merging.
- Do not add corpus to CI before the repository is clean; a gate that fails from
  day one gets disabled by day three.
- Do not rename files to dodge a finding. The finding is about the document, not
  the name.
