---
name: alien-space-ideation
description: Generate ideas that are coherent but unlikely to occur to you or to Claude's defaults. Splits a corpus (your games, skills, notes, papers) into idea atoms, finds combinations nobody has made, judges them, and ranks them. Use for "fresh ideas", "something genuinely new", stuck brainstorming, mechanics, skill concepts, research directions. Not for judging an existing idea or routine list-making. Dewey: 153.350.
metadata:
  author: TABARC-Code
  author_url: https://github.com/TABARC-Code/
  dewey_decimal_code: "153.350"
  classification_label: "Creative ideation and concept generation"
  version: "1.3.0"
---

# Alien Space Ideation

Author: TABARC-Code

**Layer:** L1 Domain. **Module:** Creative. **Abstraction Level:** Operational.

Ask Claude for a fresh idea and you get the crowded middle of what it has read. Ask a person and you get the middle of their own history. This skill goes looking for the other region: combinations that make sense but that nobody in your corpus has put together.

It is an approximation of a published method, not a reproduction. Read "Honest scope" before trusting any output.

## Use when / don't

Use when the user wants new directions and has, or can supply, a body of existing work to mine. Don't use to grade an idea they already have, for quick brainstorms where a plain list will do, or when there is nothing to mine and no appetite to supply it (say so, offer the plain list).

## Honest scope

From the paper (Artiles et al., arXiv 2603.01092, v3): break papers into idea atoms, score combinations for coherence and for availability, rank for high coherence and low availability, sample atom triples, count strictly new combinations separately, compare diversity against LLM baselines.

Mine, and unvalidated: counting corpus co-occurrence as the availability proxy, the source-coverage stand-in for author communities, the default-ideas channel, the pair-precedent prefilter, the controls and half-versus-half diagnostic, the precedent and theme-collapse checks, rubric-based coherence judging by Claude, the weights in the script. The paper trained models on 16,068 ML papers and tens of thousands of author histories. This skill trains nothing. Its gains are unmeasured, and the paper's own evidence covers ML literature only. Say this to the user once, in the report, not in every reply.

## Procedure (sequential; don't skip a gate)

0. **Frame.** Domain, corpus, what a good idea looks like. Gate: no corpus means set `"unanchored": true` in the JSON (the script caps coherence at 2) and label the report.
1. **Baseline first.** Write 10 default ideas for the bare prompt before anything sees the corpus. Run this as a separate agent with fresh context, given only the prompt, when the session has one. Record the atoms each idea uses. These are the high-availability set (the interpretability trap).
2. **Atomise.** Corpus items to atoms: one reusable concept each (mechanic, technique, constraint, theme), 25 to 60 atoms, synonyms merged. Where you know who made each document (an author, a team, a repo), add it as `source`. The script then counts which sources already use all three atoms. Write the input JSON per `references/example-input.json`.
3. **Pool.** `python3 -I scripts/rank_alien.py pool input.json --n 25`. Gives unseen triples whose pairs have precedent. Output is blind on purpose: no availability numbers, alphabetical order. About 30% are controls from higher-availability triples, so the ranking has something to compare against.
4. **Judge coherence blind and independently.** Use a separate fresh-context agent when the session has one. Give it only the blind pool, an atom glossary, and which documents use which atoms. It must not see the baseline, availability numbers, or which ideas you hope win. With no agent available, judge in-session and say in the report that judging wasn't independent. Judge every triple in the pool; skipping the dull ones ruins the comparison. No `--reveal` until step 5. For each triple write one bridge sentence naming the mechanism that joins all three, and cite a corpus document for each pair that has one. Precedent is a gate, not a score: fewer than two cited pairs means 0. Then score the mechanism: 3 = specific, changes how the work gets done, testable in one sitting; 2 = plausible but generic or hard to test; 1 = only half joins the three; 0 = no mechanism you can state, or "and also". Having all three pairs in the corpus earns nothing extra, because it makes a triple more familiar, not more coherent. Check the cited documents against the corpus before ranking, and treat `diagnostics.precedent_note` as a warning that this rule has slipped.
5. **Rank.** Add scores under `coherence` (0 to 3, atom order free), then `rank` with `--beta 0.5` (change if asked). Report each idea's rank at beta 0 and at beta; the shift shows what unavailability weighting bought. Read `diagnostics`: if the unusual half scores clearly lower on coherence, say so and don't oversell the top ranks.
6. **Decode.** Top five become proposals: premise, the bridge sentence, smallest test, what would kill it.
7. **Collapse check.** `diagnostics.collapse_atoms` names any atom in more than three of the top five. Add `groups` (theme names mapped to atoms) to the input and `collapse_groups` does the same for whole themes, which catches clustering a single atom won't. If either isn't empty, swap in the next ranked from outside that theme, and merge near-duplicates. Report `distinct_atoms_top5` against `distinct_atoms_baseline`.
8. **Feedback.** See loops below. Log keep/kill with a reason.

Every gate that fails goes in the report in plain words. A blank beats a made-up score.

The script is required above 12 atoms: 25 atoms already make 2,300 triples. If `scripts/` is missing, get it from the repo. Failing that, cap the vocabulary at 12 atoms (220 triples), count by hand, and say so in the report. Ties are settled by a fixed hash, not the alphabet, so a shift between equal-coherence ideas at beta 0 is availability doing its job, not a finding.

## Feedback loops

Record each round's decisions in a small JSON file and run `python3 -I scripts/rank_alien.py feedback input.json decisions.json --out next.json --ledger ledger.md` (format in the script header). The script does the bookkeeping, so nobody hand-edits the input.

Positive: a kept idea becomes a `docs` entry, so its triple stops being alien and its pairs gain precedent for the next round.

Negative: a kill for `incoherent` names the offending pair and puts it on the `blacklist`, which both modes then refuse until the user lifts it. A kill for `obvious` appends the triple's atoms to `baseline`. A kill for `off-brief` goes in the ledger and into step 0's framing.

Skills keep improving by these loops. The ledger records round, beta, judge, kept, kills with reasons, and rubric changes. The script warns if the same kill reason turns up three rounds running, because then the rubric or the atoms are wrong, not the user.

## Information flow, both ways

Takes in: other skills' outputs as corpus (finished designs, skill lists, notes). Hands out: atoms, the ledger, and proposals as design seeds. Candidates below are not accepted links until each end carries a matching contract.

| Candidate | Out of this skill | Into this skill | Status |
|---|---|---|---|
| skill-builder | proposals into its creative exploration stage | installed skills as corpus | candidate |
| card-game-designer, wargame-designer, boardgame-design-hydra | proposals as design seeds | finished designs as corpus | candidate |
| kaizen | ledger as audit input | defect reports on the rubric | candidate |
| answer-key-retrofit | step 4 rubric for audit | external-standard patch | candidate, not seen in this session's skill list |

## Failure risks

| Failure | Type | Guard |
|---|---|---|
| Cross-domain triples look alien only because no document spans both | Logical inconsistency | pair-precedent prefilter; judge on bridge sentence |
| Claude grades its own homework | Inconsistent evaluation | separate judge agent; script-enforced blind pool; citations checked against the corpus; unanchored cap in code |
| Judging rewards familiarity | Inconsistent evaluation | precedent is a gate only; `precedent_note` flags the drift |
| Novelty by nonsense | Overgeneration | coherence is a gate, not a weight; diagnostics flag a coherence penalty |
| Everything converges on one theme | Overgeneration | `collapse_atoms` and `collapse_groups` from the script, then step 7 |
| Malformed scores or keys silently skew ranks | Format Error | script refuses bad input with exit 2 |
| The strangest triples never reach the pool | Missed Trigger (by design) | default needs two pairs with precedent; `--min-pairs-seen 1` widens it, at a cost in noise |
| Overclaiming the paper's results | Hallucination | Honest scope; `references/method-notes.md` |

Tests: `python3 -I evals/probe_ranker.py` (64 checks on the script) and `references/evals.md` (10 behavioural evals; two exercised in a real round, none formally scored). Quick check: `python3 -I scripts/rank_alien.py selftest`.
