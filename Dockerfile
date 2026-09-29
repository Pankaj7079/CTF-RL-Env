# The image holds only the challenge service and its grader. The solver, the
# agents and the tests stay out, so nothing in the container helps a solve.
FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    AR_DATABASE_URL=sqlite+aiosqlite:////data/artifact_relay.db

WORKDIR /app

RUN pip install --no-cache-dir uv==0.10.0

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY grader ./grader

RUN useradd --system --no-create-home relay \
    && mkdir /data \
    && chown relay /data
USER relay

EXPOSE 8000

# uvicorn puts the working directory on sys.path, so the packages import in place.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
