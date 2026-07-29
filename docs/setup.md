# Local setup

## Fastest path: Docker Compose

Requirements: Docker with Compose v2 and at least 4 GB free memory.

```zsh
cp .env.example .env
docker compose up --build
```

Open the console at `http://localhost:3000`, API docs at `http://localhost:8000/docs`, Odoo MCP at
`http://localhost:8010/mcp`, and the supplier simulator at `http://localhost:8020/mcp`.

The default configuration uses the deterministic agent and fake Odoo boundary. It does not require an
OpenAI or Odoo key.

## Native Python development

Requirements: Python 3.12–3.14 and `uv`.

```zsh
cp .env.example .env
# For native mode, replace the Compose database URL:
perl -0pi -e 's#postgresql\+psycopg://flowpilot:flowpilot@product-db:5432/flowpilot#sqlite:///./.data/flowpilot.db#g' .env
uv sync --all-groups
uv run alembic upgrade head
uv run flowpilot-seed
```

Run the processes in separate terminals:

```zsh
uv run flowpilot-api
uv run flowpilot-worker
cd apps/web && npm install && npm run dev
```

## Verification loop

```zsh
uv run pytest -m 'not integration'
uv run flowpilot-smoke
uv run python evals/run_local.py
uv run python scripts/validate_repo.py
python -m compileall -q src migrations evals scripts
```

## Enabling OpenAI

After the zero-key path works, set `AGENT_RUNTIME=openai` and configure `OPENAI_API_KEY`. Keep the
secret server-side. The live runtime can use read-only MCP servers, persistent tenant memory,
compaction, tracing, structured output, and severity-based routing.

## Enabling real Odoo

Set `ODOO_MODE=json2`, the URL/database/key, and install the optional `flowpilot_bridge` addon for
approved writes and durable webhooks. Start read-only. Do not enable write permissions until the bot
user, action allowlist, payload validation, and recovery plan have been reviewed.
