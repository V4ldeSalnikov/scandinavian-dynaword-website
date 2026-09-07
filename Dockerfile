FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN python -m pip install --no-cache-dir -r server/requirements.txt \
    && useradd --create-home --uid 10001 dynaword

COPY --chown=dynaword:dynaword server /app/server
RUN mkdir -p /app/.cache/texts && chown -R dynaword:dynaword /app/.cache

USER dynaword
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import json,urllib.request; r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=5)); assert r['status']=='ready' and r['text_search']['status']=='ready'"

# One worker shares the memory-mapped corpus vectors and bounded query caches.
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
