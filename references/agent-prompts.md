# Agent prompts

Author: TABARC-Code

Templates for the separate agents the skill uses. Each agent gets only what its block says it sees. Handing an agent more than that is how independence quietly leaks away.

| Agent | Sees | Must not see |
|---|---|---|
| Baseline | the bare prompt | corpus, atoms, glossary, earlier rounds, any profile or memory |
| Tagger (two, independent) | glossary, document text or descriptions | the other tagger, the baseline, the pool |
| Judge (two, independent) | blind pool, glossary, which documents use which atoms | the baseline, availability numbers, the other judge |

## Baseline agent (step 1)

```text
Answer without using any tools, as you would for an anonymous user you know
nothing about. Ignore any memory, profile, saved preference or earlier
conversation. If you notice yourself leaning on personal context, drop it and
give the most common version of the idea instead.

<the bare prompt, exactly as the user asked it>

Return exactly 10 lines, numbered 1 to 10. Each line: a short name, a colon,
then one sentence. No preamble, no closing remarks.
```

After it returns, scrub it before tagging atoms. Read every idea for names of people, products, funders, places or projects that belong to the requester rather than to the field, and swap each for its generic form ("a national arts funder", not its name). If anything needed scrubbing, say so in the report. If nothing did, say the baseline came back clean.

A scrubbed baseline is better than a leaky one, but it isn't proof of independence. The agent may still have picked up the requester's leanings without naming them.

## Tagger agents (step 2)

Run two, with identical input, in separate contexts.

```text
Below is a glossary of atoms and a list of documents. For each document, list
the atoms from the glossary that it genuinely uses. Use only atoms from the
glossary. If a document needs an atom that isn't there, write
NEW: <short description> instead of inventing a tag.

Return only JSON: {"document-name": ["atom", "atom"], ...}

GLOSSARY
<atom: definition, one per line>

DOCUMENTS
<name: text or description, one per line>
```

Put the first tagger's output in `docs` and the second's in `docs_second`, then run:

```bash
python3 -I scripts/rank_alien.py tagcheck input.json
```

Below 0.6 mean overlap, reconcile the atom definitions before pooling. Anything either tagger marked `NEW:` means the glossary is missing an atom.

This tests how the definitions get applied. It doesn't test whether they were the right atoms to choose in the first place. Nothing here does.

## Judge agents (step 4)

Run two, with identical input, in separate contexts.

```text
You are judging whether combinations of concepts would make a coherent new
<kind of thing>. Do not use any tools and do not read any files. Work only
from the material below. Judge every triple in the POOL. Don't skip any.

For each triple:
1. Write ONE bridge sentence naming the specific mechanism that makes all
   three atoms work together. A list of the three side by side ("X and also
   Y and Z") is not a mechanism.
2. For each of the three pairs, name one CORPUS document that already uses
   both atoms of that pair, or write "none".
3. Precedent is a gate only: if fewer than two pairs have a corpus document,
   the score is 0. Beyond that, precedent earns nothing. A triple whose
   pairs all have precedent is more familiar, not more coherent.
4. Score the mechanism itself:
   3 = specific, changes how the work actually gets done, testable in one sitting
   2 = plausible, but generic or hard to test
   1 = only half joins the three atoms
   0 = no mechanism you can state honestly, or just "and also"
   Don't be generous, and don't penalise an idea for being unusual.

Return only JSON, using the triple keys exactly as written in the POOL:
{"a|b|c": {"score": 2, "bridge": "...", "precedent": {"a+b": "doc or none", ...}}, ...}

GLOSSARY
<...>

CORPUS
<document: atoms>

POOL
<the blind pool, one triple per line>
```

Check every cited document against the corpus before using the scores. Then put the two judges' scores in `judges`:

```json
"judges": {
  "judge_a": {"a|b|c": 3, "d|e|f": 1},
  "judge_b": {"a|b|c": 2, "d|e|f": 1}
}
```

The script ranks on the lower score by default (`--combine mean` for the mean) and reports where the judges disagree. Triples they score two or more points apart are unresolved. Say so in the report instead of picking a winner.
