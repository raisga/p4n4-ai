"""Regression suite for the System 1 image: the contract system1_app.py keeps on top of laya.

Runs the image under test in Docker, hardened as Compose runs it. Needs a models volume that the
pull step has filled (as UID 10001):

    docker volume create system1-test-models
    docker run --rm --user 10001:10001 -e HF_HUB_OFFLINE=0 -e SYSTEM1_REVISION=<sha> \
        -v system1-test-models:/models <image> python /app/system1_app.py pull
    SYSTEM1_TEST_IMAGE=<image> SYSTEM1_TEST_MODELS=system1-test-models pytest system1/tests

`make system1-test` in the stack does all three.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import secrets
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

IMAGE = os.environ.get("SYSTEM1_TEST_IMAGE", "p4n4-system1:dev")
MODELS = os.environ.get("SYSTEM1_TEST_MODELS", "system1-test-models")
REVISION = os.environ.get("SYSTEM1_REVISION", "aa8c91ca088ec597df95a0d1c76b3063cb2ae5e8")
QUESTIONS = Path(__file__).resolve().parents[2] / "config" / "system1" / "questions"
SNAPSHOT = f"/models/hub/models--convaiinnovations--laya/snapshots/{REVISION}"
KEY = secrets.token_hex(32)
HARDENED = [
    *("--user", "10001:10001", "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL"),
    *("--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "2g"),
]

SMOKE = "Smoke detected in electrical cabinet 3"
CAUSE = {
    "type": "choice",
    "instructions": "What is the most likely cause of the alert?",
    "criteria": {"electrical": "power, fuse, smoke in a cabinet", "thermal": "overheating"},
}


def docker(*args: str, timeout: float = 120, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=check)


def run_args(env: dict[str, str] | None = None, mounts: list[str] = (), questions: Path = QUESTIONS,
             models: str = MODELS):
    env = {"LAYA_API_KEY": KEY, "LAYA_THREADS": "2", "SYSTEM1_REVISION": REVISION, **(env or {})}
    args = [*HARDENED, "-v", f"{models}:/models:ro", "-v", f"{questions}:/config/questions:ro"]
    for m in mounts:
        args += ["-v", m]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    return [*args, IMAGE]


def start_fails(message: str, **kw) -> None:
    """The service refuses to start: exit status 1 and `message` in its output."""
    result = docker("run", "--rm", *run_args(**kw), timeout=180)
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr + result.stdout


@pytest.fixture(scope="session")
def server():
    """A running service, hardened as in Compose; yields its host port and container id."""
    name = f"system1-test-{os.getpid()}"
    docker("run", "-d", "--name", name, "-p", "127.0.0.1::8000", *run_args(), check=True)
    try:
        port = int(docker("port", name, "8000", check=True).stdout.split(":")[-1])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if request(port, "GET", "/health", auth=None)[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            pytest.fail("service not healthy:\n" + docker("logs", name).stdout)
        yield port, name
    finally:
        docker("rm", "-f", name)


def request(port, method, path, body=None, auth=KEY, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    headers = {"Content-Type": "application/json"}
    if auth is not None:
        headers["Authorization"] = "Bearer " + auth
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    out = resp.read()
    try:
        return resp.status, json.loads(out)
    except ValueError:
        return resp.status, out


def triage(port, alert, **kw):
    return request(port, "POST", "/v1/sets/incident-triage", {"state": {"alert": alert}}, **kw)


# ── Fail-closed starts ───────────────────────────────────────────────────────


def test_refuses_without_key():
    start_fails("LAYA_API_KEY must be set", env={"LAYA_API_KEY": ""})
    start_fails("LAYA_API_KEY must be set", env={"LAYA_API_KEY": "short"})


def test_refuses_branch_revision():
    start_fails("40-character commit sha", env={"SYSTEM1_REVISION": "main"})


def test_refuses_unpinned_revision():
    start_fails("no pinned hashes", env={"SYSTEM1_REVISION": "0" * 40})


def test_refuses_unknown_and_unlicensed_checkpoints():
    start_fails("SYSTEM1_CHECKPOINT must be one of", env={"SYSTEM1_CHECKPOINT": "nope"})
    start_fails("typed-decisions is excluded", env={"SYSTEM1_CHECKPOINT": "typed-decisions"})


def test_refuses_settings_that_change_answers():
    start_fails("LAYA_TOURNAMENT_GROUP", env={"LAYA_TOURNAMENT_GROUP": "4"})
    start_fails("LAYA_JEV_STRICT", env={"LAYA_JEV_STRICT": "1"})


def test_refuses_missing_checkpoint():
    volume = f"system1-test-empty-{os.getpid()}"
    docker("volume", "create", volume, check=True)
    try:
        result = docker("run", "--rm", *run_args(models=volume), timeout=120)
        assert result.returncode == 1
        assert "run the pull step as the service user" in result.stderr
    finally:
        docker("volume", "rm", volume)


@pytest.mark.parametrize("file", ["model.safetensors", "tokenizer/tokenizer_config.json"])
def test_refuses_modified_checkpoint_files(tmp_path, file):
    fake = tmp_path / "fake"
    fake.write_text("{}")
    fake.chmod(0o644)
    target = f"{SNAPSHOT}/multilingual/{file}"
    start_fails("does not match its pinned hashes", mounts=[f"{fake}:{target}:ro"])


def test_refuses_bad_calibration(tmp_path):
    start_fails("cannot read the calibration file", env={"SYSTEM1_CALIBRATION": "/nope.json"})
    cal = tmp_path / "cal.json"
    for bad in ({"choice:7": 1.2}, {"choice:2": 9}, {"choice:2": True}):
        cal.write_text(json.dumps(bad))
        cal.chmod(0o644)
        start_fails(
            "calibration",
            env={"SYSTEM1_CALIBRATION": "/cal/cal.json"},
            mounts=[f"{tmp_path}:/cal:ro"],
        )


@pytest.mark.parametrize(
    "spec, message",
    [
        ({"version": 1, "questions": {"q": {**CAUSE, "type": "score"}}}, "must be of type 'choice'"),
        ({"version": 0, "questions": {"q": CAUSE}}, "positive integer"),
        ({"version": 1, "questions": {"q": CAUSE}, "thresholds": {"q": 2}}, "lie in [0, 1]"),
        ({"version": 1, "questions": {"q": CAUSE}, "thresholds": {"x": 0.5}}, "must name a question"),
        ({"version": 1, "questions": {"q": CAUSE}, "threshold_on": "top"}, "threshold_on"),
        ({"version": 1, "questions": {"q": CAUSE}, "extra": 1}, "unknown keys"),
        ({"version": 1, "questions": {"q": CAUSE}, "temperatures": {"q": 0.1}}, "lie in [0.5, 5]"),
        ({"version": 1, "questions": {"q": CAUSE}, "temperatures": {"x": 1}}, "temperatures ['x']"),
        (
            {"version": 1, "questions": {"q": {**CAUSE, "criteria": {"a": "word " * 60, "b": "x"}}}},
            "options over 48 tokens would be cut",
        ),
        (
            {"version": 1, "questions": {"q": {**CAUSE, "criteria": {f"k{i}": "a b c d e f g h " * 5
                                                                   for i in range(8)}}}},
            "instructions and options are",
        ),
    ],
)
def test_refuses_bad_question_sets(tmp_path, spec, message):
    (tmp_path / "bad.json").write_text(json.dumps(spec))
    tmp_path.chmod(0o755)
    (tmp_path / "bad.json").chmod(0o644)
    start_fails(message, questions=tmp_path)


# ── Requests ─────────────────────────────────────────────────────────────────


def test_health_is_open(server):
    port, _ = server
    status, body = request(port, "GET", "/health", auth=None)
    assert status == 200 and body["status"] == "ok"


def test_set_answer(server):
    port, _ = server
    status, body = triage(port, SMOKE)
    assert status == 200
    assert body["set"] == {"name": "incident-triage", "version": 3}
    cause = body["answers"]["cause"]
    assert cause["choice"] == "electrical" and cause["abstain"] is False
    assert cause["temperature"] == 1.0  # the checkpoint's own: no site file, no set temperature
    assert len(body["state_sha256"]) == 64
    assert body["usage"]["input_tokens"] > 0


def test_set_abstains_under_threshold(server):
    port, _ = server
    status, body = triage(port, "Status changed.")
    assert status == 200 and body["answers"]["cause"]["abstain"] is True


def test_auth(server):
    port, _ = server
    assert triage(port, SMOKE, auth=None)[0] == 401
    assert triage(port, SMOKE, auth="x" * 64)[0] == 401
    assert request(port, "POST", "/v1/systemone", {"state": SMOKE, "questions": {"q": CAUSE}},
                   auth=None)[0] == 401


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/v1/sets/nope"),
        ("GET", "/v1/sets/incident-triage"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("POST", "/v1/systemone/batch"),
        ("GET", "/v1/systemone"),
        ("POST", "/v1/sets"),
    ],
)
def test_only_four_routes(server, method, path):
    port, _ = server
    body = {"states": [SMOKE], "questions": {"q": CAUSE}} if method == "POST" else None
    assert request(port, method, path, body)[0] == 404


def test_set_listing(server):
    port, _ = server
    assert request(port, "GET", "/v1/sets", auth=None)[0] == 401
    status, body = request(port, "GET", "/v1/sets")
    assert status == 200 and body["checkpoint"] == "multilingual" and body["revision"] == REVISION[:12]
    sets = {s["name"]: s for s in body["sets"]}
    shipped = {p.stem: json.loads(p.read_text()) for p in QUESTIONS.glob("*.json")}
    assert set(sets) == set(shipped)
    for name, spec in shipped.items():
        assert sets[name]["version"] == spec["version"]
        for qid, q in spec["questions"].items():
            listed = sets[name]["questions"][qid]
            assert listed["options"] == list(q["criteria"])
            assert listed["threshold"] == spec["thresholds"].get(qid, 0.0)
            assert listed["temperature"] == spec.get("temperatures", {}).get(qid, 1.0)


def test_bad_bodies(server):
    port, _ = server
    assert request(port, "POST", "/v1/sets/incident-triage", {"alert": SMOKE})[0] == 400
    assert request(port, "POST", "/v1/sets/incident-triage", raw=b"{nope")[0] == 400
    assert request(port, "POST", "/v1/systemone", raw=b"[1]")[0] == 400


@pytest.mark.parametrize(
    "field, value", [("max_len", 4096), ("head_max_len", 512), ("lang", "en"), ("task", "x"),
                     ("min_confidence", 0.1), ("hooks", [])]
)
def test_per_request_controls_refused(server, field, value):
    port, _ = server
    status, body = request(port, "POST", "/v1/systemone",
                           {"state": SMOKE, "questions": {"q": CAUSE}, field: value})
    assert status == 422 and field in body["detail"]


def test_model_is_ignored(server):
    port, _ = server
    status, body = request(port, "POST", "/v1/systemone",
                           {"state": SMOKE, "questions": {"q": CAUSE}, "model": "english"})
    assert status == 200 and body["routing"]["model"] == "multilingual"


def test_budgets_are_errors(server):
    port, _ = server
    many = {f"q{i}": CAUSE for i in range(9)}
    status, body = request(port, "POST", "/v1/systemone", {"state": SMOKE, "questions": many})
    assert status == 422 and "at most 8 questions" in body["detail"]
    status, body = triage(port, "a" * 4001)
    assert status == 422 and "4000 state characters" in body["detail"]
    syslog = " ".join(f"kernel: [{i}.{i:06d}] eth0: link {i % 7} down rx={i * 97} tx={i * 31}"
                      for i in range(60))[:3900]
    status, body = triage(port, syslog)
    assert status == 422 and "checkpoint reads at most 764" in body["detail"]
    long = {**CAUSE, "criteria": {"a": "word " * 60, "b": "x"}}
    status, body = request(port, "POST", "/v1/systemone", {"state": SMOKE, "questions": {"q": long}})
    assert status == 422 and "would be cut" in body["detail"]


def test_body_limit(server):
    port, _ = server
    status, body = triage(port, "x" * 70000)
    assert status == 413


def test_chunked_body_limit_doesnt_buffer(server):
    """F10: a chunked body without Content-Length is counted as it arrives and refused."""
    port, name = server
    before = _rss_kib(name)
    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    sock.sendall(
        b"POST /v1/sets/incident-triage HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n"
        + b"Authorization: Bearer " + KEY.encode() + b"\r\nContent-Type: application/json\r\n\r\n"
    )
    chunk = b"x" * (1 << 20)
    started, reply = time.monotonic(), b""
    try:
        for _ in range(384):
            sock.sendall(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
    except OSError:
        pass  # the server answered and closed while the rest was still being sent
    try:
        reply = sock.recv(4096)
    finally:
        sock.close()
    assert b" 413 " in reply.split(b"\r\n")[0]
    assert time.monotonic() - started < 30
    assert _rss_kib(name) - before < 64 * 1024


def _rss_kib(container: str) -> int:
    status = docker("exec", container, "cat", "/proc/1/status", check=True).stdout
    return int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS")))


def test_chunking_is_exact(server):
    port, _ = server
    questions = {
        "a": CAUSE,
        "b": {**CAUSE, "instructions": "Which team should look at it?"},
        "c": {**CAUSE, "criteria": {"x": "anything electrical", "y": "anything else hot"}},
    }
    _, together = request(port, "POST", "/v1/systemone", {"state": SMOKE, "questions": questions})
    for qid, q in questions.items():
        _, alone = request(port, "POST", "/v1/systemone", {"state": SMOKE, "questions": {qid: q}})
        assert alone["answers"][qid]["probabilities"] == together["answers"][qid]["probabilities"]


@contextmanager
def extra_server(suffix, **kw):
    """A second service with other settings; yields its host port."""
    name = f"system1-test-{suffix}-{os.getpid()}"
    docker("run", "-d", "--name", name, "-p", "127.0.0.1::8000", *run_args(**kw), check=True)
    try:
        port = int(docker("port", name, "8000", check=True).stdout.split(":")[-1])
        for _ in range(120):
            try:
                if request(port, "GET", "/health", auth=None)[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        yield port
    finally:
        docker("rm", "-f", name)


def test_calibration_applies(tmp_path, server):
    port, _ = server
    question = {"q": {"type": "choice", "instructions": "Is this about power?",
                      "criteria": {"A": "it is about power", "B": "it is about something else"}}}
    body = {"state": "Fan noise in room 2", "questions": question}
    p = request(port, "POST", "/v1/systemone", body)[1]["answers"]["q"]["probabilities"]["A"]
    (tmp_path / "cal.json").write_text(json.dumps({"choice:2": 1.9}))
    tmp_path.chmod(0o755)
    (tmp_path / "cal.json").chmod(0o644)
    with extra_server("cal", env={"SYSTEM1_CALIBRATION": "/cal/cal.json"},
                      mounts=[f"{tmp_path}:/cal:ro"]) as cal_port:
        got = request(cal_port, "POST", "/v1/systemone", body)[1]["answers"]["q"]["probabilities"]["A"]
    logit = math.log(p / (1 - p))
    assert got == pytest.approx(1 / (1 + math.exp(-logit / 1.9)), abs=2e-4)


def test_question_temperatures_apply(tmp_path, server):
    """A set's own temperature replaces the bucket's for that question only, and the answer says
    which one was applied; the site file still applies to the set's other questions."""
    port, _ = server
    power = {"type": "choice", "instructions": "Is this about power?",
             "criteria": {"A": "it is about power", "B": "it is about something else"}}
    state = "Fan noise in room 2"
    plain = request(port, "POST", "/v1/systemone", {"state": state, "questions": {"q": power}})
    p = plain[1]["answers"]["q"]["probabilities"]["A"]
    spec = {"version": 1, "questions": {"own": power, "bucket": power}, "temperatures": {"own": 2.5}}
    (tmp_path / "q").mkdir()
    (tmp_path / "q" / "t.json").write_text(json.dumps(spec))
    (tmp_path / "cal.json").write_text(json.dumps({"choice:2": 1.9}))
    for path in (tmp_path, tmp_path / "q"):
        path.chmod(0o755)
    for path in (tmp_path / "cal.json", tmp_path / "q" / "t.json"):
        path.chmod(0o644)
    with extra_server("temp", questions=tmp_path / "q", env={"SYSTEM1_CALIBRATION": "/cal/cal.json"},
                      mounts=[f"{tmp_path}:/cal:ro"]) as t_port:
        status, body = request(t_port, "POST", "/v1/sets/t", {"state": state})
        listing = request(t_port, "GET", "/v1/sets")[1]
    assert status == 200
    logit = math.log(p / (1 - p))
    own, bucket = body["answers"]["own"], body["answers"]["bucket"]
    assert own["temperature"] == 2.5 and bucket["temperature"] == 1.9
    # rounding to 4 places before re-tempering costs a few 1e-4 at most
    assert own["probabilities"]["A"] == pytest.approx(1 / (1 + math.exp(-logit / 2.5)), abs=5e-4)
    assert bucket["probabilities"]["A"] == pytest.approx(1 / (1 + math.exp(-logit / 1.9)), abs=2e-4)
    top = max(own["probabilities"].values())
    assert own["answer_confidence"] == pytest.approx(top, abs=1e-4)
    entropy = -sum(x * math.log(x) for x in own["probabilities"].values() if x > 0)
    assert own["confidence"] == pytest.approx(1 - entropy / math.log(2), abs=5e-4)
    assert own["choice"] == bucket["choice"]
    questions = listing["sets"][0]["questions"]
    assert questions["own"]["temperature"] == 2.5 and questions["bucket"]["temperature"] == 1.9


def test_hardened(server):
    _, name = server
    status = docker("exec", name, "cat", "/proc/1/status", check=True).stdout
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    assert fields["CapEff"].strip() == "0000000000000000"
    assert fields["NoNewPrivs"].strip() == "1"
    assert docker("exec", name, "id", "-u", check=True).stdout.strip() == "10001"
    assert docker("exec", name, "touch", "/app/x").returncode != 0


def test_logs_carry_no_state(server):
    port, name = server
    secret = "operator Jane Doe reports smoke at cabinet 9"
    triage(port, secret)
    logs = docker("logs", name).stdout
    assert secret not in logs
    line = [ln for ln in logs.splitlines() if ln.startswith("{") and '"/v1/sets"' in ln][-1]
    entry = json.loads(line)
    assert entry["set"] == "incident-triage" and entry["status"] == 200
    assert len(entry["state_sha256"]) == 64 and entry["input_tokens"] > 0


# ── Shipped question sets ────────────────────────────────────────────────────


@pytest.mark.parametrize("path", sorted(QUESTIONS.glob("*.json")), ids=lambda p: p.stem)
def test_shipped_sets_pass_their_gates(server, path):
    """Rule 10: every shipped set passes its gates on its evaluation file (system1.md §10)."""
    s1 = pytest.importorskip("p4n4_lib.system1")
    port, _ = server
    qset = s1.load_set(path)
    examples = s1.load_examples(qset)
    answers, latencies = [], []
    for ex in examples:
        started = time.monotonic()
        status, body = request(port, "POST", f"/v1/sets/{qset.name}", {"state": ex.state})
        latencies.append((time.monotonic() - started) * 1000)
        assert status == 200, body
        answers.append(body["answers"])
    report = s1.evaluate(qset, examples, answers, latencies)
    assert report.passed, json.dumps(report.as_dict(), indent=2)
