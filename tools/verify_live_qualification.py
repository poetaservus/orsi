"""Read-only verification of revision-bound evidence before any later promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.infrastructure import qualification as q


def verify(root: Path, report_path: Path) -> list[str]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        profiles = q.required_profiles(root)
        errors = q.qualification_errors(report, q.identity(root), profiles)
        if errors:
            return errors
        from app.settings.local_models import LocalModelCatalog
        from app.settings.model import load_model_config
        catalog = LocalModelCatalog(root / "models", root / "config/model.json", load_model_config())
        if {m.id for m in catalog.models} != {p["model_id"] for p in profiles}:
            errors.append("Every available local chooser model needs a versioned qualified profile.")
        for profile in profiles:
            model = next(m for m in catalog.models if m.id == profile["model_id"])
            if catalog.identity(model)["sha256"] != profile["sha256"]:
                errors.append("Installed model bytes changed after qualification.")
        return errors
    except Exception as exc:
        return [f"Qualification evidence could not be verified ({type(exc).__name__})."]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    errors = verify(Path.cwd(), args.report)
    if errors:
        print("Qualification blocked:")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    print("Exact-revision live qualification verified. No branch or build was changed.")


if __name__ == "__main__":
    main()
