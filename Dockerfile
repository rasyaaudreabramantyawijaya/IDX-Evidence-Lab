FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=src \
    IDXEL_HOST=0.0.0.0 \
    IDXEL_PORT=5500

WORKDIR /app

COPY requirements-portfolio.txt .
# pytest is a test-only dependency listed in the same file; the runtime image does not need it.
RUN grep -viE '^pytest' requirements-portfolio.txt > requirements-runtime.txt \
    && pip install --no-cache-dir -r requirements-runtime.txt

RUN useradd --system --uid 10001 --no-create-home app

COPY src ./src
COPY configs ./configs
COPY reports ./reports
COPY docs/prototypes ./docs/prototypes
# Market snapshots (data/) are mounted at runtime, see docker-compose.yml.

# The factor-zoo endpoint refreshes a JSON artifact under docs/prototypes at runtime.
RUN chown -R app:app /app/docs/prototypes
USER app

EXPOSE 5500
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5500/api/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "idx_evidence_lab.web_app"]
