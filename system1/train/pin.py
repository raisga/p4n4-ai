"""Pin a published fine-tuned checkpoint in pins.json (system1.md §17.5).

    python pin.py REPO REVISION OUT

REPO is the Hugging Face repository p4n4 controls, REVISION the 40-character commit the push
created, and OUT the directory `train.py` wrote. The hashes come from the local files, never from
the hub, so the image refuses anything but what was trained and evaluated here. Rebuild the image
afterwards: the pins are part of it.
"""
import json
import re
import sys
from pathlib import Path

from train import CHECKPOINT, PINS, served_files

REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    repo, revision, out = argv
    if not REPO_RE.match(repo):
        sys.exit("pin: %r is not an owner/name repository" % repo)
    if not SHA_RE.match(revision):
        sys.exit("pin: the revision must be a 40-character commit sha, never a branch")
    manifest = json.loads((Path(out) / "p4n4-train.json").read_text())
    files = served_files(Path(out) / CHECKPOINT)
    if files != manifest["files"]:
        sys.exit("pin: %s/%s no longer matches p4n4-train.json; pin only what was evaluated" % (out, CHECKPOINT))
    pins = json.loads(PINS.read_text())
    pins.setdefault(repo, {})[revision] = {CHECKPOINT: files}
    PINS.write_text(json.dumps(pins, indent=2) + "\n")
    print("pin: %s@%s %s, %d files" % (repo, revision[:12], CHECKPOINT, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
