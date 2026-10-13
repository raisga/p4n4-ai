"""Fine-tune the pinned base checkpoint on the S4 corpus (system1.md §17). Runs off the device.

    python train.py CORPUS OUT [--base DIR] [--epochs N] [--device cpu|cuda|auto]

Run it in the system1 image, which has laya and torch (`make system1-train`). `--base` is the
pinned checkpoint as `system1_app.py pull` leaves it; its files are checked against pins.json
first, so a fine-tune never starts from weights the image would refuse.

OUT gets the repository to publish: `multilingual/` with the files the wrapper downloads,
`p4n4-train.json` (what was trained, on what, and the file hashes) and laya's own
`train_report.json`. `card.py` writes the model card from them once the checkpoint is evaluated.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = HERE.parent / "pins.json"
BASE_REPO = "convaiinnovations/laya"
BASE_REVISION = "aa8c91ca088ec597df95a0d1c76b3063cb2ae5e8"
CHECKPOINT = "multilingual"
BASE_DIR = "/models/hub/models--convaiinnovations--laya/snapshots/%s/%s" % (BASE_REVISION, CHECKPOINT)
# What the wrapper downloads (system1_app.FILES); nothing else is published or pinned
SERVED = ("rl_agent_config.json", "model.safetensors", "tokenizer/", "encoder/")
# The recipe. Defaults are laya.train's, the published notebook's, except where noted.
RECIPE = {
    "epochs": 2,                       # 3 overfit: confident on what it should leave unanswered (§17.3)
    "micro_batch": 8,
    "grad_accum": 2,                   # an effective batch of 16: the corpus is ~2,700 items, not ~30k
    "shuffle_options": ["choice"],     # every option in every slot, so no position prior is learnt
    "gradient_checkpointing": True,    # fits in 10 GiB on CPU
    "calib_frac": 0.1,
    "seed": 0,
    "log_every": 20,
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def served_files(root):
    """{relative path: sha256} of the files the wrapper would download from `root`."""
    out = {}
    for folder, _, names in os.walk(root):
        for fn in names:
            rel = os.path.relpath(os.path.join(folder, fn), root).replace(os.sep, "/")
            if rel in SERVED or any(rel.startswith(p) for p in SERVED if p.endswith("/")):
                out[rel] = sha256(os.path.join(folder, fn))
    return dict(sorted(out.items()))


def check_base(base):
    pinned = json.loads(PINS.read_text())[BASE_REPO][BASE_REVISION][CHECKPOINT]
    found = served_files(base)
    if found != pinned:
        sys.exit("train: %s does not match the pinned %s@%s files: %s"
                 % (base, BASE_REPO, BASE_REVISION[:12], sorted(set(found) ^ set(pinned)) or "hashes differ"))
    return pinned


def corpus_summary(path):
    counts, langs = {}, {}
    for line in open(path, encoding="utf-8"):
        row = json.loads(line)
        counts[row["set"]] = counts.get(row["set"], 0) + 1
        langs[row["lang"]] = langs.get(row["lang"], 0) + 1
    return {"sha256": sha256(path), "rows": sum(counts.values()), "rows_by_set": counts, "rows_by_lang": langs}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus")
    ap.add_argument("out")
    ap.add_argument("--base", default=BASE_DIR)
    ap.add_argument("--epochs", type=int, default=RECIPE["epochs"])
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)

    import laya
    import torch
    from laya.train import TrainConfig, finetune

    base_files = check_base(args.base)
    recipe = dict(RECIPE, epochs=args.epochs)
    config = TrainConfig(**dict(recipe, shuffle_options=tuple(recipe["shuffle_options"])))
    work = Path(args.out) / "work"
    started = time.time()
    result = finetune(args.corpus, args.base, str(work), config, device=args.device)
    minutes = round((time.time() - started) / 60, 1)

    # The published layout keeps the base repository's, so the wrapper's subfolder logic holds
    target = Path(args.out) / CHECKPOINT
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in SERVED:
        src = work / name.rstrip("/")
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, target / name.rstrip("/"))
    shutil.copy2(work / "train_report.json", Path(args.out) / "train_report.json")
    shutil.rmtree(work)

    manifest = {
        "base": {"repo": BASE_REPO, "revision": BASE_REVISION, "checkpoint": CHECKPOINT, "files": base_files},
        "laya": laya.__version__,
        "torch": torch.__version__,
        "device": args.device,
        "minutes": minutes,
        "recipe": recipe,
        "corpus": corpus_summary(args.corpus),
        "train_items": result["train_items"],
        "calibration_items": result["calibration_items"],
        "skipped": result["skipped"],
        "epoch_loss": [round(x, 4) for x in result["epoch_loss"]],
        "temperature": result["temperature"],
        "temperature_by_options": result["temperature_by_options"],
        "files": served_files(target),
    }
    (Path(args.out) / "p4n4-train.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("train: %s in %.1f min; files in %s" % (CHECKPOINT, minutes, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
