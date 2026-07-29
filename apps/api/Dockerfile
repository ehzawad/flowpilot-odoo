FROM ghcr.io/astral-sh/uv:0.11.29-python3.13-bookworm-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --no-group dev --no-install-project && uv sync --no-group dev
RUN useradd --create-home --uid 10001 flowpilot && chown -R flowpilot:flowpilot /app
USER flowpilot
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "flowpilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
