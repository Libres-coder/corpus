# Changelog

## [0.1.7] - 2026-11-14

### Fixed
- A link to a dangling symlink is broken again. `exists_exact` compares the
  names `listdir` returns (so case is exact on every platform), but a name is
  not a target: the final component is now checked with `os.path.exists`, so
  the 0.1.6 case fix does not silently start accepting a symlink whose target
  is gone.

## [0.1.6] - 2026-11-14

### Fixed
- **Local links resolve with the case of a Linux checkout, on every platform.**
  Windows resolved `docs/Guide.md` for a link to `docs/guide.md`, so the same
  repository passed `corpus check` locally and failed it in CI - the finding
  was real (GitHub serves paths case-sensitively), but only one platform saw
  it. `scan.exists_exact` walks the path components and compares the names
  `listdir` returns; broken links, the stale-reference lookup and the
  "deleted then restored" test all use it now. Strictly a consistency fix:
  no new findings on the repositories this was tested against.

## [0.1.5] - 2026-11-14

### Fixed
- **A gitignored runtime path is not a missing reference.** A document may name
  state the tool itself writes - "the reading goes to `.lifecycle/context.json`".
  If that path was once committed and later removed and ignored, the
  `missing-ref` check reported it as a dead reference on any machine where the
  file did not happen to exist. Reported by lifecycle's CI on Linux, where three
  documents were flagged; on Windows the ignored file existed locally and hid
  the finding. `git check-ignore` now decides, so the check gives the same
  answer on every platform.

## [0.1.4] - 2026-11-14

### Added
- **A document that still names a file deleted from the repository is
  incorrect** (`missing-ref`). It is judged against the paths git says were
  deleted, so a README's `src/foo.py` example is not flagged - the first
  version of the check did flag exactly that, and a doc checker that reports
  examples teaches people to ignore it.

## [0.1.3] - 2026-11-13

### Fixed
- `_template.md` files written by `lifecycle pack init` were scanned as
  documents, so every chapter or quest template looked like an orphan or a
  duplicate. Scaffold templates are not documents; they are skipped now.

## [0.1.2] - 2026-11-13

### Fixed
- `SKILL.md` was never classified as a skill: the rule compared against
  "SKILL.md" after the path had been lowercased. Every skill file was treated as
  an ordinary document, which changed its orphan status.
- `.lifecycle/` (sibling tool state: compaction snapshots) is ignored, like
  `.projtruth/` and `.claude/`.

## [0.1.1] - 2026-11-13

### Fixed
- `copy-voice.md` and `api-status-copy.md` were reported as scratch files; the
  scratch rule no longer treats "copy" as temporary (duplicate detection already
  covers real copies).
- `SOURCE.md` provenance files are not artifacts; scanning them produced orphan
  findings in every vendored skill.

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
