# GoalCert backend (FastAPI + engine)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "pydantic-settings>=2.6" \
    "sqlalchemy>=2.0" "psycopg[binary]>=3.2" "websockets>=13" "python-multipart>=0.0.12"

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
