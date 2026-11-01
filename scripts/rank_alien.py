#!/usr/bin/env python3
"""rank_alien.py v1.2.0 - the deterministic bits of alien-space-ideation.

Author: TABARC-Code

Claude does the judging (atoms, coherence scores, write-ups). This script does
the counting, because counting is easy to get quietly wrong by eye, and it
enforces the rules that prose alone can only ask for.

Modes
  pool      unseen atom triples whose pairs have corpus precedent. BLIND by
            default: no availability numbers, alphabetical order, so the
            coherence judge can't tell which ones are the unusual ones.
            --reveal shows availability, controls, and source coverage.
  rank      take coherence scores and rank at beta=0 and at --beta, plus
            diagnostics on whether novelty is costing coherence.
  selftest  quick built-in checks. The full suite is evals/probe_ranker.py.

Input JSON (references/example-input.json)
  atoms      list of atom names (no "|")
  docs       {doc_name: [atom, ...]}  or
             {doc_name: {"atoms": [atom, ...], "source": "who made it"}}
  baseline   [[atom, ...], ...]        atoms used by the ordinary ideas
  blacklist  [[atom, atom], ...]       pairs rejected as incoherent; never pooled
  coherence  {"a|b|c": 0-3}            judged scores (any atom order)
  unanchored true/false                no real corpus: scores capped at 2
  groups     {theme: [atom, ...]}      optional; flags a theme hogging the top five

Availability (0 to 1, higher = more likely someone would think of it) blends:
  pair       how often the triple's pairs appear together (log scaled)
  baseline   whether the ordinary ideas already use two of its atoms
  habit      how heavily the corpus leans on its atoms (log scaled)
  community  share of sources whose combined work already uses all three
             atoms. Only active when docs carry a "source". Without sources,
             its weight is shared out among the other three.

Bad input exits 2 with a one-line message. It never prints a traceback and it
never quietly accepts something it can't interpret.

The weights are the author's defaults, not the paper's. Tunable.
"""
import argparse
import itertools
import json
import math
import sys
from collections import Counter, defaultdict

W_PAIR, W_BASE, W_HABIT, W_COMM = 0.45, 0.1875, 0.1125, 0.25
SLOW_ATOMS = 150


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def is_strs(x):
    return isinstance(x, list) and all(isinstance(a, str) for a in x)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        die(f"{path} is not valid JSON: {e}")
    if not isinstance(data, dict):
        die("top level of the input must be a JSON object")
    atoms = data.get("atoms")
    if not isinstance(atoms, list) or not all(isinstance(a, str) and a and "|" not in a
                                              for a in atoms):
        die('"atoms" must be a list of non-empty strings without "|"')
    vocab = set(atoms)
    raw_docs = data.get("docs", {})
    if not isinstance(raw_docs, dict):
        die('"docs" must map document names to atom lists or {"atoms", "source"} objects')
    docs = {}
    for name, v in raw_docs.items():
        if is_strs(v):
            docs[name] = {"atoms": v, "source": None}
        elif isinstance(v, dict) and is_strs(v.get("atoms")) \
                and (v.get("source") is None or (isinstance(v["source"], str) and v["source"])):
            docs[name] = {"atoms": v["atoms"], "source": v.get("source")}
        else:
            die(f'doc {name!r} must be a list of atoms or {{"atoms": [...], "source": "..."}}')
    base = data.get("baseline", [])
    if not isinstance(base, list) or not all(is_strs(b) for b in base):
        die('"baseline" must be a list of lists of atom names')
    bl = set()
    for p in data.get("blacklist", []):
        if not is_strs(p) or len(set(p)) != 2 or not set(p) <= vocab:
            die(f'"blacklist" entries must be two distinct known atoms, got {p!r}')
        bl.add(frozenset(p))
    raw = data.get("coherence", {})
    if not isinstance(raw, dict):
        die('"coherence" must be an object of "a|b|c": score')
    coh = {}
    for k, v in raw.items():
        parts = k.split("|")
        if len(parts) != 3 or len(set(parts)) != 3:
            die(f'coherence key {k!r} must name exactly three distinct atoms')
        if not set(parts) <= vocab:
            die(f'coherence key {k!r} uses atoms not in "atoms": '
                f'{sorted(set(parts) - vocab)}')
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3:
            die(f'coherence score for {k!r} must be an integer 0 to 3, got {v!r}')
        nk = "|".join(sorted(parts))
        if nk in coh:
            die(f"coherence lists {nk!r} twice (atom order doesn't matter)")
        coh[nk] = v
    unanchored = data.get("unanchored", False)
    if not isinstance(unanchored, bool):
        die('"unanchored" must be true or false')
    groups = data.get("groups", {})
    if not isinstance(groups, dict) or not all(is_strs(v) and set(v) <= vocab
                                               for v in groups.values()):
        die('"groups" must map theme names to lists of known atoms')
    return {"vocab": vocab, "docs": docs, "baseline": [set(b) for b in base],
            "blacklist": bl, "coherence": coh, "unanchored": unanchored,
            "groups": {g: set(v) for g, v in groups.items()}}


def stats(cfg):
    pair, trip, use = Counter(), Counter(), Counter()
    profiles = defaultdict(set)
    for name, d in cfg["docs"].items():
        s = sorted(set(d["atoms"]) & cfg["vocab"])
        unknown = set(d["atoms"]) - cfg["vocab"]
        if unknown:
            warn(f"{name} uses atoms not in vocabulary: {sorted(unknown)}")
        if d["source"]:
            profiles[d["source"]].update(s)
        for a in s:
            use[a] += 1
        for p in itertools.combinations(s, 2):
            pair[p] += 1
        for t in itertools.combinations(s, 3):
            trip[t] += 1
    return {"pair": pair, "trip": trip, "use": use, "profiles": dict(profiles),
            "lmaxp": math.log1p(max(pair.values(), default=1)),
            "lmaxu": math.log1p(max(use.values(), default=1))}


def weights(w, st):
    """Drop the community weight when no doc has a source, keeping the total."""
    if st["profiles"]:
        return w
    rest = w[0] + w[1] + w[2]
    if rest == 0:
        return (0.0, 0.0, 0.0, 0.0)
    scale = (rest + w[3]) / rest
    return (w[0] * scale, w[1] * scale, w[2] * scale, 0.0)


def covered_by(t, st):
    return sorted(s for s, prof in st["profiles"].items() if set(t) <= prof)


def availability(t, st, base, w):
    t = tuple(sorted(t))
    pairs = list(itertools.combinations(t, 2))
    p = sum(math.log1p(st["pair"][x]) for x in pairs) / (len(pairs) * st["lmaxp"])
    h = sum(math.log1p(st["use"][a]) for a in t) / (len(t) * st["lmaxu"])
    b = 1.0 if any(len(set(t) & s) >= 2 for s in base) else 0.0
    c = len(covered_by(t, st)) / len(st["profiles"]) if st["profiles"] else 0.0
    return min(1.0, w[0] * p + w[1] * b + w[2] * h + w[3] * c)


def blacklisted(t, bl):
    return any(frozenset(p) in bl for p in itertools.combinations(t, 2))


def pool(cfg, n, min_pairs, w, controls, reveal):
    st = stats(cfg)
    w = weights(w, st)
    cands = []
    for t in itertools.combinations(sorted(cfg["vocab"]), 3):
        if st["trip"][t] > 0 or blacklisted(t, cfg["blacklist"]):
            continue  # already made, or rejected as incoherent
        seen = sum(1 for x in itertools.combinations(t, 2) if st["pair"][x] > 0)
        if seen < min_pairs:
            continue  # no precedent for the pairs, likely noise
        cands.append({"triple": list(t), "key": "|".join(t), "pairs_seen": seen,
                      "availability": round(availability(t, st, cfg["baseline"], w), 4),
                      "covered_by": covered_by(t, st)})
    cands.sort(key=lambda r: (r["availability"], r["key"]))
    want_ctrl = int(round(n * controls))
    alien, rest = cands[:n - want_ctrl], cands[n - want_ctrl:]
    k = min(want_ctrl, len(rest))  # controls: evenly spaced through the rest
    ctrl = [rest[int((i + 0.5) * len(rest) / k)] for i in range(k)] if k else []
    for r in alien:
        r["control"] = False
    for r in ctrl:
        r["control"] = True
    out = alien + ctrl
    if reveal:
        out.sort(key=lambda r: (r["availability"], r["key"]))
        return out
    out.sort(key=lambda r: r["key"])  # alphabetical: order must not leak availability
    return [{"triple": r["triple"], "key": r["key"]} for r in out]


def rank(cfg, beta, gate, w):
    st = stats(cfg)
    w = weights(w, st)
    rows = []
    for k, c in cfg["coherence"].items():
        t = tuple(k.split("|"))
        if st["trip"][t] > 0 or blacklisted(t, cfg["blacklist"]):
            continue  # strict novelty only; rejected pairs stay rejected
        if cfg["unanchored"]:
            c = min(c, 2)  # no corpus to anchor the judgement: 3 is not available
        rows.append({"key": k, "coherence": c,
                     "availability": availability(t, st, cfg["baseline"], w),
                     "pairs_seen": sum(1 for x in itertools.combinations(sorted(t), 2)
                                       if st["pair"][x] > 0)})

    def order(fn, subset):
        s = sorted(subset, key=lambda r: (-fn(r), r["key"]))
        return {r["key"]: i + 1 for i, r in enumerate(s)}

    r0 = order(lambda r: r["coherence"] / 3, rows)  # beta 0: coherence only
    passed = [r for r in rows if r["coherence"] >= gate]  # coherence is a gate
    rb = order(lambda r: (1 - beta) * r["coherence"] / 3 + beta * (1 - r["availability"]),
               passed)
    ranked = [{**{x: v for x, v in r.items() if x != "pairs_seen"},
               "availability": round(r["availability"], 4),
               "rank_beta0": r0[r["key"]], "rank_beta": rb[r["key"]],
               "shift": r0[r["key"]] - rb[r["key"]]} for r in passed]
    ranked.sort(key=lambda r: r["rank_beta"])
    return {"ranked": ranked, "diagnostics": diagnostics(cfg, st, rows, passed, ranked)}


def diagnostics(cfg, st, rows, passed, ranked):
    top = [r["key"].split("|") for r in ranked[:5]]
    counts = Counter(a for t in top for a in t)
    d = {"judged": len(rows), "passed_gate": len(passed),
         "unanchored": cfg["unanchored"],
         "sources": len(st["profiles"]),
         "collapse_atoms": sorted(a for a, c in counts.items() if c > 3),
         "collapse_groups": sorted(g for g, members in cfg.get("groups", {}).items()
                                   if sum(1 for t in top if set(t) & members) > 3),
         "distinct_atoms_top5": len(counts),
         "distinct_atoms_baseline": len(set().union(*cfg["baseline"])) if cfg["baseline"] else 0,
         "mean_coherence_low_availability_half": None,
         "mean_coherence_high_availability_half": None, "note": None,
         "precedent_note": None}
    full = [r["coherence"] for r in rows if r["pairs_seen"] == 3]
    part = [r["coherence"] for r in rows if r["pairs_seen"] < 3]
    if len(full) >= 2 and len(part) >= 2:
        gap = sum(full) / len(full) - sum(part) / len(part)
        d["precedent_note"] = (
            f"scores track precedent: triples with all three pairs seen average "
            f"{gap:.2f} higher, so the judging may be rewarding familiarity") \
            if gap >= 0.5 else "scores don't track precedent"
    if len(rows) < 4:
        d["note"] = "fewer than 4 judged triples: no comparison possible"
        return d
    s = sorted(rows, key=lambda r: (r["availability"], r["key"]))
    h = len(s) // 2
    lo, hi = s[:h], s[-h:]
    d["mean_coherence_low_availability_half"] = round(sum(r["coherence"] for r in lo) / len(lo), 3)
    d["mean_coherence_high_availability_half"] = round(sum(r["coherence"] for r in hi) / len(hi), 3)
    gap = d["mean_coherence_high_availability_half"] - d["mean_coherence_low_availability_half"]
    d["note"] = ("novelty is costing coherence: the unusual half scores lower, so check the "
                 "rubric and the atoms before trusting the top ranks") if gap >= 0.5 else \
                "no large coherence penalty for the unusual half"
    return d


def selftest():
    def doc(atoms, source=None):
        return {"atoms": list(atoms), "source": source}
    cfg = {"vocab": set("abcde"),
           "docs": {"d1": doc("abc"), "d2": doc("abd"), "d3": doc("cde"), "d4": doc("ae")},
           "baseline": [set("abx")], "blacklist": {frozenset("ac")}, "coherence": {},
           "unanchored": False}
    w = (W_PAIR, W_BASE, W_HABIT, W_COMM)
    p = pool(cfg, 50, 2, w, 0.0, True)
    keys = [r["key"] for r in p]
    blind = pool(cfg, 50, 2, w, 0.0, False)
    ok = "a|b|c" not in keys and "c|d|e" not in keys
    ok &= all(not {"a", "c"} <= set(r["triple"]) for r in p)  # blacklist honoured
    ok &= all("availability" not in r for r in blind)
    ok &= [r["key"] for r in blind] == sorted(r["key"] for r in blind)
    ok &= abs(sum(weights(w, stats(cfg))) - sum(w)) < 1e-9  # weight total kept
    cfg["coherence"] = {"a|d|e": 3, "b|d|e": 2, "a|b|e": 1}
    res = rank(cfg, 0.5, 2, w)
    ok &= {r["key"] for r in res["ranked"]} == {"a|d|e", "b|d|e"}
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["pool", "rank", "selftest"])
    ap.add_argument("input", nargs="?", help="input JSON path")
    ap.add_argument("--n", type=int, default=40, help="pool size, 1 or more (default 40)")
    ap.add_argument("--controls", type=float, default=0.3,
                    help="fraction of the pool drawn evenly from higher-availability "
                         "triples as a comparison group (default 0.3)")
    ap.add_argument("--reveal", action="store_true",
                    help="pool: show availability, controls, and coverage (not for the judge)")
    ap.add_argument("--min-pairs-seen", type=int, default=2,
                    help="pairs of each triple needing corpus precedent, 0 to 3 (default 2)")
    ap.add_argument("--beta", type=float, default=0.5,
                    help="weight on unavailability, 0 to 1 (default 0.5)")
    ap.add_argument("--gate", type=int, default=2,
                    help="minimum coherence to be ranked, 0 to 3 (default 2)")
    ap.add_argument("--w-pair", type=float, default=W_PAIR)
    ap.add_argument("--w-base", type=float, default=W_BASE)
    ap.add_argument("--w-habit", type=float, default=W_HABIT)
    ap.add_argument("--w-comm", type=float, default=W_COMM)
    a = ap.parse_args()
    if a.mode == "selftest":
        sys.exit(selftest())
    if not a.input:
        ap.error("input JSON required")
    if a.n < 1:
        ap.error("--n must be 1 or more")
    if not 0 <= a.controls <= 1 or math.isnan(a.controls):
        ap.error("--controls must be between 0 and 1")
    if not 0 <= a.min_pairs_seen <= 3:
        ap.error("--min-pairs-seen must be 0 to 3")
    if not 0 <= a.beta <= 1 or math.isnan(a.beta):
        ap.error("--beta must be between 0 and 1")
    if not 0 <= a.gate <= 3:
        ap.error("--gate must be 0 to 3")
    w = (a.w_pair, a.w_base, a.w_habit, a.w_comm)
    if any(x < 0 or math.isnan(x) for x in w):
        ap.error("availability weights must not be negative")
    cfg = load(a.input)
    nv = len(cfg["vocab"])
    if nv > SLOW_ATOMS:
        warn(f"{nv} atoms means {math.comb(nv, 3):,} triples to check; this will be slow. "
             "Merge synonyms or split the corpus.")
    elif not 25 <= nv <= 60:
        warn(f"{nv} atoms; SKILL.md recommends 25 to 60")
    res = pool(cfg, a.n, a.min_pairs_seen, w, a.controls, a.reveal) if a.mode == "pool" \
        else rank(cfg, a.beta, a.gate, w)
    json.dump(res, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
