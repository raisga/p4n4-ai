"""Write the model card (README.md) of a fine-tuned checkpoint (system1.md §17.5).

    python card.py OUT BASE.json TUNED.json

OUT is the directory `train.py` wrote; BASE.json and TUNED.json are `compare.py` runs of the
base and the fine-tuned checkpoint on the same held-out files. The card states the data, the
recipe, the licences and every set's result, the failing ones included.
"""
import json
import sys
from pathlib import Path

from compare import line
from corpus import SETS


def card(manifest, base, tuned):
    corpus = manifest["corpus"]
    b = manifest["base"]
    rows = []
    for name in sorted(tuned["sets"], key=lambda n: (SETS.get(n, ("drafts",))[0] != "questions", n)):
        t_set, b_set = tuned["sets"][name], base["sets"].get(name, {})
        ships = SETS.get(name, ("drafts",))[0] == "questions"
        gates = "%s → %s" % ("passes" if b_set.get("passed") else "fails", "passes" if t_set["passed"] else "fails")
        for qid, entry in t_set["questions"].items():
            before = b_set.get("questions", {}).get(qid)
            rows.append("| `%s.%s` | %s | %s | %s | %s |" % (
                name, qid, "v%s, threshold %s" % (t_set["version"], entry["threshold"]) if ships else "draft",
                line(before) if before else "-", line(entry), gates if ships else "-"))
    return f"""---
license: apache-2.0
base_model: {b["repo"]}
tags: [laya, p4n4, typed-decisions]
---

# p4n4 System 1: laya `{b["checkpoint"]}`, fine-tuned

A fine-tune of [`{b["repo"]}`](https://huggingface.co/{b["repo"]}) at `{b["revision"]}`
(`{b["checkpoint"]}`, mmBERT-base, MIT; laya, Apache-2.0) for the p4n4 System 1 question sets.
It is served by p4n4's `system1` service, which checks every file against the sha256 pins built
into its image. Design: p4n4-docs, `decisions/system1.md` §17.

## Data

- **Training:** {corpus["rows"]} generic synthetic examples, written from templates by
  `stacks/ai/system1/train/corpus.py` (sha256 `{corpus["sha256"][:16]}…`), by set:
  {", ".join(f"{k} {v}" for k, v in sorted(corpus["rows_by_set"].items()))}; by language:
  {", ".join(f"{k} {v}" for k, v in sorted(corpus["rows_by_lang"].items()))}. No site data, no personal data, and
  neither the upstream notebook nor the `LocalLLaMA/typed-decisions` dataset.
- **Held out:** every set's evaluation file. A training example equal to an evaluation example,
  or sharing 70 % of its words with one, was dropped.
- **Same author.** One person wrote the templates and the evaluation files, so these results
  overstate how well it does on a real site's wording. A site evaluates it on its own file
  before serving it.

## Recipe

laya {manifest["laya"]} `laya.train.finetune`, torch {manifest["torch"]} on {manifest["device"]},
{manifest["minutes"]} minutes: {json.dumps(manifest["recipe"])}. Temperatures were fitted by laya
on a calibration slice of the training corpus.

## Results on the held-out files

"Safe coverage" is the highest coverage at which the confident-wrong and accuracy gates hold;
"gates" the lowest threshold where every gate holds; "held out" how many of three splits keep
every gate on the third the threshold wasn't fitted on. The last column is every gate of a
shipped set, per language included, at that set's own thresholds, which were chosen on the
same files. Draft sets don't ship: p4n4 keeps them out of the service until they pass held
out.

| Question | Set | Base | Fine-tuned | Gates, base → fine-tuned |
|----------|-----|------|------------|--------------------------|
{chr(10).join(rows)}

## Limits

- It knows the p4n4 sets' menus as they were trained. A changed option text, or a site's own
  set, has to be evaluated on it again, and may do better on the base checkpoint.
- It is English and Spanish only where the corpus is (operator intake); the other sets were
  trained in English.

## Files

{chr(10).join(f"- `{b['checkpoint']}/{k}`: `{v}`" for k, v in manifest["files"].items())}
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    out, base, tuned = argv
    manifest = json.loads((Path(out) / "p4n4-train.json").read_text())
    text = card(manifest, json.loads(Path(base).read_text()), json.loads(Path(tuned).read_text()))
    (Path(out) / "README.md").write_text(text, encoding="utf-8")
    print("card: %s/README.md" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
