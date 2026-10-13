"""Checks of the S4 training tooling that need neither laya nor the weights: python -m pytest system1/train"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import corpus  # noqa: E402
import pin  # noqa: E402
import train  # noqa: E402


@pytest.fixture(scope="module")
def built():
    return corpus.build()


def test_the_corpus_is_the_same_for_a_seed(built):
    again, _ = corpus.build()
    assert again == built[0]
    other, _ = corpus.build(seed=corpus.SEED + 1)
    assert other != built[0]


def test_every_set_is_in_the_corpus_with_its_own_questions(built):
    rows, report = built
    assert set(report) == set(corpus.SETS)
    for name in corpus.SETS:
        spec, _ = corpus.load_set(name, corpus.QUESTIONS, corpus.DRAFTS)
        mine = [r for r in rows if r["set"] == name]
        assert len(mine) >= 150, name
        assert all(r["questions"] == spec["questions"] for r in mine)
        for qid, q in spec["questions"].items():
            # every option is trained on, at least 10 times (log-triage's routine lines rarely reach it)
            seen = [r["expected"][qid] for r in mine]
            assert all(seen.count(k) >= (5 if k == "info" else 10) for k in q["criteria"]), (name, qid)


def test_no_training_state_is_near_an_evaluation_state(built):
    rows, _ = built
    for name, (_, field, _) in corpus.SETS.items():
        _, evals = corpus.load_set(name, corpus.QUESTIONS, corpus.DRAFTS)
        held = [corpus.words(json.dumps(e["state"], ensure_ascii=False)) for e in evals]
        for r in rows:
            if r["set"] == name:
                w = corpus.words(json.dumps(r["state"], ensure_ascii=False))
                assert all(corpus.jaccard(w, h) < corpus.OVERLAP for h in held), r["state"]


def test_intake_trains_both_languages(built):
    rows, _ = built
    langs = {r["lang"] for r in rows if r["set"] == "operator-intake"}
    assert langs == {"en", "es"}


def test_served_files_are_only_what_the_wrapper_downloads(tmp_path):
    for rel in ("model.safetensors", "rl_agent_config.json", "tokenizer/tokenizer.json",
                "encoder/config.json", "questions.json", "train_report.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(rel)
    assert sorted(train.served_files(tmp_path)) == [
        "encoder/config.json", "model.safetensors", "rl_agent_config.json", "tokenizer/tokenizer.json"]


def test_every_pinned_base_file_counts_as_served(tmp_path):
    pinned = json.loads(train.PINS.read_text())[train.BASE_REPO][train.BASE_REVISION][train.CHECKPOINT]
    for rel in pinned:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(rel)
    assert sorted(train.served_files(tmp_path)) == sorted(pinned)


@pytest.mark.parametrize("argv, message", [
    (["not a repo", "a" * 40, "out"], "owner/name"),
    (["example/laya", "main", "out"], "40-character"),
])
def test_pin_refuses_bad_names(argv, message):
    with pytest.raises(SystemExit) as exc:
        pin.main(argv)
    assert message in str(exc.value)


def test_pin_refuses_files_that_changed_since_training(tmp_path, monkeypatch):
    out = tmp_path / "out"
    (out / "multilingual").mkdir(parents=True)
    (out / "multilingual" / "model.safetensors").write_text("weights")
    (out / "p4n4-train.json").write_text(json.dumps({"files": {"model.safetensors": "0" * 64}}))
    with pytest.raises(SystemExit) as exc:
        pin.main(["example/laya", "a" * 40, str(out)])
    assert "no longer matches" in str(exc.value)


def test_pin_writes_the_local_hashes(tmp_path, monkeypatch):
    out = tmp_path / "out"
    (out / "multilingual").mkdir(parents=True)
    (out / "multilingual" / "model.safetensors").write_text("weights")
    files = train.served_files(out / "multilingual")
    (out / "p4n4-train.json").write_text(json.dumps({"files": files}))
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"convaiinnovations/laya": {}}))
    monkeypatch.setattr(pin, "PINS", pins)
    assert pin.main(["example/laya", "a" * 40, str(out)]) == 0
    assert json.loads(pins.read_text())["example/laya"]["a" * 40] == {"multilingual": files}
