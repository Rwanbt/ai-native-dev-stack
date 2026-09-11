"""Record provider/model observability without reading credentials or invoking a model."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path


PROVIDER_VARIABLES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "GOOGLE_API_KEY", "OLLAMA_HOST", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL")


@dataclass(frozen=True)
class ModelEgressReport:
    schema_version: int
    recorded_at: str
    provider_surfaces_present: tuple[str, ...]
    effective_provider_observation: str
    effective_model_observation: str
    session_containment: str
    sensitive_model_available: bool
    reason: str


def inspect(environment: dict[str, str] | None = None) -> ModelEgressReport:
    environment = os.environ if environment is None else environment
    surfaces = tuple(name for name in PROVIDER_VARIABLES if environment.get(name))
    return ModelEgressReport(1, datetime.now(timezone.utc).isoformat(timespec="seconds"), surfaces, "none", "none", "UNKNOWN", False, "no qualified pre-exposure provider/model observer or containment evidence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(asdict(inspect()), sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
