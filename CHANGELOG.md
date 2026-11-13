# Changelog

## [0.1.0] - 2026-11-13

### Added
- `scan`: inventory every markdown artifact, its title, kind, links, backticked
  path references and content hash.
- `find`: term-overlap ranking with CJK bigrams, so "does this topic already
  exist?" works for Chinese and English.
- `report`: findings in three severities - incorrect (broken local links, exact
  and near duplicates, links to retired documents), stale (the referenced code
  changed after a grace period), noise (orphans, scratch files, directories with
  no index).
- `dupes`: near-duplicate pairs with the one to keep.
- `supersede` / `archive` / `restore` / `retired`: the only hand-kept state,
  `.corpus/status.json`.
- `check [--strict]`: CI gate on incorrect findings (and stale with `--strict`).
- `SKILL.md` with the pre-write rule, the triage order and honest limits.
- 19 tests.
