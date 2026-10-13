"""Judge a checkpoint on every set's held-out evaluation file (system1.md §17).

    python compare.py OUT.json --url http://127.0.0.1:8000 --key-file KEY SETS_DIR [SETS_DIR ...]
    python compare.py --show BASE.json TUNED.json

The first form asks a running service, serving the checkpoint under test, about every example of
every set in SETS_DIR (each `<name>.json` with its `<name>.eval.jsonl`, the drafts included: mount
them as the service's question sets). It records, per question, what decides whether a set may
serve: the gates at the set's own threshold, the lowest threshold that meets the gates on the
whole file, and whether thresholds fitted on two thirds hold on the other third, for three
splits. The second form prints two such runs side by side. Needs p4n4-lib.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from p4n4_lib import system1 as s1

SEEDS = (0, 1, 2)


def ask(url, key, name, state):
    body = json.dumps({"state": state}).encode()
    req = urllib.request.Request(f"{url}/v1/sets/{name}", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    started = time.monotonic()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["answers"], (time.monotonic() - started) * 1000
        except urllib.error.HTTPError:
            raise
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)


def lowest_passing(qset, qid, pairs, gates):
    """The lowest threshold whose gates all hold on `pairs`, with its metrics, or None."""
    values = sorted({a[qid].get(qset.threshold_on, 0.0) for _, a in pairs} | {0.0})
    for t in values:
        m = s1._metrics(qset, qid, pairs, threshold=t)
        if not s1._gate_failures(qid, m, gates):
            return {"threshold": round(t, 4), **m.as_dict()}
    return None


def best_safe(qset, qid, pairs, gates):
    """The highest coverage at which confident-wrong and accuracy hold, whatever the coverage gate."""
    best = None
    for t in sorted({a[qid].get(qset.threshold_on, 0.0) for _, a in pairs} | {0.0}):
        m = s1._metrics(qset, qid, pairs, threshold=t)
        safe = m.confident_wrong <= gates["max_confident_wrong"] and (
            m.answered_accuracy >= gates["min_answered_accuracy"] or not m.answered)
        if safe and (best is None or m.coverage > best["coverage"]):
            best = {"threshold": round(t, 4), **m.as_dict()}
    return best


def held_out(qset, qid, examples, answers, gates):
    """Per split: the threshold fitted on two thirds, and whether every gate holds on the rest."""
    out = []
    for seed in SEEDS:
        fit = s1.fit_thresholds(qset, examples, answers, seed=seed).get(qid, {}).get(qset.threshold_on, {})
        if fit.get("threshold") is None:
            out.append({"seed": seed, "threshold": None, "passed": False})
            continue
        h = fit["held_out"]
        failures = [name for name, bad in (
            ("coverage", h["coverage"] < gates["min_coverage"]),
            ("accuracy", h["coverage"] > 0 and h["answered_accuracy"] < gates["min_answered_accuracy"]),
            ("confident_wrong", h["confident_wrong"] > gates["max_confident_wrong"])) if bad]
        out.append({"seed": seed, "threshold": fit["threshold"], "passed": not failures,
                    "failures": failures, **h})
    return out


def judge(url, key, folders):
    result = {}
    for folder in folders:
        for qset in s1.list_sets(Path(folder)):
            examples = s1.load_examples(qset)
            with ThreadPoolExecutor(4) as pool:
                replies = list(pool.map(lambda ex: ask(url, key, qset.name, ex.state), examples))
            answers = [a for a, _ in replies]
            report = s1.evaluate(qset, examples, answers, [ms for _, ms in replies])
            pairs = list(zip(examples, answers))
            questions = {}
            for q in report.questions:
                entry = {"at_set_threshold": q.metrics.as_dict(), "failures": q.failures,
                         "threshold": qset.thresholds.get(q.question, 0.0)}
                if q.by_lang:
                    entry["by_lang"] = {lang: m.as_dict() for lang, m in q.by_lang.items()}
                if q.auc is not None:
                    entry["auc"] = q.auc
                    entry["auc_by_lang"] = q.auc_by_lang
                else:
                    entry["lowest_passing"] = lowest_passing(qset, q.question, pairs, q.gates)
                    entry["best_safe"] = best_safe(qset, q.question, pairs, q.gates)
                    entry["held_out"] = held_out(qset, q.question, examples, answers, q.gates)
                questions[q.question] = entry
            result[qset.name] = {"version": qset.version, "examples": len(examples), "passed": report.passed,
                                 "latency_ms": report.latency_ms, "questions": questions}
            print("%-16s %s" % (qset.name, "passes" if report.passed else "; ".join(report.failures)), flush=True)
    return result


def line(entry):
    if "auc" in entry:
        return "AUC %.2f" % entry["auc"]
    best, lp = entry.get("best_safe"), entry.get("lowest_passing")
    held = sum(h["passed"] for h in entry.get("held_out", []))
    return "safe coverage %s; gates %s; held out %d/%d" % (
        "%.2f at %.2f" % (best["coverage"], best["threshold"]) if best else "none",
        "from %.2f" % lp["threshold"] if lp else "never",
        held, len(entry.get("held_out", [])))


def show(base, tuned):
    for name in sorted(set(base) | set(tuned)):
        for qid in sorted(set(base.get(name, {}).get("questions", {})) | set(tuned.get(name, {}).get("questions", {}))):
            b = base.get(name, {}).get("questions", {}).get(qid)
            t = tuned.get(name, {}).get("questions", {}).get(qid)
            print("%s.%s" % (name, qid))
            print("  base   %s" % (line(b) if b else "-"))
            print("  tuned  %s" % (line(t) if t else "-"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--key-file")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_intermixed_args(argv)
    if args.show:
        base, tuned = (json.loads(Path(p).read_text()) for p in args.paths)
        show(base["sets"], tuned["sets"])
        return 0
    out, folders = args.paths[0], args.paths[1:]
    key = Path(args.key_file).read_text().strip()
    with urllib.request.urlopen(urllib.request.Request(f"{args.url}/v1/sets", headers={
            "Authorization": "Bearer " + key}), timeout=30) as r:
        listing = json.load(r)
    result = {"checkpoint": listing["checkpoint"], "revision": listing["revision"], "sets": judge(args.url, key, folders)}
    Path(out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
