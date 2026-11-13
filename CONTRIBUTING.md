# Contributing

Small tool, two rules:

- **Standard library only.** No runtime dependencies, Python 3.8+.
- **A finding must be defensible.** If a rule cannot explain itself in one
  sentence with an example, it will be wrong on real repositories and gets
  switched off. False positives cost more than missed findings here.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

## Dogfood

```bash
python -m corpus --repo <some real repository> report --noise
```

Run it on a repository whose documents you actually know before and after a
change. Every heuristic in this tool was tuned against a real 292-document tree;
a rule that only works on fixtures does not work.

## Adding a finding

1. It needs a severity: would a reader be *misled* (incorrect), *out of date*
   (stale), or just *overwhelmed* (noise)?
2. It needs an action the reader can perform without judgement - "merge X into
   Y" beats "review this".
3. It needs a false-positive story in `references/findings.md`: when is this
   finding *not* a problem?
4. Add a test that fails without it.
