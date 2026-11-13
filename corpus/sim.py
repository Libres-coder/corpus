"""corpus similarity: word/CJK tokens, shingles, Jaccard, candidate pruning.

Chinese text has no spaces, so a whitespace tokenizer sees a whole paragraph as
one token. Here every CJK character is its own token and runs of ASCII
letters/digits/underscore stay together - good enough for near-duplicate
detection without a segmenter.
"""
import re

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

SHINGLE = 4
# A shingle appearing in more than this many documents is boilerplate
# ("license", "installation"); it cannot help tell two documents apart.
COMMON_DF = 20


def tokens(text, strip_code=False):
    if strip_code:
        text = FENCE_RE.sub(" ", text)
    return TOKEN_RE.findall(text.lower())


def shingles(toks, k=SHINGLE):
    if not toks:
        return set()
    if len(toks) <= k:
        return {tuple(toks)}
    return {tuple(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a) + len(b) - inter
    return inter / float(union) if union else 0.0


def _candidate_pairs(sets, min_shared=3):
    """Pairs that share at least `min_shared` shingles, via an inverted index."""
    index = {}
    for key, sh in sets.items():
        for s in sh:
            index.setdefault(s, []).append(key)
    shared = {}
    for s, docs in index.items():
        if len(docs) < 2 or len(docs) > COMMON_DF:
            continue
        docs = sorted(docs)
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                pair = (docs[i], docs[j])
                shared[pair] = shared.get(pair, 0) + 1
    return [p for p, n in shared.items() if n >= min_shared]


def near_duplicates(docs, threshold=0.7):
    """docs: {key: text}. Return [(key_a, key_b, score)] at or above threshold.

    Two stages so a few thousand files stay fast: an inverted index proposes
    pairs that share rare shingles, then exact Jaccard decides.
    """
    sets = {}
    for key, text in docs.items():
        sets[key] = shingles(tokens(text, strip_code=True))
    out = []
    for a, b in _candidate_pairs(sets):
        score = jaccard(sets[a], sets[b])
        if score >= threshold:
            out.append((a, b, round(score, 3)))
    out.sort(key=lambda t: -t[2])
    return out


STOP = {"the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "with",
        "is", "are", "was", "be", "by", "as", "at", "it", "this", "that", "from"}


def terms(text):
    """Distinct match terms: ASCII words, plus CJK character bigrams.

    A single CJK character appears in almost every Chinese document, so
    unigrams drown the score; bigrams ("发布", "技能") carry the meaning.
    """
    toks = tokens(text, strip_code=True)
    out = set(t for t in toks if len(t) > 1 and t not in STOP)
    cjk = [t for t in toks if len(t) == 1 and "一" <= t <= "鿿"]
    bigrams = set(a + b for a, b in zip(cjk, cjk[1:]))
    out |= bigrams
    if not bigrams:
        out |= set(cjk)
    return out


def score_against(query, text):
    """Share of the query's terms that the document contains (0..1)."""
    q = terms(query)
    if not q:
        return 0.0
    d = terms(text)
    return len(q & d) / float(len(q))
