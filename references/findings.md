# Findings

Every finding names one file, says what is wrong, and gives one action. The
action is a suggestion, not a command corpus will run.

## incorrect - someone reading this is misled

### duplicate-exact
Two files with the same bytes. One of them is a copy someone forgot.

*Cause:* a copy operation, a vendored directory, or an agent recreating a file
it could not find. *Act:* keep the one that is linked or named in an index,
delete the other. If both are linked, fix the links first, then delete.

### duplicate-near (>= 0.85)
Almost the same text: usually one was edited and the other was not. Only files
longer than 400 characters are compared - below that, boilerplate provenance
files and one-line stubs collide by accident. This is the
most dangerous finding - two documents that disagree slightly and look equally
authoritative.

*Act:* merge into the larger one, then `corpus supersede the-smaller --by
the-larger`. Do not delete before merging: the smaller one may hold the fix.

### broken-link
A markdown link whose local target does not exist. Only *links* count, not
backticked mentions - a mention is usually an example (`name it R3-x.md`).

*Cause:* a moved file, a renamed directory, a note copied from another project.
*Act:* fix the target, or remove the link if the target is gone for good.

In `note` / `report` kind files (anything under research/, notes/, drafts/,
examples/, vendor/) a broken link is downgraded to noise: those files quote
other projects and their relative links were never true here.

### links-retired
An active document links to one you marked `superseded` or `archived`.

*Act:* point the link at the replacement named in the status entry, or at the
section that now holds the truth. If there is no replacement, the older document
was archived too early.

## stale - true when written, not now

### stale
The document names files (`backticked/path.py`) and the newest of them changed
more than `--stale-days` (7 by default) after the document was last touched.

*Act:* read the code, update the document. If the document no longer describes
anything real, archive it. A document touched yesterday is never stale - the
week is there so work in progress does not produce noise.

### duplicate-near (0.70 - 0.85)
Same topic, different text. Often legitimate (a design doc and a how-to), often
not. Read both; if one is a subset of the other, merge.

## noise - nothing is wrong, there is too much

### orphan
Nothing links to it, and no README or INDEX mentions it. It was written and then
abandoned.

*Act:* one of three - link it from an index, merge it into something linked, or
archive it. Do not delete a document you did not write without asking.

### scratch
A name that looks temporary: `tmp-`, `draft-`, `wip-`, `scratch-`, `copy`,
`old-`, `backup-`, `untitled`.

*Act:* delete it if it is yours, rename it if it is real.

### no-index
Eight or more documents in one directory and none of them is a README or INDEX.

*Act:* write a README.md listing them with one line each - that single file turns
a directory into a navigable set, and gives every document an inbound link.

## What corpus will not tell you

- Whether a document is *correct*. It checks structure, not claims.
- Whether two documents written differently say the same thing.
- Whether a plan was executed. That is `projtruth`'s job.
