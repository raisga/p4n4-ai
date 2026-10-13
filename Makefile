# ==============================================================================
# GenAI Stack Makefile
# ==============================================================================

.PHONY: help up down restart logs ps clean pull status interactive start stop \
        models pull-models test-ollama system1-pull system1-build system1-lock system1-test \
        system1-train

# Colors
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
BOLD   := \033[1m
DIM    := \033[2m
NC     := \033[0m

# Service list
AI_SERVICES := ollama letta n8n system1

# Each service is in a Compose profile of the same name. Started when neither
# the environment nor .env sets COMPOSE_PROFILES:
DEFAULT_PROFILES := ollama
ifeq ($(origin COMPOSE_PROFILES)$(shell grep -s '^COMPOSE_PROFILES=' .env),undefined)
export COMPOSE_PROFILES := $(DEFAULT_PROFILES)
endif

# down/clean also stop services started outside COMPOSE_PROFILES (make start)
ALL_PROFILES := --profile '*'

# Default target
help:
	@echo ""
	@printf "$(BOLD)$(CYAN)  GenAI Stack$(NC) - Available Commands\n"
	@echo "  ════════════════════════════════════════════"
	@echo ""
	@printf "  $(BOLD)Core:$(NC)\n"
	@printf "    $(GREEN)make up$(NC)              Start the services in COMPOSE_PROFILES\n"
	@printf "    $(GREEN)make down$(NC)            Stop all services\n"
	@printf "    $(GREEN)make restart$(NC)         Restart all services\n"
	@printf "    $(GREEN)make status$(NC)          Show service status table\n"
	@printf "    $(GREEN)make logs$(NC)            Follow logs for all services\n"
	@printf "    $(GREEN)make ps$(NC)              Docker compose ps\n"
	@printf "    $(GREEN)make pull$(NC)            Pull latest images\n"
	@printf "    $(GREEN)make clean$(NC)           Stop and remove volumes\n"
	@echo ""
	@printf "  $(BOLD)Modular:$(NC)\n"
	@printf "    $(GREEN)make interactive$(NC)     Interactive service selector\n"
	@printf "    $(GREEN)make start SERVICE=x$(NC) Start a service + its deps\n"
	@printf "    $(GREEN)make stop SERVICE=x$(NC)  Stop a service (warns about deps)\n"
	@echo ""
	@printf "  $(BOLD)Ollama:$(NC)\n"
	@printf "    $(GREEN)make models$(NC)          List downloaded models\n"
	@printf "    $(GREEN)make pull-models$(NC)     Pull default models (llama3.2)\n"
	@echo ""
	@printf "  $(BOLD)System 1 (laya):$(NC)\n"
	@printf "    $(GREEN)make system1-pull$(NC)    Download the pinned checkpoint\n"
	@printf "    $(GREEN)make system1-build$(NC)   Build the image locally (p4n4-system1:dev)\n"
	@printf "    $(GREEN)make system1-lock$(NC)    Recompile the hashed dependency locks\n"
	@printf "    $(GREEN)make system1-test$(NC)    Run the regression suite against the image\n"
	@printf "    $(GREEN)make system1-train$(NC)   Fine-tune the checkpoint off the device (S4)\n"
	@echo ""
	@printf "  $(BOLD)Testing:$(NC)\n"
	@printf "    $(GREEN)make test-ollama$(NC)     Send a test prompt to Ollama\n"
	@echo ""

# ------------------------------------------------------------------------------
# Core Commands
# ------------------------------------------------------------------------------

up:
	@echo "Starting GenAI stack..."
	@echo ""
	@printf "$(YELLOW)  NOTE: p4n4-net must exist. Start p4n4-iot first, or run:$(NC)\n"
	@printf "$(YELLOW)        docker network create p4n4-net$(NC)\n"
	@echo ""
	docker compose up -d
	@echo ""
	@echo "Services started! Access them at:"
	@printf "  $(CYAN)n8n$(NC):    http://localhost:5678\n"
	@printf "  $(CYAN)Letta$(NC):  http://localhost:8283\n"
	@printf "  $(CYAN)Ollama$(NC): http://localhost:11434\n"
	@echo ""

down:
	@echo "Stopping GenAI stack..."
	docker compose $(ALL_PROFILES) down

restart:
	@echo "Restarting GenAI stack..."
	docker compose restart

logs:
	docker compose logs -f

ps:
	docker compose ps

pull:
	@echo "Pulling latest images..."
	docker compose pull

clean:
	@printf "$(RED)$(BOLD)  WARNING: This will DELETE ALL DATA (Ollama models, Letta agents, n8n workflows)$(NC)\n"
	@read -p "  Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "Stopping services and removing volumes..."; \
		docker compose $(ALL_PROFILES) down -v; \
		echo "Cleaned up!"; \
	else \
		echo "Cancelled."; \
	fi

# ------------------------------------------------------------------------------
# Status (colorized service table)
# ------------------------------------------------------------------------------

status:
	@echo ""
	@printf "$(BOLD)$(CYAN)  GenAI Stack - Service Status$(NC)\n"
	@echo "  ════════════════════════════════════════════════════════════════════"
	@printf "  $(BOLD)%-14s %-12s %-8s %s$(NC)\n" "SERVICE" "STATUS" "PORT" "URL"
	@printf "  $(DIM)%-14s %-12s %-8s %s$(NC)\n" "─────────────" "──────────" "──────" "───────────────────────────"
	@for svc in ollama letta n8n system1; do \
		container="p4n4-$$svc"; \
		state=$$(docker inspect --format='{{.State.Status}}' $$container 2>/dev/null || echo "stopped"); \
		case $$svc in \
			ollama)  port="11434"; url="http://localhost:11434" ;; \
			letta)   port="8283";  url="http://localhost:8283" ;; \
			n8n)     port="5678";  url="http://localhost:5678" ;; \
			system1) port="-";     url="p4n4-system1:8000 (p4n4-net only)" ;; \
		esac; \
		if [ "$$state" = "running" ]; then \
			printf "  $(BOLD)%-14s$(NC) $(GREEN)%-12s$(NC) %-8s %s\n" "$$svc" "running" "$$port" "$$url"; \
		else \
			printf "  $(BOLD)%-14s$(NC) $(RED)%-12s$(NC) %-8s $(DIM)%s$(NC)\n" "$$svc" "$$state" "$$port" "-"; \
		fi; \
	done
	@echo ""

# ------------------------------------------------------------------------------
# Interactive Service Selector
# ------------------------------------------------------------------------------

interactive:
	@bash scripts/selector.sh

# ------------------------------------------------------------------------------
# Granular Start/Stop with Dependency Awareness
# ------------------------------------------------------------------------------

# Dependency map
deps_ollama :=
deps_letta :=
deps_n8n :=
deps_system1 :=

# Reverse deps (what breaks)
rdeps_ollama :=
rdeps_letta :=
rdeps_n8n :=
rdeps_system1 :=

start:
ifndef SERVICE
	@printf "$(RED)  Usage: make start SERVICE=<name>$(NC)\n"
	@printf "  Available: $(BOLD)ollama letta n8n system1$(NC)\n"
	@exit 1
endif
	@deps="$(deps_$(SERVICE))"; \
	if [ -n "$$deps" ]; then \
		printf "$(YELLOW)  Auto-starting dependencies: $(BOLD)$$deps$(NC)\n"; \
		docker compose $(foreach d,$(deps_$(SERVICE)),--profile $(d)) up -d $$deps; \
	fi
	@printf "$(GREEN)  Starting $(BOLD)$(SERVICE)$(NC)$(GREEN)...$(NC)\n"
	@docker compose $(foreach d,$(deps_$(SERVICE)) $(SERVICE),--profile $(d)) up -d $(SERVICE)
	@printf "$(GREEN)$(BOLD)  Done!$(NC)\n"

stop:
ifndef SERVICE
	@printf "$(RED)  Usage: make stop SERVICE=<name>$(NC)\n"
	@printf "  Available: $(BOLD)ollama letta n8n system1$(NC)\n"
	@exit 1
endif
	@rdeps="$(rdeps_$(SERVICE))"; \
	if [ -n "$$rdeps" ]; then \
		for dep in $$rdeps; do \
			state=$$(docker inspect --format='{{.State.Status}}' "p4n4-$$dep" 2>/dev/null || echo "stopped"); \
			if [ "$$state" = "running" ]; then \
				printf "$(RED)  WARNING: Stopping '$(SERVICE)' will affect running service: $(BOLD)$$dep$(NC)\n"; \
			fi; \
		done; \
	fi
	@printf "$(YELLOW)  Stopping $(BOLD)$(SERVICE)$(NC)$(YELLOW)...$(NC)\n"
	@docker compose stop $(SERVICE)
	@printf "$(GREEN)$(BOLD)  Done!$(NC)\n"

# ------------------------------------------------------------------------------
# Ollama Model Management
# ------------------------------------------------------------------------------

models:
	@printf "$(BOLD)$(CYAN)  Ollama Models$(NC)\n"
	@docker exec p4n4-ollama ollama list 2>/dev/null \
		|| printf "$(RED)  Ollama is not running. Start with: make up$(NC)\n"

pull-models:
	@bash scripts/pull-models.sh

# ------------------------------------------------------------------------------
# Testing Commands
# ------------------------------------------------------------------------------

test-ollama:
	@printf "$(CYAN)  Sending test prompt to Ollama...$(NC)\n"
	@docker run --rm --network p4n4-net curlimages/curl:latest \
		curl -sf http://p4n4-ollama:11434/api/generate \
		-H "Content-Type: application/json" \
		-d '{"model":"llama3.2","prompt":"Reply with one word: healthy","stream":false}' \
		| python3 -c "import sys,json; d=json.load(sys.stdin); print('  Response:', d.get('response','').strip())" \
		2>/dev/null || printf "$(RED)  Ollama is not running or no models loaded. Run: make pull-models$(NC)\n"

# ------------------------------------------------------------------------------
# System 1 (laya)
# ------------------------------------------------------------------------------

SYSTEM1_DEV_IMAGE ?= p4n4-system1:dev
SYSTEM1_TEST_MODELS ?= system1-test-models
SYSTEM1_TRAIN_OUT ?= system1/train/out
SYSTEM1_TRAIN_BASE := /models/hub/models--convaiinnovations--laya/snapshots/$$(grep -m1 '^SYSTEM1_REVISION=' .env.example | cut -d= -f2)/multilingual
SYSTEM1_LOCK_FLAGS := -c constraints.txt --generate-hashes --python-version 3.12 \
	--index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu \
	--index-strategy unsafe-best-match --no-header --emit-index-url

system1-pull:
	docker compose run --rm system1-pull

system1-build:
	docker build -t $(SYSTEM1_DEV_IMAGE) system1

# Needs uv. Read the laya diff before bumping it (docs: decisions/system1.md, rule 13)
system1-lock:
	cd system1 && uv pip compile requirements.in $(SYSTEM1_LOCK_FLAGS) \
		--python-platform x86_64-manylinux_2_28 -o requirements-amd64.txt
	cd system1 && uv pip compile requirements.in $(SYSTEM1_LOCK_FLAGS) \
		--python-platform aarch64-manylinux_2_28 -o requirements-arm64.txt

# Fills a test volume as the service user, then runs the suite (needs pytest; with
# p4n4-lib installed it also checks every shipped set against its gates)
system1-test:
	docker volume create $(SYSTEM1_TEST_MODELS) >/dev/null
	docker run --rm --user 10001:10001 -e HF_HUB_OFFLINE=0 \
		-e SYSTEM1_REVISION=$$(grep -m1 '^SYSTEM1_REVISION=' .env.example | cut -d= -f2) \
		-v $(SYSTEM1_TEST_MODELS):/models $(SYSTEM1_DEV_IMAGE) python /app/system1_app.py pull
	SYSTEM1_TEST_IMAGE=$(SYSTEM1_DEV_IMAGE) SYSTEM1_TEST_MODELS=$(SYSTEM1_TEST_MODELS) \
		python3 -m pytest -q system1/tests

# Off the device only: a workstation or a GPU runner (~2 h on 8 CPU cores, 11 GiB). Writes
# the corpus and the repository to publish to $(SYSTEM1_TRAIN_OUT); then compare.py, card.py,
# pin.py (docs: decisions/system1.md §17)
system1-train:
	mkdir -p $(SYSTEM1_TRAIN_OUT)
	python3 system1/train/corpus.py $(SYSTEM1_TRAIN_OUT)/corpus.jsonl
	docker volume create $(SYSTEM1_TEST_MODELS) >/dev/null
	docker run --rm --user 10001:10001 -e HF_HUB_OFFLINE=0 \
		-e SYSTEM1_REVISION=$$(grep -m1 '^SYSTEM1_REVISION=' .env.example | cut -d= -f2) \
		-v $(SYSTEM1_TEST_MODELS):/models $(SYSTEM1_DEV_IMAGE) python /app/system1_app.py pull
	docker run --rm --user $$(id -u):$$(id -g) --memory 11g -e HF_HUB_OFFLINE=1 \
		-v $(SYSTEM1_TEST_MODELS):/models:ro -v $(CURDIR)/system1:/src:ro \
		-v $(abspath $(SYSTEM1_TRAIN_OUT)):/out $(SYSTEM1_DEV_IMAGE) \
		python /src/train/train.py /out/corpus.jsonl /out/checkpoint --base $(SYSTEM1_TRAIN_BASE)
