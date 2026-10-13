# p4n4-ai

> Dockerized **GenAI stack** — local LLM inference, stateful AI agents, and workflow automation.

The GenAI stack (Ollama · Letta · n8n) brings local AI capabilities to your IoT deployment. Ollama runs open-weight LLMs entirely on-device, Letta provides persistent AI agents with long-term memory, and n8n wires everything together with event-driven workflows.

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
- [Resources](#resources)
- [License](#license)

---

## Architecture

```
  [p4n4-iot / MQTT / InfluxDB]
           │
           │  (shared p4n4-net bridge)
           ▼
        [n8n]           ← event-driven workflow automation
       /     \
      ▼       ▼
  [Ollama]  [Letta]     ← local LLM runtime + stateful AI agents
```

**Data flow:** n8n subscribes to MQTT topics (via p4n4-net) and triggers AI workflows. Ollama serves local LLM inference, Letta manages persistent AI agents with memory, and n8n routes results back to MQTT, InfluxDB, or external webhooks.

---

## Stack Components

| Service | Role | Description |
|---------|------|-------------|
| **[Ollama](https://ollama.com/)** | Local LLM Runtime | Runs open-weight models (Llama, Mistral, Phi, etc.) entirely on-device with zero data egress. Exposes an OpenAI-compatible REST API on port 11434. |
| **[Letta](https://letta.com/)** *(optional)* | AI Agent Framework | Stateful AI agent framework with persistent memory (formerly MemGPT). Build agents that remember context across sessions and reason over long-term IoT event histories. |
| **System 1** *(optional)* | Fast Typed Decisions | [laya](https://huggingface.co/convaiinnovations/laya), a small encoder that picks one option from a closed menu in a fraction of a second on the CPU. Advisory routing for n8n and Node-RED: rules decide, System 1 routes, the LLM explains. No host port. See [System 1](#system-1). |
| **[n8n](https://n8n.io/)** *(optional)* | Workflow Automation | Low-code, node-based workflow engine. Connects MQTT, InfluxDB, Ollama, Letta, and external APIs without custom glue code. Includes four starter IoT + AI workflows. |

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (v2.0+)
- At least **8 GB RAM** available to Docker (16 GB recommended for larger models)
- `p4n4-iot` running (or `p4n4-net` network created manually — see [Network Requirements](#network-requirements))
- *(Optional)* NVIDIA GPU with drivers + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU acceleration

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

   Letta and n8n only run when enabled; see [Choosing Services](#choosing-services).

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

For AMD (ROCm), uncomment the `ollama:rocm` override section instead.

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

make start SERVICE=n8n    # Start a single service
make stop SERVICE=letta   # Stop a single service

make models           # List Ollama models
make pull-models      # Pull default models
make test-ollama      # Send a test prompt to Ollama

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

**Option 3 — Use the CLI:**

```bash
p4n4 up        # start IoT stack
p4n4 up --ai   # start AI stack
```

---

## Security Hardening

1. **Change all default credentials** in `.env` before exposing services externally.

2. **Set a strong `N8N_ENCRYPTION_KEY`** — this encrypts stored credentials in n8n. Minimum 32 characters.

3. **Letta API password** — set `LETTA_SERVER_PASSWORD` to a strong value. All API calls require this password as a bearer token.

4. **Restrict port exposure** — Ollama and Letta are published on `127.0.0.1` only (`OLLAMA_BIND`, `LETTA_BIND`). For remote access, use a reverse proxy with TLS rather than binding them to other addresses.

5. **Ollama access** — Ollama has no built-in authentication: anyone who can reach its port can pull, delete and run models. Keep `OLLAMA_BIND=127.0.0.1` unless the network is trusted.

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

---

## Resources

- [p4n4 Platform](https://github.com/raisga/p4n4) — umbrella repo and architecture docs
- [p4n4-iot](https://github.com/raisga/p4n4-iot) — IoT stack (MING)
- [p4n4-api](https://github.com/raisga/p4n4-api) — Rust REST API gateway (proxies Ollama and Letta behind JWT auth)
- [Ollama Documentation](https://ollama.com/library) — available models and API reference
- [Letta Documentation](https://docs.letta.com/) — agent framework docs
- [n8n Documentation](https://docs.n8n.io/) — workflow automation docs

---

## License

This project is licensed under the [MIT License](LICENSE).