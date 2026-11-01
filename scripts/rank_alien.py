#!/usr/bin/env python3
"""rank_alien.py v1.4.0 - the deterministic bits of alien-space-ideation.

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
  tagcheck  compare two independent taggings of the same documents ("docs" and
            "docs_second") and report where the taggers disagree.
  feedback  apply a round's keep/kill decisions to the input file and log the
            round in a ledger. Takes a decisions file (see below).
  selftest  quick built-in checks. The full suite is evals/probe_ranker.py.

Decisions file (feedback mode)
  {"round": 2, "beta": 0.5, "judge": "fresh agent",
   "decisions": [
     {"key": "a|b|c", "verdict": "keep", "note": "worth a prototype"},
     {"key": "d|e|f", "verdict": "kill", "reason": "incoherent", "pair": ["d", "e"]},
     {"key": "g|h|i", "verdict": "kill", "reason": "obvious"},
     {"key": "j|k|l", "verdict": "kill", "reason": "off-brief"}]}
  keep > the triple becomes a corpus document (so it is no longer unmade)
  incoherent > the named pair goes on the blacklist
  obvious > the triple's atoms are added to the baseline
  off-brief > ledger note only
Every decided key must be a triple scored in "coherence". Scores belong to the
round, so the output file starts the next round with "coherence" empty.

Input JSON (references/example-input.json)
  atoms      list of atom names (no "|")
  docs       {doc_name: [atom, ...]}  or
             {doc_name: {"atoms": [atom, ...], "source": "who made it"}}
  baseline   [[atom, ...], ...]        atoms used by the ordinary ideas
  blacklist  [[atom, atom], ...]       pairs rejected as incoherent; never pooled
  coherence  {"a|b|c": 0-3}            judged scores (any atom order)
  judges     {"name": {"a|b|c": 0-3}}  two or more judges scoring the same triples,
                                       instead of "coherence". Ranking uses the lowest
                                       score (--combine mean for the mean); the
                                       diagnostics report where the judges disagree.
  docs_second same shape as docs       a second, independent tagging, for tagcheck
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
import hashlib
import itertools
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

W_PAIR, W_BASE, W_HABIT, W_COMM = 0.45, 0.1875, 0.1125, 0.25
SLOW_ATOMS = 150


def tiebreak(key):
    """Deterministic, order-neutral tie-break. Alphabetical order would quietly
    favour atoms near the start of the alphabet whenever scores tie."""
    return hashlib.sha256(("alien-space:" + key).encode("utf-8")).hexdigest()


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def is_strs(x):
    return isinstance(x, list) and all(isinstance(a, str) for a in x)


def parse_docs(raw_docs, field):
    if not isinstance(raw_docs, dict):
        die(f'"{field}" must map document names to atom lists or {{"atoms", "source"}} objects')
    docs = {}
    for name, v in raw_docs.items():
        if is_strs(v):
            docs[name] = {"atoms": v, "source": None}
        elif isinstance(v, dict) and is_strs(v.get("atoms")) \
                and (v.get("source") is None or (isinstance(v["source"], str) and v["source"])):
            docs[name] = {"atoms": v["atoms"], "source": v.get("source")}
        else:
            die(f'{field}: doc {name!r} must be a list of atoms or {{"atoms": [...], "source": "..."}}')
    return docs


def norm_scores(raw, vocab, label):
    """Validate {"a|b|c": 0-3} and return it with keys sorted."""
    if not isinstance(raw, dict):
        die(f'{label} must be an object of "a|b|c": score')
    out = {}
    for k, v in raw.items():
        parts = k.split("|")
        if len(parts) != 3 or len(set(parts)) != 3:
            die(f'{label} key {k!r} must name exactly three distinct atoms')
        if not set(parts) <= vocab:
            die(f'{label} key {k!r} uses atoms not in "atoms": '
                f'{sorted(set(parts) - vocab)}')
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3:
            die(f'{label} score for {k!r} must be an integer 0 to 3, got {v!r}')
        nk = "|".join(sorted(parts))
        if nk in out:
            die(f"{label} lists {nk!r} twice (atom order doesn't matter)")
        out[nk] = v
    return out


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
    docs = parse_docs(data.get("docs", {}), "docs")
    docs_second = parse_docs(data["docs_second"], "docs_second") if "docs_second" in data else None
    base = data.get("baseline", [])
    if not isinstance(base, list) or not all(is_strs(b) for b in base):
        die('"baseline" must be a list of lists of atom names')
    bl = set()
    for p in data.get("blacklist", []):
        if not is_strs(p) or len(set(p)) != 2 or not set(p) <= vocab:
            die(f'"blacklist" entries must be two distinct known atoms, got {p!r}')
        bl.add(frozenset(p))
    raw = data.get("coherence", {})
    raw_judges = data.get("judges", {})
    judges = {}
    if raw_judges:
        if raw:
            die('use "coherence" or "judges", not both')
        if not isinstance(raw_judges, dict) or len(raw_judges) < 2:
            die('"judges" needs at least two judges; use "coherence" for one')
        for jn, jr in raw_judges.items():
            judges[jn] = norm_scores(jr, vocab, f"judge {jn!r}")
        names = list(judges)
        first = set(judges[names[0]])
        for jn in names[1:]:
            if set(judges[jn]) != first:
                diff = sorted(set(judges[jn]) ^ first)
                die(f"every judge must score the same triples; {names[0]!r} and {jn!r} "
                    f"differ on {len(diff)} (first: {diff[0]!r})")
        coh = {k: min(j[k] for j in judges.values()) for k in first}  # cautious default
    else:
        coh = norm_scores(raw, vocab, "coherence")
    unanchored = data.get("unanchored", False)
    if not isinstance(unanchored, bool):
        die('"unanchored" must be true or false')
    groups = data.get("groups", {})
    if not isinstance(groups, dict) or not all(is_strs(v) and set(v) <= vocab
                                               for v in groups.values()):
        die('"groups" must map theme names to lists of known atoms')
    return {"vocab": vocab, "docs": docs, "docs_second": docs_second,
            "baseline": [set(b) for b in base],
            "blacklist": bl, "coherence": coh, "judges": judges, "unanchored": unanchored,
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
    cands.sort(key=lambda r: (r["availability"], tiebreak(r["key"]), r["key"]))
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
        out.sort(key=lambda r: (r["availability"], tiebreak(r["key"]), r["key"]))
        return out
    out.sort(key=lambda r: r["key"])  # alphabetical: order must not leak availability
    return [{"triple": r["triple"], "key": r["key"]} for r in out]


def rank(cfg, beta, gate, w, combine="min"):
    st = stats(cfg)
    w = weights(w, st)
    rows = []
    for k, c in cfg["coherence"].items():
        t = tuple(k.split("|"))
        if st["trip"][t] > 0 or blacklisted(t, cfg["blacklist"]):
            continue  # strict novelty only; rejected pairs stay rejected
        scores = None
        if cfg["judges"]:
            scores = {n: j[k] for n, j in cfg["judges"].items()}
            c = min(scores.values()) if combine == "min" else sum(scores.values()) / len(scores)
        if cfg["unanchored"]:
            c = min(c, 2)  # no corpus to anchor the judgement: 3 is not available
        rows.append({"key": k, "coherence": c, "judge_scores": scores,
                     "availability": availability(t, st, cfg["baseline"], w),
                     "pairs_seen": sum(1 for x in itertools.combinations(sorted(t), 2)
                                       if st["pair"][x] > 0)})

    def order(fn, subset):
        s = sorted(subset, key=lambda r: (-fn(r), tiebreak(r["key"]), r["key"]))
        return {r["key"]: i + 1 for i, r in enumerate(s)}

    r0 = order(lambda r: r["coherence"] / 3, rows)  # beta 0: coherence only
    passed = [r for r in rows if r["coherence"] >= gate]  # coherence is a gate
    rb = order(lambda r: (1 - beta) * r["coherence"] / 3 + beta * (1 - r["availability"]),
               passed)
    ranked = [{**{x: v for x, v in r.items()
                  if x != "pairs_seen" and not (x == "judge_scores" and v is None)},
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
         "precedent_note": None, "judge_note": None}
    full = [r["coherence"] for r in rows if r["pairs_seen"] == 3]
    part = [r["coherence"] for r in rows if r["pairs_seen"] < 3]
    if cfg["judges"]:
        spreads = {r["key"]: max(r["judge_scores"].values()) - min(r["judge_scores"].values())
                   for r in rows}
        n = len(spreads) or 1
        d["judges"] = len(cfg["judges"])
        d["judge_exact_agreement"] = round(sum(1 for v in spreads.values() if v == 0) / n, 3)
        d["judge_within_one"] = round(sum(1 for v in spreads.values() if v <= 1) / n, 3)
        d["judge_mean_spread"] = round(sum(spreads.values()) / n, 3)
        d["judge_disputed"] = sorted(k for k, v in spreads.items() if v >= 2)
        if d["judge_disputed"]:
            d["judge_note"] = (f"{len(d['judge_disputed'])} triple(s) have judges two or more "
                               "points apart: treat their rank as unresolved")
        elif d["judge_exact_agreement"] < 0.5:
            d["judge_note"] = ("judges agree exactly on fewer than half the triples: "
                               "the rubric is probably too loose")
        else:
            d["judge_note"] = "judges broadly agree"
    if len(full) >= 2 and len(part) >= 2:
        gap = sum(full) / len(full) - sum(part) / len(part)
        d["precedent_note"] = (
            f"scores track precedent: triples with all three pairs seen average "
            f"{gap:.2f} higher, so the judging may be rewarding familiarity") \
            if gap >= 0.5 else "scores don't track precedent"
    if len(rows) < 4:
        d["note"] = "fewer than 4 judged triples: no comparison possible"
        return d
    s = sorted(rows, key=lambda r: (r["availability"], tiebreak(r["key"]), r["key"]))
    h = len(s) // 2
    lo, hi = s[:h], s[-h:]
    d["mean_coherence_low_availability_half"] = round(sum(r["coherence"] for r in lo) / len(lo), 3)
    d["mean_coherence_high_availability_half"] = round(sum(r["coherence"] for r in hi) / len(hi), 3)
    gap = d["mean_coherence_high_availability_half"] - d["mean_coherence_low_availability_half"]
    d["note"] = ("novelty is costing coherence: the unusual half scores lower, so check the "
                 "rubric and the atoms before trusting the top ranks") if gap >= 0.5 else \
                "no large coherence penalty for the unusual half"
    return d


REASONS = ("incoherent", "obvious", "off-brief")


def read_decisions(path, cfg):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        die(f"{path} is not valid JSON: {e}")
    if not isinstance(d, dict):
        die("decisions file must be a JSON object")
    rnd = d.get("round")
    if isinstance(rnd, bool) or not isinstance(rnd, int) or rnd < 1:
        die('"round" must be a whole number, 1 or more')
    for field in ("judge",):
        if field in d and not isinstance(d[field], str):
            die(f'"{field}" must be a string')
    if "beta" in d and (isinstance(d["beta"], bool) or not isinstance(d["beta"], (int, float))
                        or not 0 <= d["beta"] <= 1):
        die('"beta" must be a number between 0 and 1')
    items = d.get("decisions")
    if not isinstance(items, list) or not items:
        die('"decisions" must be a non-empty list')
    seen, out = set(), []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            die(f"decision {i} must be an object")
        parts = str(it.get("key", "")).split("|")
        if len(parts) != 3 or len(set(parts)) != 3 or not set(parts) <= cfg["vocab"]:
            die(f"decision {i}: key must name three distinct known atoms")
        key = "|".join(sorted(parts))
        if key not in cfg["coherence"]:
            die(f"decision {i}: {key!r} was not scored in \"coherence\", so it can't be decided")
        if key in seen:
            die(f"decision {i}: {key!r} is decided twice")
        seen.add(key)
        verdict = it.get("verdict")
        if verdict not in ("keep", "kill"):
            die(f'decision {i}: verdict must be "keep" or "kill"')
        note = it.get("note", "")
        if not isinstance(note, str):
            die(f"decision {i}: note must be a string")
        rec = {"key": key, "atoms": sorted(parts), "verdict": verdict, "note": note,
               "reason": None, "pair": None}
        if verdict == "kill":
            if it.get("reason") not in REASONS:
                die(f"decision {i}: a kill needs a reason, one of {', '.join(REASONS)}")
            rec["reason"] = it["reason"]
            if it["reason"] == "incoherent":
                pair = it.get("pair")
                if not is_strs(pair) or len(set(pair)) != 2 or not set(pair) <= set(parts):
                    die(f"decision {i}: an incoherent kill needs \"pair\": two atoms from the triple")
                rec["pair"] = sorted(pair)
        out.append(rec)
    return rnd, d.get("beta"), d.get("judge"), out


def ledger_rounds(text):
    """Return [(round_number, set_of_reasons)] in file order."""
    rounds, cur = [], None
    for line in text.splitlines():
        m = re.match(r"## Round (\d+)\s*$", line)
        if m:
            cur = [int(m.group(1)), set()]
            rounds.append(cur)
        elif cur is not None and line.startswith("Reasons: "):
            cur[1] = {r.split("=")[0].strip() for r in line[9:].split(",") if "=" in r}
    return [(n, r) for n, r in rounds]


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def feedback(in_path, dec_path, out_path, in_place, ledger):
    cfg = load(in_path)  # validates the input file as well
    rnd, beta, judge, decs = read_decisions(dec_path, cfg)
    if in_place and out_path:
        die("use --out or --in-place, not both")
    if not in_place and not out_path:
        die("give --out PATH, or --in-place to overwrite the input")
    target = in_path if in_place else out_path
    if not in_place and os.path.abspath(out_path) == os.path.abspath(in_path):
        die("--out is the input file; use --in-place if you mean it")
    ledger_text = ""
    if ledger and os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as f:
            ledger_text = f.read()
        if any(n == rnd for n, _ in ledger_rounds(ledger_text)):
            die(f"{ledger} already has a Round {rnd}; each round is logged once")

    with open(in_path, encoding="utf-8") as f:
        raw = json.load(f)
    docs = raw.setdefault("docs", {})
    blacklist = raw.setdefault("blacklist", [])
    baseline = raw.setdefault("baseline", [])
    kept = killed = 0
    reasons = Counter()
    for d in decs:
        if d["verdict"] == "keep":
            kept += 1
            name, n = f"kept_r{rnd}_{kept}", kept
            while name in docs:
                n += 1
                name = f"kept_r{rnd}_{n}"
            docs[name] = list(d["atoms"])
            if isinstance(raw.get("docs_second"), dict):
                raw["docs_second"][name] = list(d["atoms"])  # kept ideas are tagged by definition
        else:
            killed += 1
            reasons[d["reason"]] += 1
            if d["reason"] == "incoherent" and d["pair"] not in [sorted(b) for b in blacklist]:
                blacklist.append(d["pair"])
            elif d["reason"] == "obvious":
                baseline.append(list(d["atoms"]))
    dropped = len(cfg["coherence"]) - len(decs)
    raw["coherence"] = {}
    if "judges" in raw:
        raw["judges"] = {}
    write_json_atomic(target, raw)

    if ledger:
        lines = [] if ledger_text else ["# Ledger", ""]
        lines += [f"## Round {rnd}"]
        meta = []
        if beta is not None:
            meta.append(f"Beta: {beta}")
        if judge:
            meta.append(f"Judge: {judge}")
        if meta:
            lines.append(". ".join(meta) + ".")
        lines.append(f"Kept: {kept}. Killed: {killed}.")
        if reasons:
            lines.append("Reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
        for d in decs:
            tail = f" {d['note']}" if d["note"] else ""
            if d["verdict"] == "keep":
                lines.append(f"- keep `{d['key']}`.{tail}")
            else:
                extra = f" ({'+'.join(d['pair'])})" if d["pair"] else ""
                lines.append(f"- kill `{d['key']}`: {d['reason']}{extra}.{tail}")
        lines.append("")
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(("\n" if ledger_text and not ledger_text.endswith("\n\n") else "")
                    + "\n".join(lines) + "\n")
        with open(ledger, encoding="utf-8") as f:
            recent = ledger_rounds(f.read())[-3:]
        if len(recent) == 3:
            common = set.intersection(*(r for _, r in recent))
            for r in sorted(common):
                warn(f"kill reason '{r}' has turned up in three rounds running; "
                     "the rubric or the atoms are wrong, not the decisions")
    if dropped:
        warn(f"{dropped} scored triple(s) had no decision and were dropped with the scores")
    return {"round": rnd, "kept": kept, "killed": killed, "reasons": dict(reasons),
            "undecided_dropped": dropped, "wrote": target,
            "ledger": ledger or None}


def tagcheck(cfg, min_j):
    """Compare two independent taggings of the same documents."""
    a, b = cfg["docs"], cfg["docs_second"]
    if b is None:
        die('tagcheck needs "docs_second": a second, independent tagging of the same documents')
    if set(a) != set(b):
        only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        die(f'"docs" and "docs_second" must name the same documents '
            f"(only in docs: {only_a[:3]}, only in docs_second: {only_b[:3]})")
    bad = sorted({x for d in b.values() for x in d["atoms"]} - cfg["vocab"])
    if bad:
        die(f'"docs_second" uses atoms not in "atoms": {bad[:5]}')
    per_doc, atoms = [], defaultdict(lambda: [0, 0, 0])  # both, first only, second only
    for name in sorted(a):
        sa = set(a[name]["atoms"]) & cfg["vocab"]
        sb = set(b[name]["atoms"]) & cfg["vocab"]
        union = sa | sb
        j = len(sa & sb) / len(union) if union else 1.0
        per_doc.append({"doc": name, "jaccard": round(j, 3),
                        "only_first": sorted(sa - sb), "only_second": sorted(sb - sa)})
        for x in sa & sb:
            atoms[x][0] += 1
        for x in sa - sb:
            atoms[x][1] += 1
        for x in sb - sa:
            atoms[x][2] += 1
    mean_j = sum(r["jaccard"] for r in per_doc) / len(per_doc) if per_doc else 1.0
    by_atom = sorted(({"atom": x, "both": v[0], "first_only": v[1], "second_only": v[2],
                       "jaccard": round(v[0] / sum(v), 3)} for x, v in atoms.items()),
                     key=lambda r: (r["jaccard"], r["atom"]))
    return {"documents": len(per_doc), "mean_jaccard": round(mean_j, 3),
            "low_agreement_docs": sorted((r for r in per_doc if r["jaccard"] < min_j),
                                         key=lambda r: (r["jaccard"], r["doc"])),
            "atoms_worst_first": by_atom,
            "verdict": ("taggers broadly agree" if mean_j >= min_j else
                        "taggers disagree a lot: reconcile the atom definitions before pooling")}


def selftest():
    def doc(atoms, source=None):
        return {"atoms": list(atoms), "source": source}
    cfg = {"vocab": set("abcde"),
           "docs": {"d1": doc("abc"), "d2": doc("abd"), "d3": doc("cde"), "d4": doc("ae")},
           "baseline": [set("abx")], "blacklist": {frozenset("ac")}, "coherence": {},
           "unanchored": False, "judges": {}}
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
    ap.add_argument("mode", choices=["pool", "rank", "feedback", "tagcheck", "selftest"])
    ap.add_argument("input", nargs="?", help="input JSON path")
    ap.add_argument("decisions", nargs="?", help="feedback: decisions JSON path")
    ap.add_argument("--out", help="feedback: write the updated input here")
    ap.add_argument("--in-place", action="store_true",
                    help="feedback: overwrite the input file")
    ap.add_argument("--ledger", help="feedback: append the round to this markdown ledger")
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
    ap.add_argument("--combine", choices=["min", "mean"], default=None,
                    help="rank, with several judges: use the lowest score (default) or the mean")
    ap.add_argument("--min-jaccard", type=float, default=0.6,
                    help="tagcheck: documents below this overlap are flagged (default 0.6)")
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
    if not 0 <= a.min_jaccard <= 1 or math.isnan(a.min_jaccard):
        ap.error("--min-jaccard must be between 0 and 1")
    w = (a.w_pair, a.w_base, a.w_habit, a.w_comm)
    if any(x < 0 or math.isnan(x) for x in w):
        ap.error("availability weights must not be negative")
    if a.mode == "feedback":
        if not a.decisions:
            ap.error("feedback needs a decisions JSON path after the input path")
        json.dump(feedback(a.input, a.decisions, a.out, a.in_place, a.ledger),
                  sys.stdout, indent=2)
        print()
        return
    cfg = load(a.input)
    if a.combine and not cfg["judges"]:
        ap.error('--combine only applies when the input has "judges"')
    if a.mode == "tagcheck":
        json.dump(tagcheck(cfg, a.min_jaccard), sys.stdout, indent=2)
        print()
        return
    nv = len(cfg["vocab"])
    if nv > SLOW_ATOMS:
        warn(f"{nv} atoms means {math.comb(nv, 3):,} triples to check; this will be slow. "
             "Merge synonyms or split the corpus.")
    elif not 25 <= nv <= 60:
        warn(f"{nv} atoms; SKILL.md recommends 25 to 60")
    res = pool(cfg, a.n, a.min_pairs_seen, w, a.controls, a.reveal) if a.mode == "pool" \
        else rank(cfg, a.beta, a.gate, w, a.combine or "min")
    json.dump(res, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
