FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY README.md /app/README.md
COPY backend /app/backend
COPY docs /app/docs
COPY scripts /app/scripts

RUN python -m pip install --upgrade pip \
    && python -m pip install ./backend

EXPOSE 8018

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8018"]
