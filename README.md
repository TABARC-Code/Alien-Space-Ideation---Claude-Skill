# alien-space-ideation

**Author:** TABARC-Code · **Licence:** MIT

A Claude skill for finding ideas that hold together but that nobody in your own body of work has combined yet.

Ask a model for something new and you get the middle of the road, the ideas everyone reaches for first. Ask yourself and you get the middle of your own history. This skill goes to the edges. You give it a corpus (your games, notes, skills, papers). It breaks that into small reusable concepts, lists the three-way combinations that appear nowhere in the corpus, and ranks the ones that still make sense.

The method is borrowed from Artiles et al., *The Alien Space of Science* (arXiv 2603.01092). This is an approximation of it, not a reproduction. See Limitations.

## What it does

1. A separate agent writes ten ordinary ideas for your prompt before anything sees the corpus, so the common ground is on the table.
2. Your corpus is split into atoms: one mechanic, technique, constraint, or theme each.
3. The script lists triples of atoms that no document combines, where at least two of the three pairs do appear together somewhere.
4. Another fresh agent scores each triple from 0 to 3 on whether the mechanism joining it actually works. It cites a corpus document for each pair. The citations get checked.
5. The script ranks the survivors with and without a weighting towards unusual combinations, so you can see what the weighting changed.
6. The top five are written up: premise, bridge, smallest test, and what would kill it.

The script does the counting and the rule enforcement. The judging stays with a person or a model, because a script can't tell you whether three mechanics fit together.

## Status

Working and checked: the `pool`, `rank`, and `selftest` modes, input validation, the blind pool, and the diagnostics. The 41 checks in `evals/probe_ranker.py` pass.

Tried once on real material: a corpus of 89 installed Claude skills. The first judging pass turned up a rubric that rewarded familiarity, and the rubric was changed. The second pass produced five proposals that don't overlap the ordinary ideas, though two of them partly overlap skills that already exist.

Not done: the ten behavioural evals in `references/evals.md` haven't been run formally. The availability weights are untuned guesses.

## Requirements

- Python 3 for the script. Standard library only. Developed on 3.13.
- A Claude setup that supports skills, for the full workflow. The ideal is one that can run separate agents, so the baseline and the judging stay independent. The script runs fine on its own.

## Installation

Add `SKILL.md` as a skill in your Claude app and keep `scripts/` and `references/` alongside it. How you add a skill depends on the app, so follow its own instructions. I haven't tested any particular install route beyond running the script from this folder.

The script matters. Twenty-five atoms already make 2,300 triples, so without it the skill caps itself at 12 atoms.

## Try the script

From this folder:

```bash
python3 -I scripts/rank_alien.py selftest
python3 -I evals/probe_ranker.py
python3 -I scripts/rank_alien.py pool references/example-input.json --n 10
```

You should see `selftest: PASS`, then `41/41 passed`, then a JSON list of triples. The example only has 10 atoms, so you'll also get a warning on stderr that 25 to 60 is recommended. That's expected.

The pool is blind on purpose: no availability numbers, alphabetical order, and about 30% of the entries are ordinary triples included as controls. `--reveal` shows everything. Use it yourself, not for the judging pass.

To rank, add a score from 0 to 3 for every triple under `coherence`, keys in any atom order:

```json
"coherence": {
  "dice-pool|legacy-campaign|narrative-prompts": 3,
  "asymmetric-factions|dice-pool|push-your-luck": 2
}
```

then run:

```bash
python3 -I scripts/rank_alien.py rank your-input.json --beta 0.5
```

## Input file

| Field | What it holds |
|---|---|
| `atoms` | List of atom names. No `\|` characters. |
| `docs` | Each corpus document and its atoms. Either a list, or `{"atoms": [...], "source": "who made it"}`. |
| `baseline` | Atoms used by the ten ordinary ideas. |
| `groups` | Optional. Theme names mapped to atoms, for spotting one theme hogging the results. |
| `blacklist` | Pairs of atoms you've rejected as incoherent. Never pooled or ranked. |
| `coherence` | Scores from 0 to 3, one per judged triple. |
| `unanchored` | `true` if there's no real corpus. Caps every score at 2. |

When documents carry a `source` (an author, a team, a repo), the script also counts how many sources already work with all three atoms. That's closer to the paper's question of who could plausibly propose an idea. Without sources, that part switches off.

`references/example-input.json` is a complete working example.

## Reading the results

`rank` prints the ranked triples, each with its rank at beta 0 and at your beta, plus a `diagnostics` block:

- `collapse_atoms` and `collapse_groups` name any atom or theme that turns up in more than three of the top five.
- `precedent_note` warns if scores are rising with how familiar a triple is. That means the judging has drifted into rewarding the ordinary.
- `mean_coherence_low_availability_half` and `mean_coherence_high_availability_half` compare the unusual half with the ordinary half. If the unusual half scores clearly lower, the novelty is costing you coherence.
- `distinct_atoms_top5` and `distinct_atoms_baseline` show how widely the results range compared with the ordinary ideas.

Triples that already exist in the corpus are dropped, and so is anything scored below 2. Bad input exits with a one-line error rather than a stack trace or a quietly wrong ranking.

## Limitations

- The paper trained models on 16,068 machine learning papers. This trains nothing. Counts stand in for the availability model, and a written rubric stands in for the coherence model.
- The paper's evidence covers machine learning literature only. One real round on a skills corpus isn't evidence it works elsewhere.
- Judging uses one model per run. A separate agent helps, but it isn't a human panel.
- By default a triple needs two pairs with precedent, which keeps out the strangest combinations. `--min-pairs-seen 1` lets more through, at the cost of more noise.
- Small corpora give thin pools. The script warns outside 25 to 60 atoms, and again above 150, where it gets slow.

## Layout

```text
SKILL.md                      the procedure Claude follows
scripts/rank_alien.py         pool, rank, selftest (stdlib only)
evals/probe_ranker.py         41 checks on the script
references/example-input.json
references/method-notes.md    what comes from the paper and what doesn't
references/evals.md           behavioural evals
LICENSE                       MIT
README.md, description.md
```
