# p4n4 System 1: laya-serve behind system1_app.py (CPU, non-root, offline at run time).
# python:3.12-slim, pinned by its multi-arch index digest
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG TARGETARCH
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    USE_TF=0 HF_HOME=/models HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1
COPY requirements-amd64.txt requirements-arm64.txt /tmp/
# One hashed lock per architecture; TARGETARCH is unset outside BuildKit, so fall back to dpkg's
RUN arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
 && pip install --require-hashes --no-deps -r "/tmp/requirements-${arch}.txt" \
 && rm /tmp/requirements-*.txt
# pull and serve must run as the same user: huggingface_hub writes its offline index with mode 0600
RUN groupadd --system --gid 10001 system1 \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin system1 \
 && mkdir -p /models /config/questions && chown 10001:10001 /models
COPY system1_app.py pins.json /app/
USER 10001:10001
EXPOSE 8000
CMD ["python", "/app/system1_app.py"]
