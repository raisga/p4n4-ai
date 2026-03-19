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
- [Project Structure](#project-structure)
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
| **[Letta](https://letta.com/)** | AI Agent Framework | Stateful AI agent framework with persistent memory (formerly MemGPT). Build agents that remember context across sessions and reason over long-term IoT event histories. |
| **[n8n](https://n8n.io/)** | Workflow Automation | Low-code, node-based workflow engine. Connects MQTT, InfluxDB, Ollama, Letta, and external APIs without custom glue code. Includes four starter IoT + AI workflows. |

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
│   └── n8n/
│       └── workflows/
│           ├── alert-enrichment.json   # Enrich MQTT alerts with LLM analysis
│           ├── scheduled-digest.json   # Hourly telemetry summary via Ollama
│           ├── device-onboarding.json  # Auto-register new MQTT devices
│           └── incident-escalation.json # Classify and escalate critical alerts
└── scripts/
    ├── pull-models.sh                  # Helper to pull models into Ollama
    ├── selector.sh                     # Interactive service selector
    └── check_env_example.py            # CI: .env.example completeness check
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
| `llama3.2:70b` | 40 GB | High-quality reasoning (requires GPU) |

### Listing Installed Models

```bash
make models
# or
docker exec p4n4-ollama ollama list
```

---

## n8n Workflows

Four starter workflows are included in `n8n/workflows/`. Import them via the n8n UI:

1. Open n8n at <http://localhost:5678>
2. Go to **Workflows → Import from File**
3. Select the JSON file from `config/n8n/workflows/`

| Workflow | Description |
|----------|-------------|
| `alert-enrichment.json` | Subscribes to `inference/results` MQTT topic; sends low-confidence results to Ollama for analysis |
| `scheduled-digest.json` | Runs hourly; queries InfluxDB for recent telemetry and generates a natural-language summary via Ollama |
| `device-onboarding.json` | Listens on `devices/+/register`; auto-registers new devices and publishes a confirmation to MQTT |
| `incident-escalation.json` | Listens on `alerts/+/critical`; classifies severity via Ollama and publishes enriched alert to `alerts/escalated` |

### MQTT Credential Setup in n8n

After importing workflows, configure an MQTT credential named **`p4n4 MQTT`**:

- Host: `p4n4-mqtt` *(service name on p4n4-net)*
- Port: `1883`
- Username/Password: match values in your p4n4-iot `.env`

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
| Ollama API | `11434` | <http://localhost:11434> |
| Letta Server | `8283` | <http://localhost:8283> |
| n8n UI | `5678` | <http://localhost:5678> |

---

## Default Credentials

All credentials are set in `.env`. Defaults from `.env.example`:

| Service | Username | Password |
|---------|----------|----------|
| n8n | `admin` | `adminpassword` |
| Letta | *(no username)* | `lettapassword` |

**Note:** Change all passwords and the `N8N_ENCRYPTION_KEY` before deploying to production.

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

4. **Restrict port exposure** — for production, remove host-port bindings from `docker-compose.yml` and access services only via `p4n4-net` or a reverse proxy.

5. **Ollama access** — Ollama has no built-in authentication. Restrict access at the network or reverse-proxy level for production deployments.

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