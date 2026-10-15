# p4n4-ai

> Dockerized **AI stack** — local LLM inference, stateful AI agents, workflow automation, and Edge Impulse / ONNX inference on the data path.

The AI stack (Ollama · Letta · n8n · System 1 · ei-runner) brings local AI capabilities to your IoT deployment. Ollama runs open-weight LLMs entirely on-device, Letta provides persistent AI agents with long-term memory, n8n wires everything together with event-driven workflows, and the edge inference runner (ei-runner) runs an Edge Impulse `.eim` or ONNX `.onnx` model on every sensor sample.

> **Formerly p4n4-edge.** The edge inference runner was its own stack, p4n4-edge, until it merged into this one as the `ei-runner` profile. See [Migrating from p4n4-edge](#migrating-from-p4n4-edge).

Attaches to the shared `p4n4-net` Docker bridge network created by [`p4n4-iot`](https://github.com/raisga/p4n4-iot), enabling seamless integration with MQTT, InfluxDB, Node-RED, and Grafana.

Part of the [p4n4](https://github.com/raisga/p4n4) platform — an EdgeAI + GenAI integration platform for IoT deployments.

---

## Table of Contents

- [Architecture](#architecture)
- [Stack Components](#stack-components)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Choosing Services](#choosing-services)
- [Project Structure](#project-structure)
- [System 1](#system-1)
- [Edge Inference](#edge-inference)
- [Ollama Models](#ollama-models)
- [n8n Workflows](#n8n-workflows)
- [GPU Support](#gpu-support)
- [Usage](#usage)
- [Default Ports](#default-ports)
- [Default Credentials](#default-credentials)
- [Network Requirements](#network-requirements)
- [Security Hardening](#security-hardening)
- [Local Overrides](#local-overrides)
- [Integration with p4n4-iot](#integration-with-p4n4-iot)
- [Migrating from p4n4-edge](#migrating-from-p4n4-edge)
- [Resources](#resources)
- [License](#license)

---

## Architecture

```
  [p4n4-iot / MQTT / InfluxDB]
           │
           │  (shared p4n4-net bridge)
           ├──────────────────────────────┐
           ▼                              ▼
        [n8n]           ← workflows   [ei-runner]   ← .eim / .onnx model
       /     \                       sensors/<device>/raw in;
      ▼       ▼                      inference/<device>/result
  [Ollama]  [Letta]     ← local LLM   and the ai_events bucket out
                          + agents
```

**Data flow:** n8n subscribes to MQTT topics (via p4n4-net) and triggers AI workflows. Ollama serves local LLM inference, Letta manages persistent AI agents with memory, and n8n routes results back to MQTT, InfluxDB, or external webhooks. The edge inference runner subscribes to `sensors/+/raw`, runs the loaded model on each sample, and publishes the result to `inference/<device-id>/result` and the `ai_events` InfluxDB bucket, where Node-RED, n8n (the Alert Enrichment workflow) and Grafana pick it up.

---

## Stack Components

| Service | Role | Description |
|---------|------|-------------|
| **[Ollama](https://ollama.com/)** | Local LLM Runtime | Runs open-weight models (Llama, Mistral, Phi, etc.) entirely on-device with zero data egress. Exposes an OpenAI-compatible REST API on port 11434. |
| **[Letta](https://letta.com/)** *(optional)* | AI Agent Framework | Stateful AI agent framework with persistent memory (formerly MemGPT). Build agents that remember context across sessions and reason over long-term IoT event histories. |
| **System 1** *(optional)* | Fast Typed Decisions | [laya](https://huggingface.co/convaiinnovations/laya), a small encoder that picks one option from a closed menu in a fraction of a second on the CPU. Advisory routing for n8n and Node-RED: rules decide, System 1 routes, the LLM explains. No host port. See [System 1](#system-1). |
| **[n8n](https://n8n.io/)** *(optional)* | Workflow Automation | Low-code, node-based workflow engine. Connects MQTT, InfluxDB, Ollama, Letta, and external APIs without custom glue code. Includes six starter IoT + AI workflows. |
| **ei-runner** *(optional)* | Edge Inference | Python inference runner. Loads an [Edge Impulse](https://edgeimpulse.com/) `.eim` model or an [ONNX](https://onnx.ai/) `.onnx` model (via [ONNX Runtime](https://onnxruntime.ai/)), subscribes to raw sensor data on MQTT, and publishes results. Falls back to **mock mode** when no model is present. See [Edge Inference](#edge-inference). |

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (v2.0+)
- At least **8 GB RAM** available to Docker (16 GB recommended for larger models)
- `p4n4-iot` running (or `p4n4-net` network created manually — see [Network Requirements](#network-requirements))
- *(Optional)* NVIDIA GPU with drivers + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU acceleration
- *(Optional, for ei-runner)* An Edge Impulse `.eim` model file — download from [Edge Impulse Studio](https://studio.edgeimpulse.com) under **Deployment → Linux (x86_64 or AARCH64)** — or an ONNX `.onnx` model exported from any framework (PyTorch, TensorFlow, scikit-learn, …)

---

## Getting Started

1. **Clone the repository**

   ```bash
   git clone https://github.com/raisga/p4n4-ai.git
   cd p4n4-ai
   ```

2. **Configure environment variables**

   ```bash
   cp .env.example .env
   # Edit .env — at minimum change N8N_ENCRYPTION_KEY and passwords
   ```

3. **Ensure `p4n4-net` exists** (skip if p4n4-iot is already running)

   ```bash
   docker network create p4n4-net
   ```

4. **Start the stack**

   ```bash
   docker compose up -d
   # or
   make up
   ```

5. **Pull a language model**

   ```bash
   make pull-models
   # or pull specific models:
   ./scripts/pull-models.sh llama3.2 nomic-embed-text
   ```

6. **Open the interfaces**

   - n8n: <http://localhost:5678>
   - Letta: <http://localhost:8283>
   - Ollama API: <http://localhost:11434>

   Letta, n8n and the inference runner only run when enabled; see [Choosing Services](#choosing-services).

---

## Choosing Services

Every service is optional. Each one sits in a [Compose profile](https://docs.docker.com/compose/how-tos/profiles/) of its own name, and `COMPOSE_PROFILES` in `.env` lists the ones that start:

```bash
# Default: Ollama only
COMPOSE_PROFILES=ollama

# Ollama with Letta agents and n8n workflows
COMPOSE_PROFILES=ollama,letta,n8n

# Plus System 1 (needs SYSTEM1_API_KEY and `make system1-pull` first)
COMPOSE_PROFILES=ollama,letta,n8n,system1

# Edge inference only, no LLM (e.g. a Raspberry Pi next to the sensors)
COMPOSE_PROFILES=ei-runner

# Ollama explaining what the inference runner finds
COMPOSE_PROFILES=ollama,ei-runner
```

Run `docker compose up -d --remove-orphans` after changing it. `make start SERVICE=<name>` starts any service, whether or not it is listed, and `make down` stops them all. If `.env` has no `COMPOSE_PROFILES` line, plain `docker compose up` starts nothing; the `make` targets fall back to Ollama.

---

## Project Structure

```
p4n4-ai/
├── docker-compose.yml                  # GenAI stack service definitions
├── docker-compose.override.yml.example # Local override template (GPU, dev)
├── Makefile                            # Convenience commands
├── .env.example                        # Environment template (copy to .env)
├── .gitignore
├── config/
│   ├── ollama/                         # Ollama config (models pulled at runtime)
│   ├── letta/
│   │   └── letta.conf                  # Letta server configuration reference
│   ├── n8n/
│   │   └── workflows/
│   │       ├── alert-enrichment.json   # Enrich MQTT alerts with LLM analysis
│   │       ├── scheduled-digest.json   # Hourly telemetry summary via Ollama
│   │       ├── device-onboarding.json  # Auto-register new MQTT devices
│   │       ├── incident-escalation.json # Rules, System 1 suggestion, escalate every alert
│   │       ├── operator-intake.json    # Chat messages to confirmed requests, with System 1
│   │       └── system1-drift.json      # Grafana's System 1 drift alerts to system1/drift/<set>
│   └── system1/
│       ├── questions/
│       │   ├── incident-triage.json        # Question set: likely cause of a critical alert
│       │   ├── incident-triage.eval.jsonl  # Its evaluation examples and gates' input
│       │   ├── operator-intake.json        # Question set: request type and asset of a message
│       │   └── operator-intake.eval.jsonl  # Its examples, in English and Spanish
│       └── calibration/                # Optional site temperatures (SYSTEM1_CALIBRATION)
├── system1/                            # System 1 image: Dockerfile, wrapper, hash pins, locks, tests;
│                                       #   drafts/: S3 sets that don't pass yet (not served);
│                                       #   train/: S4 fine-tuning corpus, training and model card
├── runner/
│   ├── Dockerfile                      # Container image for the edge inference runner
│   ├── runner.py                       # Inference loop: MQTT → model → MQTT + InfluxDB
│   └── requirements.txt                # Python dependencies
├── edge-impulse/
│   └── models/                         # Place .eim files here — NEVER commit them
├── onnx/
│   └── models/                         # Place .onnx files here — NEVER commit them
├── tests/                              # Runner and check_env_example.py tests (pytest tests/)
└── scripts/
    ├── pull-models.sh                  # Helper to pull models into Ollama
    ├── selector.sh                     # Interactive service selector
    └── check_env_example.py            # CI: .env.example completeness check
```

---

## System 1

System 1 runs laya behind a hardened wrapper (`system1/system1_app.py`): one checkpoint,
pinned by commit and by the sha256 of every file, served offline, with a required bearer
key and no silent truncation. It answers server-side question sets in
`config/system1/questions/` and abstains when unsure. Nothing safety-related depends on
it, and every workflow works the same without it. Two sets ship: `incident-triage` for
Incident Escalation and `operator-intake` for Operator Intake; `GET /v1/sets` lists what
the service loaded, and a set's `temperatures` key calibrates single questions. A site file
in `config/system1/calibration/` (`SYSTEM1_CALIBRATION`) calibrates every set, and the
iot stack's Grafana alerts when a set drifts (System 1 Drift workflow below).

```bash
p4n4 ai system1 enable          # with the p4n4 CLI: key, profile, model, n8n credential

# or by hand:
echo "SYSTEM1_API_KEY=$(openssl rand -hex 32)" >> .env   # and add system1 to COMPOSE_PROFILES
make system1-pull               # download and verify the pinned checkpoint
docker compose up -d
```

Until the first image release, build it locally (`make system1-build`) and set
`SYSTEM1_IMAGE=p4n4-system1:dev`. `make system1-test` runs the regression suite against
it, and `make system1-lock` recompiles the hashed dependency locks.

**Fine-tuning (S4).** `make system1-train` fine-tunes `multilingual` on a generic synthetic
corpus for every set, off the device (about 2 h on 8 CPU cores), and writes the repository
to publish to `system1/train/out/`. `system1/train/compare.py` judges it against the base on
the held-out evaluation files, `card.py` writes its model card, and `pin.py` adds its hashes
to `system1/pins.json` once it is pushed to a Hugging Face repository you control. Serve it
with `SYSTEM1_REPO` and `SYSTEM1_REVISION`, after rebuilding the image. The design, the
measurements and the rules of use are in p4n4-docs:
[System 1](https://github.com/raisga/p4n4-docs/blob/main/decisions/system1.md) and the
[AI stack page](https://github.com/raisga/p4n4-docs/blob/main/stacks/ai-stack.md#system-1-typed-decisions).

---

## Edge Inference

The `ei-runner` service runs an [Edge Impulse](https://edgeimpulse.com/) `.eim` model or an [ONNX](https://onnx.ai/) `.onnx` model on the data path. Add `ei-runner` to `COMPOSE_PROFILES` (or run `make start SERVICE=ei-runner`); its image is built from `runner/` on the first start (`make build` rebuilds it).

```bash
make deploy-model MODEL=~/Downloads/my-project-linux-aarch64-v5.eim   # → edge-impulse/models/
make deploy-model MODEL=~/Downloads/my-classifier.onnx                # → onnx/models/
# set EI_MODEL_FILE or ONNX_MODEL_FILE in .env, then recreate the runner:
make up
make test-inference   # publish a sample on MQTT and print the result
```

Without a model the runner starts in mock mode, so the whole pipeline (MQTT → inference → InfluxDB → Grafana) works before a model is trained.

### Model Backends

The runner supports two inference backends, selected via `MODEL_BACKEND` in `.env`:

| Value | Behavior |
|-------|----------|
| `auto` *(default)* | Load the Edge Impulse `.eim` if present, else the ONNX `.onnx`, else mock mode |
| `eim` | Edge Impulse only — the runner stops if no `.eim` is found |
| `onnx` | ONNX Runtime only — the runner stops if no `.onnx` is found |
| `mock` | Simulated inference, no model loaded |

A model file that is present but fails to load also stops the runner, and so does an unknown `MODEL_BACKEND`: the reason is in `docker logs p4n4-ei-runner`, and `restart: unless-stopped` keeps retrying. The runner never falls back to simulated results for a model it was meant to run.

Only one backend is active at a time. The active backend is reported in the `mode` field of the health endpoint and every result payload (`model` = Edge Impulse, `onnx` = ONNX Runtime, `mock` = simulated).

### Edge Impulse Models

1. Train a model in [Edge Impulse Studio](https://studio.edgeimpulse.com)
2. Go to **Deployment → Linux (x86_64)** (or AARCH64 for ARM devices)
3. Click **Build** to download the `.eim` file, then `make deploy-model MODEL=<file>` and set `EI_MODEL_FILE` in `.env`

`.eim` files are standalone executables targeting a specific architecture (x86_64, aarch64, armv7l). The runner image is built for the host's architecture, so on a Raspberry Pi 5 or a Jetson use the AARCH64 build. `EI_API_KEY` is only needed for Edge Impulse cloud features; leave it blank for fully offline deployments.

### ONNX Models

Export a classifier to ONNX from any major framework:

```python
# PyTorch
torch.onnx.export(model, example_input, "my-classifier.onnx")

# scikit-learn
from skl2onnx import to_onnx
onnx_model = to_onnx(clf, X_train[:1].astype(np.float32))
```

Deploy it with `make deploy-model MODEL=my-classifier.onnx`, and set `ONNX_MODEL_FILE` and `ONNX_LABELS` (e.g. `idle,running,anomaly,vibration`) in `.env`.

- The runner feeds the incoming `values` array to the model's **first input** as a `float32` tensor of shape `(1, N)` — `N` must match your model's expected feature count
- Inference runs on CPU (`CPUExecutionProvider`); use the compose override file for GPU execution providers
- Two output shapes are handled:
  - **Score/logit arrays** — softmax is applied automatically when the scores are not already probabilities; labels come from `ONNX_LABELS` (falling back to `class_0`, `class_1`, …)
  - **Probability maps** (e.g. sklearn-onnx `ZipMap` output) — labels are taken from the map keys
- ONNX models do not produce an anomaly score — `anomaly_score` is always `0.0` in `onnx` mode

### Sensor Data Format

Publish JSON to `sensors/<device-id>/raw`, for example `sensors/vibration-sensor-01/raw`. The subscription is configurable via `MQTT_TOPIC_INPUT` (default `sensors/+/raw`).

```json
{
  "values": [1.23, 4.56, 7.89, 0.12, 3.45, 6.78]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `values` | array of floats | Feature vector passed to the model |
| `device` | string | Optional. Device identifier, used only when the topic doesn't follow `sensors/<device-id>/raw` |

The device in the topic becomes the `device` field of the result and its InfluxDB tag. The `values` array must match the feature count expected by your trained model.

### Inference Results

The runner publishes JSON to `inference/<device-id>/result`, using the device from the input topic. The topic is configurable via `MQTT_TOPIC_RESULTS` (default `inference/{device}/result`, where `{device}` is replaced by the device id):

```json
{
  "device": "vibration-sensor-01",
  "timestamp": "2026-03-11T12:00:00.000000+00:00",
  "label": "anomaly",
  "confidence": 0.9234,
  "anomaly_score": 0.8712,
  "latency_ms": 18.4,
  "mode": "model"
}
```

| Field | Description |
|-------|-------------|
| `device` | Device id from the input topic (or the payload's `device` for a custom `MQTT_TOPIC_INPUT`) |
| `timestamp` | ISO 8601 UTC timestamp of inference |
| `label` | Top classification label from the model |
| `confidence` | Confidence score for the top label (0–1) |
| `anomaly_score` | Anomaly score from the model (0–1; higher = more anomalous; always `0.0` in `onnx` mode) |
| `latency_ms` | Inference latency in milliseconds |
| `mode` | `"model"` when running a `.eim`, `"onnx"` when running a `.onnx`, `"mock"` in mock mode |

Results are also written to the `ai_events` InfluxDB bucket (`INFLUXDB_BUCKET_AI_EVENTS`) with the measurement name `inference_result`.

### Mock Mode

With `MODEL_BACKEND=mock`, or with `auto` when no model file is found, the runner runs in **mock mode**: labels are sampled from `["idle", "running", "anomaly", "vibration"]` based on input magnitude, results are published to MQTT and InfluxDB exactly as in model mode with `mode` set to `"mock"`, and a warning is logged at startup.

### Runner HTTP API

```bash
curl http://localhost:8080/health
```

```json
{
  "status": "ok",
  "mode": "model",
  "model_file": "/models/model.eim",
  "inference_count": 142,
  "last_inference_at": "2026-03-11T12:00:00+00:00",
  "last_latency_ms": 11.84,
  "mqtt_connected": true,
  "influxdb_ok": true,
  "started_at": "2026-03-11T11:55:00+00:00"
}
```

`POST /api/v1/infer` runs inference on one sample and returns the result. Unlike a message on `sensors/<device-id>/raw`, the sample and result aren't published to MQTT or written to InfluxDB, so Node-RED and n8n don't see them.

```bash
curl -X POST http://localhost:8080/api/v1/infer \
  -H "Content-Type: application/json" \
  -d '{"values": [1.2, 4.5, 7.8], "device": "bench"}'
```

The response has the same fields as a result on `inference/<device-id>/result`. `device` is optional and defaults to `api`. An invalid body returns 400 with an `error` field. When the loaded model (Edge Impulse or ONNX) fails on the sample, for example because it has the wrong number of values, the answer is 422 with the model's error, not a simulated result. On MQTT, such a sample is dropped with a warning in the log.

Samples, over HTTP or MQTT, must carry a non-empty `values` array of at most `MAX_FEATURES` (default 65536) finite numbers within float32 range. On MQTT, any other message on the input topic is logged and dropped.

`last_latency_ms` in `/health` is the latency of the last pipeline (MQTT) inference; p4n4-api reports it as `inference_ms` in its edge metrics. `GET /api/v1/info` returns the active backend, the model file, details read from the model (the project and labels for Edge Impulse, the input name and shape for ONNX), the configured `ONNX_LABELS` and the MQTT topics.

### Sending Sensor Data Manually

```bash
# From host via mosquitto_pub
mosquitto_pub -h localhost -p 1883 -t sensors/bench-sensor/raw \
  -m '{"values":[1.2,3.4,5.6,0.1,2.3,4.5]}'

# From another container on p4n4-net
docker run --rm --network p4n4-net eclipse-mosquitto:2 \
  mosquitto_pub -h p4n4-mqtt -t sensors/bench-sensor/raw \
  -m '{"values":[1.2,3.4,5.6,0.1,2.3,4.5]}'
```

---

## Ollama Models

Models are not bundled in the image — pull them after starting the stack.

### Pulling Models

```bash
# Pull the default model (llama3.2)
make pull-models

# Pull specific models
./scripts/pull-models.sh llama3.2
./scripts/pull-models.sh llama3.2 nomic-embed-text phi3.5

# Pull directly via Docker
docker exec p4n4-ollama ollama pull llama3.2
```

### Recommended Models

| Model | Size | Use Case |
|-------|------|----------|
| `llama3.2` | 2 GB | General inference, alert analysis, summaries |
| `phi3.5` | 2.2 GB | Lightweight reasoning, classification |
| `nomic-embed-text` | 274 MB | Embeddings for Letta agent memory |
| `llama3.3:70b` | 43 GB | High-quality reasoning (needs a GPU host, far beyond a Raspberry Pi) |

### Listing Installed Models

```bash
make models
# or
docker exec p4n4-ollama ollama list
```

---

## n8n Workflows

Six starter workflows are included in `config/n8n/workflows/`. Import them via the n8n UI:

1. Open n8n at <http://localhost:5678>
2. Create the credentials below
3. Go to **Workflows → Import from File** and select a JSON file from `config/n8n/workflows/`
4. Publish (activate) each imported workflow

Or import them all from the command line, then publish them and restart n8n:

```bash
docker cp config/n8n/workflows p4n4-n8n:/tmp/workflows
docker exec p4n4-n8n n8n import:workflow --separate --input=/tmp/workflows
for id in p4n4AlertEnrichment p4n4DeviceOnboarding p4n4IncidentEscalation p4n4OperatorIntake p4n4ScheduledDigest p4n4System1Drift; do
  docker exec p4n4-n8n n8n publish:workflow --id=$id
done
docker restart p4n4-n8n
```

The workflows have fixed IDs, so importing them again updates them instead of adding copies.

| Workflow | Description |
|----------|-------------|
| `alert-enrichment.json` | Subscribes to `inference/+/result` MQTT topics; sends low-confidence results to Ollama for analysis |
| `scheduled-digest.json` | Runs hourly; queries InfluxDB for recent telemetry and generates a natural-language summary via Ollama |
| `device-onboarding.json` | Listens on `devices/+/register`; auto-registers new devices and publishes a confirmation to MQTT |
| `incident-escalation.json` | Listens on `alerts/+/critical`; site rules route known alerts, [System 1](#system-1) may suggest a team for the rest, every alert goes to `alerts/escalated` with the on-call recipient, and Ollama's summary follows on `alerts/escalated/summary` |
| `operator-intake.json` | Operators' chat messages, from `operator/messages/<channel>` or a token-protected webhook, become draft requests: rules answer greetings, [System 1](#system-1) suggests the request type and the asset, buttons ask for the rest, and nothing happens until the operator confirms. Replies go to `operator/replies/<channel>`, confirmed requests to `operator/requests/<intent>`, confirmations to `system1/feedback/operator-intake` |
| `system1-drift.json` | Receives the iot stack's Grafana drift alerts for System 1 (a token-protected webhook) and publishes each, firing or resolved, on `system1/drift/<set>`: a prompt to evaluate the set again |

### Credentials and Settings in n8n

The workflows use these credentials, matched by name:

- **`p4n4 MQTT`** (type MQTT): host `p4n4-mqtt` *(service name on p4n4-net)*, port `1883`, and the username and password from your p4n4-iot `.env` if the broker requires them.
- **`p4n4 InfluxDB`** (type Header Auth, used by the Scheduled Digest): name `Authorization`, value `Token <INFLUXDB_TOKEN>` with the token from this stack's `.env`.
- **`p4n4 System 1`**, **`p4n4 Operator Intake`** and **`p4n4 System 1 Alerts`** (type Header Auth, used by Incident Escalation and Operator Intake, and checked by the Operator Intake and System 1 Drift webhooks): name `Authorization`, value `Bearer <SYSTEM1_API_KEY>`, `Bearer <OPERATOR_INTAKE_TOKEN>` and `Bearer <SYSTEM1_ALERT_TOKEN>`. `p4n4 ai system1 enable` creates them, and `p4n4 secret rotate` updates them.

The Scheduled Digest's **Settings** node holds the InfluxDB org and bucket it queries (`ming` and `raw_telemetry`, the platform defaults). If your project uses another `INFLUXDB_ORG`, change it there. The workflows don't read `.env` through `$env`: n8n blocks that by default.

---

## GPU Support

To enable NVIDIA GPU acceleration for Ollama, use the override file:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
# Uncomment the 'ollama' GPU section
docker compose up -d
```

Verify GPU detection:

```bash
docker exec p4n4-ollama nvidia-smi
```

For AMD (ROCm), uncomment the `ollama:rocm` override section instead. The same file has an `ei-runner` GPU section for GPU-enabled `.eim` models. GPU settings stay in the override file, so the stack runs unchanged on a Raspberry Pi 5 or an x86 host without a GPU.

---

## Usage

### Make Commands

```bash
make help             # Show all available commands

make up               # Start the full stack
make down             # Stop all services
make restart          # Restart all services
make logs             # Follow logs from all services
make ps               # Show service status
make status           # Colorized status table
make build            # Rebuild the inference runner image

make start SERVICE=n8n    # Start a single service
make stop SERVICE=letta   # Stop a single service

make models           # List Ollama models
make pull-models      # Pull default models
make test-ollama      # Send a test prompt to Ollama

make deploy-model MODEL=path/to/model.eim   # Deploy a .eim or .onnx model
make test-inference   # Send test sensor data and print the runner's result

make clean            # Stop services and remove all data volumes
```

### Testing Ollama

```bash
# Via make
make test-ollama

# Via curl (from host)
curl http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","prompt":"Hello!","stream":false}'

# From another container on p4n4-net
docker run --rm --network p4n4-net curlimages/curl \
  curl -s http://p4n4-ollama:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","prompt":"Hello!","stream":false}'
```

---

## Default Ports

| Service | Port | URL |
|---------|------|-----|
| Ollama API | `11434` (`OLLAMA_PORT`), on `127.0.0.1` (`OLLAMA_BIND`) | <http://localhost:11434> |
| Letta Server | `8283`, on `127.0.0.1` (`LETTA_BIND`) | <http://localhost:8283> |
| n8n UI | `5678` | <http://localhost:5678> |
| System 1 | None | `http://p4n4-system1:8000` on `p4n4-net` |
| ei-runner health / inference API | `8080`, on `127.0.0.1` (`EI_RUNNER_BIND`) | <http://localhost:8080/health> |

---

## Default Credentials

All credentials are set in `.env`. Defaults from `.env.example`:

| Service | Username | Password |
|---------|----------|----------|
| n8n | *(owner account)* | Created on the first visit to <http://localhost:5678> |
| Letta | *(no username)* | `lettapassword` (`LETTA_SERVER_PASSWORD`) |

**Note:** n8n asks whoever opens it first to create the owner account, so open it and create the account as soon as the stack is up. Change all passwords and the `N8N_ENCRYPTION_KEY` before deploying to production.

---

## Network Requirements

This stack attaches to `p4n4-net` as an **external** network. The network must exist before running `docker compose up`.

**Option 1 — Use p4n4-iot (recommended):**

```bash
# In p4n4-iot directory
docker compose up -d
# Then start p4n4-ai
```

**Option 2 — Create network manually:**

```bash
docker network create p4n4-net
docker compose up -d
```

**Option 3 — Use the CLI** (it creates the network when needed):

```bash
p4n4 up        # start every stack of the project
p4n4 up ai     # start the AI stack only
```

---

## Security Hardening

1. **Change all default credentials** in `.env` before exposing services externally.

2. **Set a strong `N8N_ENCRYPTION_KEY`** — this encrypts stored credentials in n8n. Minimum 32 characters.

3. **Letta API password** — set `LETTA_SERVER_PASSWORD` to a strong value. All API calls require this password as a bearer token.

4. **Restrict port exposure** — Ollama and Letta are published on `127.0.0.1` only (`OLLAMA_BIND`, `LETTA_BIND`). For remote access, use a reverse proxy with TLS rather than binding them to other addresses.

5. **Ollama access** — Ollama has no built-in authentication: anyone who can reach its port can pull, delete and run models. Keep `OLLAMA_BIND=127.0.0.1` unless the network is trusted.

6. **Inference runner** — the `8080` API has no authentication either, so it's published on `127.0.0.1` only (`EI_RUNNER_BIND`). Use a scoped InfluxDB token (write-only to `ai_events`) for it in production, and set `MQTT_USER` / `MQTT_PASSWORD` to match the p4n4-iot broker. `.eim` and `.onnx` files are excluded from version control by `.gitignore`.

---

## Local Overrides

Use `docker-compose.override.yml` for machine-specific settings (GPU, external hostnames, custom volumes):

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
# Edit docker-compose.override.yml as needed
docker compose up -d
```

The override file is listed in `.gitignore` and will never be committed.

---

## Integration with p4n4-iot

When running alongside p4n4-iot on the same `p4n4-net` network, services can be referenced by their container names:

| p4n4-iot Service | Address from p4n4-ai |
|------------------|----------------------|
| MQTT Broker | `p4n4-mqtt:1883` |
| InfluxDB | `p4n4-influxdb:8086` |
| Node-RED | `p4n4-node-red:1880` |

Use these addresses in n8n workflow nodes, Letta agent configurations, and Ollama-powered scripts.

**Shared secrets** (must match between stacks — set identical values in both `.env` files):

| Variable | Purpose |
|----------|---------|
| `INFLUXDB_TOKEN` | InfluxDB API token |
| `INFLUXDB_ORG` | InfluxDB organization |
| `INFLUXDB_BUCKET` | Primary InfluxDB bucket |
| `INFLUXDB_BUCKET_AI_EVENTS` | Bucket the inference runner writes to (`ai_events`) |
| `MQTT_USER` / `MQTT_PASSWORD` | MQTT authentication (inference runner) |

**Node-RED integration:** p4n4-iot's flows subscribe to `inference/+/result` and store each result in the `raw_telemetry` bucket (`inference` measurement). Route high-anomaly events (`anomaly_score > 0.8`) from there to Ollama for natural-language explanations.

---

## Migrating from p4n4-edge

The inference runner, its models directories and its settings are the same as in p4n4-edge; only the stack they live in changed. The container keeps its name (`p4n4-ei-runner`), its port (`8080`) and its MQTT topics.

- **p4n4 projects:** `p4n4 migrate edge` moves the project's `edge/` layer into `ai/` (runner, models, `.env` values, the `ei-runner` service and profile) and drops `edge` from `.p4n4.json`. Until then the `edge` layer keeps working, with a warning.
- **By hand:** stop the edge stack (`docker compose down` in it), copy `runner/`, `edge-impulse/` and `onnx/` into this stack, copy the runner variables from the edge `.env` into this `.env` (the [Edge inference runner section](.env.example) lists them), add `ei-runner` to `COMPOSE_PROFILES` and run `docker compose up -d`.

The runner's `ei-runner-data` volume now belongs to this Compose project; the runner keeps nothing in it, so nothing needs copying.

---

## Resources

- [p4n4 Platform](https://github.com/raisga/p4n4) — umbrella repo and architecture docs
- [p4n4-iot](https://github.com/raisga/p4n4-iot) — IoT stack (MING)
- [p4n4-api](https://github.com/raisga/p4n4-api) — Python (FastAPI) REST API gateway (proxies Ollama and Letta behind JWT auth)
- [p4n4-extras](https://github.com/raisga/p4n4-extras) — optional services outside the core platform
- [Ollama Documentation](https://ollama.com/library) — available models and API reference
- [Letta Documentation](https://docs.letta.com/) — agent framework docs
- [n8n Documentation](https://docs.n8n.io/) — workflow automation docs
- [Edge Impulse Studio](https://studio.edgeimpulse.com) — train and export models; [Linux SDK](https://docs.edgeimpulse.com/docs/run-inference/linux)
- [ONNX Runtime](https://onnxruntime.ai/) — cross-platform inference engine

---

## License

This project is licensed under the [MIT License](LICENSE).