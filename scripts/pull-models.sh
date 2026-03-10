#!/usr/bin/env bash
# ==============================================================================
# Ollama Model Puller
# ==============================================================================
# Pull one or more models into the running Ollama container.
#
# Usage:
#   ./scripts/pull-models.sh                  # pull default model (llama3.2)
#   ./scripts/pull-models.sh llama3.2 nomic-embed-text
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CONTAINER="p4n4-ollama"
DEFAULT_MODELS=("llama3.2")

# Check container is running
if ! docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null | grep -q "running"; then
  printf "${RED}  Error: %s is not running. Start with: make up${NC}\n" "$CONTAINER"
  exit 1
fi

# Determine models to pull
if [ $# -gt 0 ]; then
  models=("$@")
else
  printf "${YELLOW}  No model specified — pulling default models: %s${NC}\n" \
    "${DEFAULT_MODELS[*]}"
  models=("${DEFAULT_MODELS[@]}")
fi

echo ""
printf "${BOLD}${CYAN}  Pulling Ollama models${NC}\n"
echo "  ════════════════════════════════════════════"
echo ""

for model in "${models[@]}"; do
  printf "  ${CYAN}Pulling:${NC} ${BOLD}%s${NC}\n" "$model"
  if docker exec "$CONTAINER" ollama pull "$model"; then
    printf "  ${GREEN}Done:${NC} ${BOLD}%s${NC}\n\n" "$model"
  else
    printf "  ${RED}Failed:${NC} %s\n\n" "$model"
  fi
done

echo ""
printf "${BOLD}  Available models:${NC}\n"
docker exec "$CONTAINER" ollama list
echo ""
