"""p4n4 System 1 service: laya-serve's HTTP API with a pinned and hash-checked checkpoint, one
resident model, request limits sized for small hosts, no silent truncation, server-side question
sets and optional site calibration. `python system1_app.py pull` downloads the checkpoint and exits.

Only four routes are served: POST /v1/sets/<name>, GET /v1/sets, POST /v1/systemone and GET /health.
Every other route laya-serve has (the batch route, the OpenAPI pages) answers 404, and /v1/systemone accepts only
`state`, `questions` and `model` (which is ignored), so per-request budgets, languages and hooks that
newer laya releases add can't reach the model. See docs/decisions/system1.md, Appendix A."""
import hashlib
import hmac
import json
import logging
import math
import os
import sys
import time

import torch
import uvicorn
from huggingface_hub import snapshot_download
from laya import Router
from laya.common import QTYPES, TEMP_MAX, TEMP_MIN, render_options
from laya.serve import create_app

REPO = os.environ.get("SYSTEM1_REPO", "convaiinnovations/laya")
REVISION = os.environ.get("SYSTEM1_REVISION", "")  # a commit sha, never a branch
CHECKPOINT = os.environ.get("SYSTEM1_CHECKPOINT", "multilingual")
# typed-decisions also loads, but its base model and licence aren't stated (system1.md §2.5)
SUBFOLDERS = {"english": None, "multilingual": "multilingual"}
FILES = ("rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*")
PINS_FILE = os.environ.get("SYSTEM1_PINS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pins.json"))
MAX_QUESTIONS = int(os.environ.get("SYSTEM1_MAX_QUESTIONS", "8"))
MAX_STATE_CHARS = int(os.environ.get("SYSTEM1_MAX_STATE_CHARS", "4000"))
MAX_BODY_BYTES = int(os.environ.get("SYSTEM1_MAX_BODY_BYTES", "65536"))
CHUNK = int(os.environ.get("SYSTEM1_QUESTION_CHUNK", "2"))
FP16_EMBEDDINGS = os.environ.get("SYSTEM1_FP16_EMBEDDINGS", "1") == "1"
QUESTIONS_DIR = os.environ.get("SYSTEM1_QUESTIONS", "/config/questions")
# SYSTEM1_CALIBRATION names a file here, or is an absolute path
CALIBRATION_DIR = os.environ.get("SYSTEM1_CALIBRATION_DIR", "/config/calibration")
OPTION_TOKENS = 48  # laya's build_sequence reads at most this many tokens of each option
BUCKETS = {"%s:%s" % (t, n) for t in QTYPES for n in ("2", "3-5", "6-10", "11+")}  # laya's temp_bucket
THRESHOLD_ON = ("confidence", "answer_confidence")
SET_KEYS = {"version", "description", "questions", "thresholds", "threshold_on", "temperatures", "eval"}
# laya rounds probabilities to 4 decimals, so a 0 is anything under 5e-5 (p4n4_lib.system1 fits the same)
PROB_FLOOR = 5e-5
SYSTEMONE_FIELDS = {"state", "questions", "model"}
# laya-serve settings that change answers or the response shape behind the wrapper's back
REFUSED_ENV = ("LAYA_TOURNAMENT_GROUP", "LAYA_JEV_STRICT", "LAYA_AUTO_TASK", "LAYA_EXTRA_MODELS",
               "LAYA_IDLE_UNLOAD_SECONDS")

log = logging.getLogger("system1")


def fail(message):
    sys.exit("system1: " + message)


def state_sha256(state):
    """sha256 of the state as compact JSON with sorted keys: what the decision log records."""
    text = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PinnedRouter(Router):
    """One resident checkpoint, bounded work per request, no silent truncation.

    Each question is encoded as its own sequence with the full state, so cost and peak memory
    grow with questions x state tokens. Questions are independent, so chunking them is exact.
    """

    tok = None
    agent = None
    head_budget = 0
    state_budget = 0

    def check_question(self, qid, qdef):
        """Reject a question that laya would answer from a cut-down copy of its own text."""
        self.agent._check_question(qid, qdef)
        q = self.agent._to_internal(qdef)
        opts = render_options(q)
        sizes = [len(self.tok(" " + o, add_special_tokens=False)["input_ids"]) for o in opts]
        long = [o[:40] for o, n in zip(opts, sizes) if n > OPTION_TOKENS]
        if long:
            raise ValueError("question %r: options over %d tokens would be cut: %s" % (qid, OPTION_TOKENS, long))
        head = len(self.tok("%s question: %s" % (q["t"], q["ins"]), add_special_tokens=False)["input_ids"])
        used = head + sum(n + 1 for n in sizes)  # each option is [MASK] + its tokens
        if used > self.head_budget:
            raise ValueError("question %r: instructions and options are %d tokens; the %s checkpoint reads "
                             "at most %d" % (qid, used, CHECKPOINT, self.head_budget))

    def predict(self, state, questions, model=None, **kw):
        # Per-request budgets, languages, tasks and hooks would bypass the checks below; the HTTP
        # layer never sends them, and nothing else may
        extra = sorted(k for k, v in kw.items() if v is not None)
        if extra:
            raise ValueError("system1 does not accept %s per request" % ", ".join(extra))
        if not isinstance(questions, dict) or not isinstance(state, (str, dict, list)):
            return super().predict(state, questions, model=CHECKPOINT)  # laya's own 422
        text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
        if len(questions) > MAX_QUESTIONS or len(text) > MAX_STATE_CHARS:
            raise ValueError("system1 accepts at most %d questions and %d state characters per request"
                             % (MAX_QUESTIONS, MAX_STATE_CHARS))
        for qid, qdef in questions.items():
            self.check_question(qid, qdef)
        tokens = len(self.tok(text, add_special_tokens=False)["input_ids"])
        if tokens > self.state_budget:
            # laya would cut the state to fit and still answer, from evidence the caller never sees
            raise ValueError("state is %d tokens; the %s checkpoint reads at most %d, send a shorter "
                             "canonical state" % (tokens, CHECKPOINT, self.state_budget))
        ids, out = list(questions), None
        for i in range(0, len(ids), CHUNK):
            part = super().predict(state, {k: questions[k] for k in ids[i:i + CHUNK]}, model=CHECKPOINT)
            if out is None:
                out = part
            else:
                out["answers"].update(part["answers"])
                out["usage"]["input_tokens"] += part["usage"]["input_tokens"]
        return out


class HalfEmbedding(torch.nn.Module):
    """A vocabulary table stored in fp16 that returns fp32 rows (lookup only)."""

    def __init__(self, weight, padding_idx=None):
        super().__init__()
        self.register_buffer("weight", weight)
        self.padding_idx = padding_idx

    def forward(self, ids):
        return torch.nn.functional.embedding(ids, self.weight, self.padding_idx).float()


def use_half_embeddings(model, weights_file, min_rows=50000):
    """Keep large vocabulary tables in fp16, read straight from the checkpoint.

    The checkpoints are stored in F16, so this is lossless. Each fp32 table is released before
    its fp16 copy is read, so start-up never peaks above the plain fp32 footprint.
    """
    from safetensors import safe_open
    names = [n for n, m in model.named_modules()
             if isinstance(m, torch.nn.Embedding) and m.num_embeddings >= min_rows]
    with safe_open(weights_file, framework="pt") as f:
        for name in names:
            parent_name, _, attr = name.rpartition(".")
            parent = model.get_submodule(parent_name)
            padding_idx = getattr(parent, attr).padding_idx
            setattr(parent, attr, torch.nn.Identity())
            setattr(parent, attr, HalfEmbedding(f.get_tensor(name + ".weight").to(torch.float16), padding_idx))


def retemper(answer, power):
    """A choice answer with its probabilities raised to `power` and renormalised, and its confidences
    recomputed the way laya computes them. laya applies a temperature T as p ** (1 / T), so a power
    of T0 / T replaces the T0 it applied with T. The choice never changes."""
    keys = list(answer["probabilities"])
    logs = [power * math.log(max(answer["probabilities"][k], PROB_FLOOR)) for k in keys]
    top = max(logs)
    exps = [math.exp(v - top) for v in logs]
    total = sum(exps)
    p = [e / total for e in exps]
    k = len(p)
    entropy = -sum(x * math.log(max(x, 1e-12)) for x in p)
    confidence = 1.0 if k < 2 else min(1.0, max(0.0, 1.0 - entropy / math.log(k)))
    return dict(answer, probabilities={key: round(x, 4) for key, x in zip(keys, p)},
                confidence=round(confidence, 4), answer_confidence=round(max(p), 4))


def base_temperature(agent, k):
    """The temperature laya applies to a choice question with `k` options: its bucket's, else the
    checkpoint's for the type (laya.agent._decode_answers)."""
    size = "2" if k <= 2 else "3-5" if k <= 5 else "6-10" if k <= 10 else "11+"
    return agent.temperature_by_options.get("choice:" + size, agent.temperature[QTYPES["choice"]])


def load_question_set(router, path, name):
    """One versioned question set, checked against the model's budgets. Exits on any problem."""
    try:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError) as e:
        fail("question set %s: %s" % (name, e))
    if not isinstance(spec, dict) or not isinstance(spec.get("questions"), dict) or not spec["questions"]:
        fail("question set %s: needs a non-empty 'questions' object" % name)
    unknown = sorted(set(spec) - SET_KEYS)
    if unknown:
        fail("question set %s: unknown keys %s" % (name, unknown))
    version = spec.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        fail("question set %s: 'version' must be a positive integer" % name)
    not_choice = sorted(q for q, d in spec["questions"].items() if not isinstance(d, dict) or d.get("type") != "choice")
    if not_choice:
        # score and noul answers were unusable in the spike (system1.md rule 3)
        fail("question set %s: questions %s must be of type 'choice'" % (name, not_choice))
    thresholds = spec.get("thresholds", {})
    if not isinstance(thresholds, dict):
        fail("question set %s: 'thresholds' must be an object" % name)
    bad = sorted(k for k, v in thresholds.items() if k not in spec["questions"] or isinstance(v, bool)
                 or not isinstance(v, (int, float)) or not 0 <= v <= 1)
    if bad:
        fail("question set %s: thresholds %s must name a question and lie in [0, 1]" % (name, bad))
    threshold_on = spec.get("threshold_on", "confidence")
    if threshold_on not in THRESHOLD_ON:
        fail("question set %s: 'threshold_on' must be one of %s" % (name, list(THRESHOLD_ON)))
    temperatures = spec.get("temperatures", {})
    if not isinstance(temperatures, dict):
        fail("question set %s: 'temperatures' must be an object" % name)
    bad = sorted(k for k, v in temperatures.items() if k not in spec["questions"] or isinstance(v, bool)
                 or not isinstance(v, (int, float)) or not TEMP_MIN <= v <= TEMP_MAX)
    if bad:
        fail("question set %s: temperatures %s must name a question and lie in [%g, %g]"
             % (name, bad, TEMP_MIN, TEMP_MAX))
    if temperatures and getattr(router.agent, "binning_map", None):
        # answer_confidence then comes from a binning map that re-tempering can't reproduce
        fail("question set %s: per-question temperatures need a checkpoint without a binning map" % name)
    try:
        warm = router.predict({}, spec["questions"])
    except ValueError as e:
        fail("question set %s: %s" % (name, e))
    if any(threshold_on not in a for a in warm["answers"].values()):
        fail("question set %s: this laya version returns no %r to threshold on" % (name, threshold_on))
    return {"name": name, "version": version, "questions": spec["questions"],
            "thresholds": {k: float(v) for k, v in thresholds.items()}, "threshold_on": threshold_on,
            "temperatures": {k: float(v) for k, v in temperatures.items()},
            "base_temperatures": {q: base_temperature(router.agent, len(d["criteria"]))
                                  for q, d in spec["questions"].items()}}


def set_listing(sets):
    """GET /v1/sets: what each set asks, and how its answers are tempered and thresholded."""
    return {"checkpoint": CHECKPOINT, "revision": REVISION[:12], "sets": [
        {"name": s["name"], "version": s["version"], "threshold_on": s["threshold_on"],
         "questions": {q: {"options": list(d["criteria"]), "threshold": s["thresholds"].get(q, 0.0),
                           "temperature": s["temperatures"].get(q, s["base_temperatures"][q])}
                       for q, d in s["questions"].items()}}
        for s in sorted(sets.values(), key=lambda s: s["name"])]}


def load_question_sets(router, folder):
    """Versioned question sets from <folder>/<name>.json; <name>.eval.jsonl files never serve."""
    sets = {}
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
        if fn.endswith(".json"):
            sets[fn[:-5]] = load_question_set(router, os.path.join(folder, fn), fn[:-5])
    return sets


async def _reply(send, status, obj):
    body = json.dumps(obj).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive):
    """The request body, or None as soon as it passes MAX_BODY_BYTES. laya-serve 0.3.11 checked only
    a declared Content-Length, so a chunked body was buffered and parsed in full (F10)."""
    body, more = b"", True
    while more:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            return b""
        body, more = body + msg.get("body", b""), msg.get("more_body", False)
        if len(body) > MAX_BODY_BYTES:
            return None
    return body


def _replay(body, receive):
    pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def inner_receive():
        return pending.pop() if pending else await receive()

    return inner_receive


class System1:
    """The HTTP surface in front of laya-serve's app (same auth, limits and single worker).

    POST /v1/sets/<name> {"state": ...} runs a server-side question set through laya's own
    /v1/systemone handler. The response names the set and version, carries the state's sha256,
    applies the set's per-question temperatures, reports each answer's temperature and marks
    answers under the set's threshold as abstained. GET /v1/sets lists the sets. Bodies are
    counted as they arrive and cut off at MAX_BODY_BYTES. Every request is logged as one JSON
    line, without its state."""

    def __init__(self, app, sets, api_key):
        self.app, self.sets, self.key = app, sets, ("Bearer " + api_key).encode()

    def _authorized(self, scope):
        return hmac.compare_digest(dict(scope["headers"]).get(b"authorization", b""), self.key)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, path, method = time.monotonic(), scope["path"], scope["method"]
        entry = {"route": path if not path.startswith("/v1/sets/") else "/v1/sets", "method": method}
        if path == "/health" and method == "GET":
            return await self.app(scope, receive, send)
        status = await self._route(scope, receive, send, entry)
        entry.update(status=status, latency_ms=round((time.monotonic() - started) * 1000))
        log.info(json.dumps(entry, sort_keys=True))

    async def _route(self, scope, receive, send, entry):
        path, method = scope["path"], scope["method"]
        is_set = path.startswith("/v1/sets/")
        listing = path == "/v1/sets" and method == "GET"
        if not (listing or ((is_set or path == "/v1/systemone") and method == "POST")):
            await _reply(send, 404, {"detail": "unknown question set" if is_set else "not found"})
            return 404
        if not self._authorized(scope):
            await _reply(send, 401, {"detail": "invalid or missing bearer token"})
            return 401
        if listing:
            await _reply(send, 200, set_listing(self.sets))
            return 200
        qset = None
        if is_set:
            qset = self.sets.get(path[len("/v1/sets/"):])
            if qset is None:
                await _reply(send, 404, {"detail": "unknown question set"})
                return 404
            entry.update(set=qset["name"], set_version=qset["version"])
        body = await _read_body(receive)
        if body is None:
            await _reply(send, 413, {"detail": "request body too large"})
            return 413
        try:
            request = json.loads(body)
        except ValueError:
            request = None
        if qset is not None:
            if not isinstance(request, dict) or "state" not in request:
                await _reply(send, 400, {"detail": "request body must be an object with a 'state' field"})
                return 400
            request = {"state": request["state"], "questions": qset["questions"]}
        else:
            if not isinstance(request, dict):
                await _reply(send, 400, {"detail": "request body must be a JSON object"})
                return 400
            extra = sorted(set(request) - SYSTEMONE_FIELDS)
            if extra:
                await _reply(send, 422, {"detail": "system1 accepts only %s; unsupported fields: %s"
                                                   % (sorted(SYSTEMONE_FIELDS), extra)})
                return 422
            request.pop("model", None)  # one pinned checkpoint serves every request
        if "state" in request:
            entry["state_sha256"] = state_sha256(request["state"])
        inner = json.dumps(request).encode()
        scope = dict(scope, path="/v1/systemone", raw_path=b"/v1/systemone",
                     headers=[(k, v) for k, v in scope["headers"] if k != b"content-length"]
                     + [(b"content-length", str(len(inner)).encode())])
        start, chunks, sent = {}, [], {}

        async def inner_send(msg):
            if msg["type"] == "http.response.start":
                start.update(msg)
                return
            chunks.append(msg.get("body", b""))
            if msg.get("more_body"):
                return
            out = b"".join(chunks)
            if start["status"] == 200:
                result = json.loads(out)
                entry["input_tokens"] = (result.get("usage") or {}).get("input_tokens")
                if qset is not None:
                    result["set"] = {"name": qset["name"], "version": qset["version"]}
                    result["state_sha256"] = entry["state_sha256"]
                    on = qset["threshold_on"]
                    for qid, answer in list(result["answers"].items()):
                        base, own = qset["base_temperatures"][qid], qset["temperatures"].get(qid)
                        if own is not None and own != base:
                            answer = result["answers"][qid] = retemper(answer, base / own)
                        answer["temperature"] = own if own is not None else base
                        answer["abstain"] = answer[on] < qset["thresholds"].get(qid, 0.0)
                    out = json.dumps(result, ensure_ascii=False).encode()
            headers = [(k, v) for k, v in start.get("headers", []) if k != b"content-length"]
            await send({"type": "http.response.start", "status": start["status"],
                        "headers": headers + [(b"content-length", str(len(out)).encode())]})
            await send({"type": "http.response.body", "body": out})
            sent["status"] = start["status"]

        await self.app(scope, _replay(inner, receive), inner_send)
        return sent.get("status", 500)


def load_pins():
    """sha256 of every checkpoint file, per revision and checkpoint, as built into the image."""
    try:
        with open(PINS_FILE, encoding="utf-8") as f:
            pins = json.load(f)
    except (OSError, ValueError) as e:
        fail("cannot read the hash pins in %s (%s)" % (PINS_FILE, e))
    files = pins.get(REPO, {}).get(REVISION, {}).get(CHECKPOINT)
    if not files:
        fail("%s@%s has no pinned hashes for the %s checkpoint in this image; use an image that pins "
             "that revision" % (REPO, REVISION[:12], CHECKPOINT))
    return files


def verify(local, pinned):
    """Refuse a checkpoint whose files differ from the pinned hashes, before any of them loads."""
    root = os.path.join(local, SUBFOLDERS[CHECKPOINT] or "")
    found = {}
    for folder, _, names in os.walk(root, followlinks=True):
        for fn in names:
            rel = os.path.relpath(os.path.join(folder, fn), root).replace(os.sep, "/")
            if SUBFOLDERS[CHECKPOINT] is None and rel.split("/")[0] in ("multilingual", "typed-decisions"):
                continue
            digest = hashlib.sha256()
            with open(os.path.join(folder, fn), "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    digest.update(block)
            found[rel] = digest.hexdigest()
    wrong = sorted(rel for rel in set(pinned) | set(found) if pinned.get(rel) != found.get(rel))
    if wrong:
        fail("%s checkpoint at %s does not match its pinned hashes: %s; pull it again"
             % (CHECKPOINT, REVISION[:12], wrong))


def snapshot():
    """Local path of the pinned checkpoint, downloaded first unless HF_HUB_OFFLINE=1."""
    if CHECKPOINT not in SUBFOLDERS:
        fail("SYSTEM1_CHECKPOINT must be one of %s, not %r (typed-decisions is excluded until its "
             "licence is stated)" % (sorted(SUBFOLDERS), CHECKPOINT))
    if len(REVISION) != 40 or any(c not in "0123456789abcdef" for c in REVISION):
        fail("SYSTEM1_REVISION must be a 40-character commit sha")
    pinned = load_pins()
    prefix = SUBFOLDERS[CHECKPOINT] + "/" if SUBFOLDERS[CHECKPOINT] else ""
    try:
        local = snapshot_download(REPO, revision=REVISION, allow_patterns=[prefix + f for f in FILES])
    except OSError as e:  # hub errors: offline and not pulled, unknown revision, no network
        fail("%s checkpoint at %s is not available (%s: %s); run the pull step as the service user"
             % (CHECKPOINT, REVISION[:12], type(e).__name__, (str(e).splitlines() or [""])[0][:160]))
    verify(local, pinned)
    return local


def build_app():
    if len(os.environ.get("LAYA_API_KEY", "")) < 32:
        # laya-serve runs without auth when the key is unset; this service never does
        fail("LAYA_API_KEY must be set (32+ chars) when the system1 profile is enabled")
    refused = [k for k in REFUSED_ENV if os.environ.get(k)]
    if refused:
        fail("%s change what laya answers or returns; unset them" % ", ".join(refused))
    threads = int(os.environ.get("LAYA_THREADS") or 0)
    if threads > 0:
        torch.set_num_threads(threads)
    local = snapshot()
    subfolder = SUBFOLDERS[CHECKPOINT]
    router = PinnedRouter(models={CHECKPOINT: (local, subfolder)}, default=CHECKPOINT,
                          max_loaded=1, device=os.environ.get("LAYA_DEVICE") or None)
    agent = router.load(CHECKPOINT)
    router.tok, router.agent = agent.tok, agent
    router.head_budget = agent.cfg.get("head_max_len", 192)
    # laya's build_sequence is [CLS] head [SEP] options [SEP] state [SEP]; check_question keeps
    # head + options within head_max_len, so every question leaves at least this much for the state
    router.state_budget = agent.cfg.get("max_len", 512) - router.head_budget - 4
    if FP16_EMBEDDINGS:
        use_half_embeddings(agent.model, os.path.join(local, subfolder or "", "model.safetensors"))
    calibration = os.environ.get("SYSTEM1_CALIBRATION")
    if calibration and not os.path.isabs(calibration):
        calibration = os.path.join(CALIBRATION_DIR, calibration)
    if calibration:
        try:
            with open(calibration, encoding="utf-8") as f:
                fitted = json.load(f)  # {"choice:2": 1.9, ...}: site-fitted temperatures per laya bucket
        except (OSError, ValueError) as e:
            fail("cannot read the calibration file %s (%s)" % (calibration, e))
        if not isinstance(fitted, dict):
            fail("calibration %s must be an object of {bucket: temperature}" % calibration)
        for bucket, t in fitted.items():
            if (bucket not in BUCKETS or isinstance(t, bool) or not isinstance(t, (int, float))
                    or not TEMP_MIN <= t <= TEMP_MAX):
                fail("calibration %s=%r: use a bucket in %s with a temperature in [%g, %g]"
                     % (bucket, t, sorted(BUCKETS), TEMP_MIN, TEMP_MAX))
            agent.temperature_by_options[bucket] = float(t)
    sets = load_question_sets(router, QUESTIONS_DIR)
    log.info(json.dumps({"event": "ready", "checkpoint": CHECKPOINT, "revision": REVISION[:12],
                         "sets": {s["name"]: s["version"] for s in sets.values()}}, sort_keys=True))
    return System1(create_app(router), sets, os.environ["LAYA_API_KEY"])


if __name__ == "__main__":
    # The service's own lines at LAYA_LOG_LEVEL; libraries (httpx's per-request lines) at warning
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    log.setLevel(os.environ.get("LAYA_LOG_LEVEL", "info").upper())
    if sys.argv[1:] == ["pull"]:
        # run once online, as the service user: huggingface_hub keeps its offline index of the
        # revision (trees/<sha>.json) readable by its owner only
        print("system1: %s checkpoint ready and verified in %s" % (CHECKPOINT, snapshot()))
    else:
        uvicorn.run(build_app(), host=os.environ.get("LAYA_HOST", "0.0.0.0"),
                    port=int(os.environ.get("LAYA_PORT", "8000")),
                    log_level=os.environ.get("LAYA_LOG_LEVEL", "info"))
