#!/usr/bin/env python3
"""probe_ranker.py - hostile checks for scripts/rank_alien.py.

Author: TABARC-Code

Run:  python3 -I evals/probe_ranker.py [path/to/rank_alien.py]
Exit 0 only if every check passes. Each check is a promise SKILL.md makes or
an input a real user will eventually feed the script.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "scripts", "rank_alien.py")
with open(os.path.join(ROOT, "references", "example-input.json"), encoding="utf-8") as f:
    BASE = json.load(f)

RESULTS = []


def run(mode, data=None, args=(), raw=None):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as t:
        t.write(raw if raw is not None else json.dumps(data))
        path = t.name
    try:
        p = subprocess.run([sys.executable, "-I", SCRIPT, mode, path, *args],
                           capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    return p.returncode, p.stdout, p.stderr


def parse(out):
    j = json.loads(out)
    return j["ranked"] if isinstance(j, dict) and "ranked" in j else j


def clean_reject(rc, err):
    return rc == 2 and "Traceback" not in err and err.strip() != ""


def check(name, ok):
    RESULTS.append((name, bool(ok)))


def with_coh(coh, **extra):
    d = copy.deepcopy(BASE)
    d["coherence"] = coh
    d.update(extra)
    return d


T1 = "dice-pool|legacy-campaign|narrative-prompts"
T2 = "asymmetric-factions|dice-pool|push-your-luck"
T3 = "area-control|deck-building|dice-pool"

# --- poka-yoke: bad input must be refused cleanly -------------------------
rc, _, err = run("rank", with_coh({T1: 5}))
check("reject_coherence_out_of_range", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({T1: "high"}))
check("reject_coherence_non_integer", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({"dice-pool|legacy-campaign": 2}))
check("reject_coherence_key_not_triple", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({"dice-pool|legacy-campaign|nonsense": 2}))
check("reject_coherence_unknown_atom", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({T1: 3, "narrative-prompts|dice-pool|legacy-campaign": 2}))
check("reject_duplicate_triple_other_order", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({T1: 3}), ["--beta", "1.7"])
check("reject_beta_out_of_range", clean_reject(rc, err))
rc, _, err = run("pool", BASE, ["--n", "-1"])
check("reject_negative_n", clean_reject(rc, err))
rc, _, err = run("pool", BASE, ["--min-pairs-seen", "5"])
check("reject_min_pairs_out_of_range", clean_reject(rc, err))
rc, _, err = run("rank", with_coh({T1: 3}), ["--gate", "9"])
check("reject_gate_out_of_range", clean_reject(rc, err))
rc, _, err = run("pool", BASE, ["--w-pair", "-0.5"])
check("reject_negative_weight", clean_reject(rc, err))
rc, _, err = run("pool", {"docs": {}})
check("reject_missing_atoms_key", clean_reject(rc, err))
rc, _, err = run("pool", raw="{ not json")
check("reject_invalid_json", clean_reject(rc, err))

# --- blind judging is enforced, not requested -----------------------------
rc, out, _ = run("pool", BASE, ["--n", "12"])
pool_blind = parse(out) if rc == 0 else []
check("pool_blind_hides_availability",
      rc == 0 and pool_blind and all("availability" not in r for r in pool_blind))
check("pool_blind_order_not_availability_sorted",
      rc == 0 and [r["key"] for r in pool_blind] == sorted(r["key"] for r in pool_blind))
rc, out, _ = run("pool", BASE, ["--n", "12", "--reveal"])
pool_rev = parse(out) if rc == 0 else []
check("pool_reveal_shows_availability",
      rc == 0 and pool_rev and all("availability" in r for r in pool_rev))
check("pool_includes_controls",
      rc == 0 and any(r.get("control") is True for r in pool_rev)
      and any(r.get("control") is False for r in pool_rev))

# --- promises SKILL.md makes ----------------------------------------------
bl = copy.deepcopy(BASE)
bl["blacklist"] = [["dice-pool", "narrative-prompts"]]
rc, out, _ = run("pool", bl, ["--n", "40"])
check("pool_honours_blacklist",
      rc == 0 and all(not {"dice-pool", "narrative-prompts"} <= set(r["triple"]) for r in parse(out)))
rc, out, _ = run("rank", with_coh({T1: 3, T2: 3}, blacklist=[["dice-pool", "narrative-prompts"]]))
check("rank_honours_blacklist",
      rc == 0 and [r["key"] for r in parse(out)] == [T2])
rc, out, _ = run("rank", with_coh({T1: 3, T2: 3, T3: 2}))
j = json.loads(out) if rc == 0 else None
check("rank_has_diagnostics",
      isinstance(j, dict) and "ranked" in j and "diagnostics" in j)

rc, out, _ = run("rank", with_coh({T1: 3, T2: 3}, unanchored=True))
check("rank_unanchored_caps_coherence_at_2",
      rc == 0 and all(r["coherence"] <= 2 for r in parse(out)) and parse(out))
rc, err = run("rank", with_coh({T1: 3}, unanchored="yes"))[0::2]
check("reject_unanchored_not_bool", clean_reject(rc, err))
five = {"dice-pool|legacy-campaign|narrative-prompts": 3,
        "asymmetric-factions|dice-pool|push-your-luck": 3,
        "area-control|deck-building|dice-pool": 3,
        "dice-pool|hidden-roles|narrative-prompts": 3,
        "dice-pool|hidden-roles|push-your-luck": 3}
rc, out, _ = run("rank", with_coh(five))
j = json.loads(out) if rc == 0 else {}
dg = j.get("diagnostics", {}) if isinstance(j, dict) else {}
check("rank_flags_collapse_on_shared_atom", dg.get("collapse_atoms") == ["dice-pool"])
check("rank_reports_distinct_atoms_vs_baseline",
      isinstance(dg.get("distinct_atoms_top5"), int)
      and isinstance(dg.get("distinct_atoms_baseline"), int))
spread = {T1: 3, T2: 3, T3: 3, "dice-pool|hidden-roles|narrative-prompts": 1}
rc, out, _ = run("rank", with_coh(spread))
j = json.loads(out) if rc == 0 else {}
check("rank_no_false_collapse_flag",
      isinstance(j, dict) and j.get("diagnostics", {}).get("collapse_atoms") == [])

# --- v1.2: sources, log scaling, size warning ------------------------------
obj = copy.deepcopy(BASE)
obj["docs"] = {k: {"atoms": v} for k, v in BASE["docs"].items()}
a1 = run("pool", BASE, ["--n", "20", "--reveal"])
a2 = run("pool", obj, ["--n", "20", "--reveal"])
check("docs_object_form_matches_list_form", a1[0] == 0 and a1[1] == a2[1])
bad = copy.deepcopy(BASE)
bad["docs"]["game_01"] = {"atoms": ["drafting"], "source": 7}
rc, _, err = run("pool", bad)
check("reject_doc_source_not_string", clean_reject(rc, err))
comm = {"atoms": list("abcdef"),
        "docs": {"d1": {"atoms": ["a", "b"], "source": "X"},
                 "d2": {"atoms": ["b", "c"], "source": "X"},
                 "d3": {"atoms": ["a", "c"], "source": "X"},
                 "d4": {"atoms": ["d", "e"], "source": "Y"},
                 "d5": {"atoms": ["e", "f"], "source": "Z"},
                 "d6": {"atoms": ["d", "f"], "source": "W"}}}
rc, out, _ = run("pool", comm, ["--n", "20", "--reveal", "--controls", "0"])
av = {r["key"]: r["availability"] for r in parse(out)} if rc == 0 else {}
check("community_channel_one_source_more_available",
      av.get("a|b|c", 0) > av.get("d|e|f", 1))
nosrc = {"atoms": comm["atoms"], "docs": {k: v["atoms"] for k, v in comm["docs"].items()}}
rc, out, _ = run("pool", nosrc, ["--n", "20", "--reveal", "--controls", "0"])
av = {r["key"]: r["availability"] for r in parse(out)} if rc == 0 else {}
check("no_sources_means_no_community_effect",
      rc == 0 and av.get("a|b|c") == av.get("d|e|f") is not None)


def heavy(times):
    d = {"atoms": list("abcdefg"),
         "docs": {f"h{i}": ["a", "b"] for i in range(times)}}
    d["docs"].update({"x1": ["c", "d"], "x2": ["d", "e"], "x3": ["c", "e", "f"], "x4": ["f", "g"]})
    rc, out, _ = run("pool", d, ["--n", "50", "--reveal", "--controls", "0"])
    return {r["key"]: r["availability"] for r in parse(out)} if rc == 0 else {}


lo, hi = heavy(10), heavy(20)
k = "c|d|f"
check("log_scaling_damps_one_heavy_pair",
      k in lo and k in hi and hi[k] > 0 and lo[k] / hi[k] < 1.5)
big = {"atoms": [f"a{i:03d}" for i in range(151)], "docs": {"d": ["a000", "a001"]}}
rc, _, err = run("pool", big, ["--n", "1"])
check("warns_when_vocabulary_is_slow", rc == 0 and "slow" in err)

fam = {"atoms": list("abcdefgh"),
       "docs": {"d1": ["a", "b"], "d2": ["b", "c"], "d3": ["a", "c"],
                "d4": ["d", "e"], "d5": ["e", "f"], "d6": ["d", "f"],
                "d7": ["g", "a"], "d8": ["g", "b"], "d9": ["h", "d"], "d10": ["h", "e"]},
       "coherence": {"a|b|c": 3, "d|e|f": 3, "a|b|h": 1, "d|e|g": 1}}
rc, out, _ = run("rank", fam, ["--gate", "0"])
pn = json.loads(out)["diagnostics"].get("precedent_note") if rc == 0 else None
check("flags_scores_that_track_precedent", isinstance(pn, str) and pn.startswith("scores track"))

g = with_coh(five, groups={"dice-games": ["dice-pool"], "story": ["narrative-prompts"]})
rc, out, _ = run("rank", g)
cg = json.loads(out)["diagnostics"].get("collapse_groups") if rc == 0 else None
check("flags_theme_group_collapse", cg == ["dice-games"])
rc, _, err = run("rank", with_coh({T1: 3}, groups={"x": ["not-an-atom"]}))
check("reject_group_with_unknown_atom", clean_reject(rc, err))

# --- behaviour that must not regress --------------------------------------
rc, out, _ = run("pool", BASE, ["--n", "60"])
check("pool_excludes_seen_triples",
      rc == 0 and not any(r["key"] == "drafting|hidden-roles|push-your-luck" for r in parse(out)))
a = run("pool", BASE, ["--n", "12"])[1]
b = run("pool", BASE, ["--n", "12"])[1]
check("pool_deterministic", a == b and a.strip() != "")
rc, out, _ = run("pool", {"atoms": [], "docs": {}})
check("pool_empty_vocab_ok", rc == 0 and parse(out) == [])
rc, out, _ = run("rank", with_coh({}))
check("rank_empty_coherence_ok", rc == 0 and parse(out) == [])
rc, out, _ = run("rank", with_coh({T1: 3, "drafting|hidden-roles|push-your-luck": 3}))
check("rank_drops_seen_triples",
      rc == 0 and [r["key"] for r in parse(out)] == [T1])
rc, out, _ = run("rank", with_coh({T1: 3, T2: 1}))
check("rank_gate_drops_low",
      rc == 0 and [r["key"] for r in parse(out)] == [T1])
rc, out, _ = run("rank", with_coh({T1: 3, T2: 3, T3: 3}), ["--beta", "0"])
ranked = parse(out) if rc == 0 else []
check("rank_beta0_matches_beta0_rank",
      ranked and all(r["rank_beta"] == r["rank_beta0"] for r in ranked))
rc, out, _ = run("rank", with_coh({T1: 3, T2: 3, T3: 3}), ["--beta", "0.5"])
r5 = parse(out) if rc == 0 else []
check("rank_ranks_are_a_permutation",
      r5 and sorted(r["rank_beta"] for r in r5) == list(range(1, len(r5) + 1)))

# --- report ---------------------------------------------------------------
passed = sum(1 for _, ok in RESULTS if ok)
for name, ok in RESULTS:
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"\n{passed}/{len(RESULTS)} passed")
sys.exit(0 if passed == len(RESULTS) else 1)
