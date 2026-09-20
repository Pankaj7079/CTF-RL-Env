# Pinned base for a deterministic build.
FROM python:3.12.8-slim AS runtime

# System hardening / smaller image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AR_DATABASE_URL=sqlite+aiosqlite:////data/artifact_relay.db

WORKDIR /app

# Pinned uv for reproducible dependency resolution.
RUN pip install --no-cache-dir uv==0.10.0

# Install third-party dependencies first (cached layer), without the project.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application, then install the project itself.
COPY app ./app
COPY grader ./grader
COPY solver ./solver
COPY agents ./agents
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# Writable state dir for the SQLite file.
RUN mkdir -p /data

EXPOSE 8000

# Single documented start command.
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
