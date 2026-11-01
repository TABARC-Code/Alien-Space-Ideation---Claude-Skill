# Method notes: what is the paper's and what is mine

Author: TABARC-Code. Checked against arXiv 2603.01092 (v3, 21 Oct 2026, NeurIPS 2026 main track). The final part of the appendix was not checked.

| Claim | Status | Where |
|---|---|---|
| Papers decomposed into idea atoms; 16,068 LLM papers | Confirmed | abstract |
| Coherence model plus availability model; rank for high coherence, low availability | Confirmed | abstract |
| Sampling is over atom triples | Confirmed | v2 PDF figure text |
| Pre-2025 data only for temporal validation; under 1% of candidates recovers 2025 combinations at 35.9x chance; 3.24x for strictly novel | Confirmed | abstract |
| Judge Decoding (ICLR 2025 oral) moves from rank 1,489 to rank 1 of 1.14M at beta 0.5 to 0.6 | Confirmed | v3 HTML |
| Human review: ten raters, 40 blinded reviews; Alien had 3 of the top 5 reports | Confirmed | v3 HTML |
| Claude interpretability reports 2/10 to 8/10 after the autoresearch pipeline; Alien 0/10 | Confirmed, with the before/after caveat | v3 HTML |
| Number of atoms | Changed across versions: about 2,500 (v1), 273 (v3) | v1, v3 HTML |
| Researchers in availability model | Disputed across sources: 39,791 (author's HN post), 25,722 kept of 26,462 (v3 text as read) | HN, v3 HTML |
| Lacuna, 25,000 proposals, medicine extension | Not in the paper text read; Lacuna exists as a separate site | Tiptree Systems |

## Mine, not the paper's (unvalidated)

- Availability as a weighted blend of log-scaled pair co-occurrence (0.45), default-ideas overlap (0.1875), log-scaled atom usage (0.1125) and source coverage (0.25). Without sources, the coverage weight is shared out in proportion, which gives 0.60, 0.25 and 0.15.
- Source coverage: the share of sources whose combined documents contain all three atoms. A rough stand-in for the paper's author-community availability model.
- Pair-precedent prefilter (`--min-pairs-seen`, default 2).
- Coherence as a 0 to 3 rubric on the mechanism alone, with precedent for two pairs as a gate and a ranking gate at 2. Judged by a fresh agent, and the citations are checked against the corpus.
- Precedent diagnostic (do scores rise with how many pairs have precedent?) and theme-group collapse check.
- Score at beta: (1 - beta) x coherence/3 + beta x (1 - availability). The paper's own beta formulation was not checked; this is the same idea, not a copy.
- Strictly-novel filter applied to every ranked triple.
- Controls (default 30% of the pool, drawn evenly from higher-availability triples) and the half-versus-half coherence diagnostic. The paper compares against LLM baselines; this is a cheap in-corpus stand-in.
- Blacklist, unanchored cap and collapse flag: feedback and safety rules of the skill, enforced in the script.

If a later run of this skill shows these choices matter, change them here and in the script header together.
