from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "pyproject.toml",
    "compose.yaml",
    ".env.example",
    "src/flowpilot/api/main.py",
    "src/flowpilot/worker/main.py",
    "src/flowpilot/agent/openai_runtime.py",
    "src/flowpilot/odoo_mcp/server.py",
    "apps/web/package.json",
    "apps/web/app/page.tsx",
    "migrations/versions/20260729_0001_initial.py",
    "infra/k8s/base/kustomization.yaml",
    "infra/terraform/aws/main.tf",
    "evals/cases.jsonl",
]
FORBIDDEN_PARTS = {".env", ".venv", "node_modules", "__pycache__", ".bootstrap"}


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"Missing required repository files: {', '.join(missing)}")
    leaked = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            if relative.as_posix() == ".env.example":
                continue
            leaked.append(relative.as_posix())
    if leaked:
        raise SystemExit(f"Generated or secret paths present: {', '.join(leaked[:20])}")
    print(f"Repository invariants passed ({len(REQUIRED)} required files).")


if __name__ == "__main__":
    main()
