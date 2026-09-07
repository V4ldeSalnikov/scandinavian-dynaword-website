FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/dynaword \
    ALLOWED_ORIGINS=https://v4ldesalnikov.github.io
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN python -m pip install --no-cache-dir -r server/requirements.txt \
    && useradd --create-home --uid 1000 dynaword \
    && mkdir -p /app/.cache && chown dynaword:dynaword /app/.cache

COPY scripts/restore_runtime.py /app/scripts/restore_runtime.py
COPY runtime-source.json /app/runtime-source.json
USER dynaword
# Bake the verified snapshot into one image layer. Waking the Space does not
# rerun preparation or fetch all individual artifacts into temporary storage.
RUN python scripts/restore_runtime.py --source runtime-source.json --destination .cache

COPY --chown=dynaword:dynaword server /app/server
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
