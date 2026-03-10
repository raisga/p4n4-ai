# ==============================================================================
# GenAI Stack Makefile
# ==============================================================================

.PHONY: help up down restart logs ps clean pull status interactive start stop \
        models pull-models test-ollama

# Colors
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
BOLD   := \033[1m
DIM    := \033[2m
NC     := \033[0m

# Service list
AI_SERVICES := ollama letta n8n

# Default target
help:
	@echo ""
	@printf "$(BOLD)$(CYAN)  GenAI Stack$(NC) - Available Commands\n"
	@echo "  ════════════════════════════════════════════"
	@echo ""
	@printf "  $(BOLD)Core:$(NC)\n"
	@printf "    $(GREEN)make up$(NC)              Start all services\n"
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
	docker compose down

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
		docker compose down -v; \
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
	@for svc in ollama letta n8n; do \
		container="p4n4-$$svc"; \
		state=$$(docker inspect --format='{{.State.Status}}' $$container 2>/dev/null || echo "stopped"); \
		case $$svc in \
			ollama)  port="11434"; url="http://localhost:11434" ;; \
			letta)   port="8283";  url="http://localhost:8283" ;; \
			n8n)     port="5678";  url="http://localhost:5678" ;; \
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

# Reverse deps (what breaks)
rdeps_ollama :=
rdeps_letta :=
rdeps_n8n :=

start:
ifndef SERVICE
	@printf "$(RED)  Usage: make start SERVICE=<name>$(NC)\n"
	@printf "  Available: $(BOLD)ollama letta n8n$(NC)\n"
	@exit 1
endif
	@deps="$(deps_$(SERVICE))"; \
	if [ -n "$$deps" ]; then \
		printf "$(YELLOW)  Auto-starting dependencies: $(BOLD)$$deps$(NC)\n"; \
		docker compose up -d $$deps; \
	fi
	@printf "$(GREEN)  Starting $(BOLD)$(SERVICE)$(NC)$(GREEN)...$(NC)\n"
	@docker compose up -d $(SERVICE)
	@printf "$(GREEN)$(BOLD)  Done!$(NC)\n"

stop:
ifndef SERVICE
	@printf "$(RED)  Usage: make stop SERVICE=<name>$(NC)\n"
	@printf "  Available: $(BOLD)ollama letta n8n$(NC)\n"
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
