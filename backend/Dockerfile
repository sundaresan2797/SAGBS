FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Must match UPLOAD_DIR in backend/.env (loaded via env_file in docker-compose.yml) and the volume
# mount below it in docker-compose.yml - a mismatch here means uploaded files land somewhere that
# isn't the persisted volume, and silently vanish on the next container restart or rebuild.
RUN mkdir -p /app/uploads_live

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
