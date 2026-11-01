# Project description

## The short version

alien-space-ideation looks for ideas that make sense but that nobody in your corpus has put together. It's a Claude skill plus a small Python script. Separate agents do the judging. The script does the counting and enforces the rules.

## The problem

Language models drift towards the crowded middle of whatever they've read. Asked for a research idea, they keep offering the same few topics. People do something similar. Your background and the people you work with decide which combinations you'd ever think to try, so plenty of workable ideas stay unproposed because nobody is standing in the right spot.

Artiles et al. (arXiv 2603.01092) tackled this by splitting papers into small concepts, training one model to judge whether a set of concepts is coherent and another to judge whether any existing community would combine them, then ranking for high coherence and low availability. That needs 16,068 papers and trained models. Most people have a folder of notes.

## The approach

Keep the idea, drop the training.

- Atoms come from your own corpus. A mechanic, a technique, a constraint.
- Availability is counted rather than learned. It blends how often each pair of atoms appears together, whether the ordinary ideas already use the combination, how heavily the corpus leans on each atom, and, when documents name their source, how many sources already work with all three atoms.
- Coherence is judged by a fresh agent against a written rubric, with corpus citations that get checked.
- The unit is the atom triple, as in the paper.

## Design decisions

**The pool is blind.** The judge never sees availability numbers, and the output is alphabetical so the order doesn't leak them either. A judge who knows which triples are the unusual ones tends to find them coherent. The script enforces it, because a rule that only exists in prose gets skipped.

**Precedent is a gate, not a score.** The first real round showed why. The rubric gave the top score only when all three pairs already appeared in the corpus, so the two highest-scoring triples were both ordinary controls, and familiar triples averaged 1.35 points higher. Precedent now only has to exist for two pairs, and the score is about the mechanism alone. The script's `precedent_note` watches for the bias coming back.

**Coherence is a gate, not a weight.** Anything scoring below 2 is dropped before ranking. Blending coherence with novelty lets nonsense through on the strength of being strange.

**Separate agents for the baseline and the judging.** The same session writing the ordinary ideas, building the atoms and scoring the results would be marking its own work. Splitting them is cheap and catches some of that. Not all, because they're still the same model family.

**Controls.** About 30% of the pool comes from ordinary triples. They give the ranking something to compare against, and they're how the precedent bias above was spotted.

**Log-scaled counts.** One heavily repeated pair used to flatten every other count, because everything was scaled against the busiest pair. Log scaling keeps a single noisy document from setting the scale for the rest.

**Sources as a stand-in for communities.** The paper asks whether any existing author is placed to propose an idea. Tagging documents with a source lets the script ask a rougher version: does anyone's body of work already contain all three atoms, even if never together?

**Theme groups.** Single atoms can be spread evenly while one theme still takes four of the top five places. That's what happened in the first real round. Optional `groups` let the script flag it.

**Feedback goes back into the input, and the script does it.** A kept idea becomes a new corpus document. A rejected pair goes on the blacklist. An obvious idea adds to the baseline. Each round starts from a slightly different map. This used to be hand-edited JSON, which is exactly where mistakes creep in, so it's a command now, and it logs each round once.

**Ties go by a hash, not the alphabet.** Plenty of triples score identically, and breaking those ties alphabetically meant atoms near the start of the alphabet won every coin flip. A fixed hash is just as repeatable and has no favourites. This was a bug in the first published version.

## Trust and boundaries

Everything is local. The script reads one JSON file, writes to stdout, and makes no network calls. Corpus text is treated as data, not instructions. The weights are the author's and are exposed as command-line options.

## Current state

v1.3.0. Working and checked: the pool, rank and selftest modes, validation, blacklist, unanchored cap, source coverage, log scaling, and the collapse, coherence and precedent diagnostics. All 64 checks in `evals/probe_ranker.py` pass.

One real round has run, on a corpus of installed skills. It found and fixed the precedent bias, and it produced five proposals with tests and kill conditions.

Not yet done: formal scoring of the ten behavioural evals, and any tuning of the weights against kept and rejected ideas.

## Limitations and awkward bits

Availability built from counts is a long way from a model trained on the publishing histories of tens of thousands of researchers. Cross-domain triples look alien partly because no single document spans both domains, so they need the most scepticism. The independent judge is independent of the session but not of the model family. And atom tagging is itself a judgement call that nothing checks yet.

## Future direction

Score the behavioural evals in a clean session. Run more rounds, keep the ledger, and tune the weights against what gets kept and killed, rather than guessing. A second judge from a different model, compared against the first, would show how much of each score belongs to the model rather than the idea.
