# Changelog

Versions before 1.2.0 were development builds and were never published. They're listed because the later fixes make no sense without them.

## 1.3.0

- Fixed a mistake of mine: equal scores were being settled alphabetically, so atoms near the start of the alphabet won every tie. Ties now go by a fixed hash. Still deterministic, no longer biased.
- New `feedback` mode. A round's keep/kill decisions go in a small JSON file, and the script updates the corpus, blacklist and baseline, clears the round's scores, and appends the round to a ledger. It also warns if the same kill reason turns up three rounds running.
- GitHub Actions workflow running the self-test and probe suite on Python 3.11, 3.12, and 3.13.
- `.gitignore`, this file.
- Probe suite grown from 41 to 64 checks. Reject checks now have to fail for the stated reason, not just fail.

## 1.2.0

- Documents can carry a `source`, which adds a community-coverage term to availability.
- Pair and atom counts are log scaled, so one heavily repeated pair no longer sets the scale for everything else.
- Warning above 150 atoms.
- `precedent_note` diagnostic: warns when scores rise with how familiar a triple is.
- Optional `groups` and `collapse_groups` to catch a theme dominating the top five.
- Judging rubric changed so that precedent is a gate, not part of the score.
- MIT licence added.

## 1.1.0

- Blind pool by default: no availability numbers, alphabetical output.
- Controls drawn from ordinary triples, and a coherence comparison between the unusual and ordinary halves.
- Blacklist, `unanchored` cap, collapse and diversity diagnostics.
- Bad input exits with a one-line error instead of a traceback or a quietly wrong ranking.
- First probe suite.

## 1.0.0

- First script: `pool`, `rank`, `selftest`. Accepted almost any input without complaint, which is why 1.1.0 exists.
