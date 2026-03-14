FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY replayos /app/replayos
COPY web /app/web
COPY config /app/config
COPY plugins /app/plugins

RUN pip install --no-cache-dir .

RUN adduser --disabled-password --gecos "" replayos
USER replayos

EXPOSE 8787

CMD ["python", "-m", "replayos.cli", "--config", "config/replayos.toml", "--env", ".env", "run"]
