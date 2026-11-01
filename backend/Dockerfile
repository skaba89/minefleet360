FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN pip install pip==26.2 && useradd --create-home --uid 10001 mf
COPY pyproject.toml ./
COPY app/__init__.py app/__init__.py

FROM base AS dev
RUN pip install -e ".[dev]"
USER mf

FROM base AS runtime
COPY . .
RUN pip install . && mkdir -p /data/mail && chown -R mf:mf /app /data
USER mf
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
