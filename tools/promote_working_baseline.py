"""Verify exact-revision live evidence before release packaging or local promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from app.infrastructure import qualification as q


def verify(root: Path, report_path: Path) -> list[str]:
    try:
        report = json.loads(report_path.read_text())
        profiles = q.required_profiles(root)
        errors = q.qualification_errors(report, q.identity(root), profiles)
        if errors:
            return errors
        # Validate actual installed GGUF bytes, not only the report's claimed identity.
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
    parser.add_argument("--promote", action="store_true", help="Fast-forward local main and mark working-baseline after verification.")
    args = parser.parse_args()
    root = Path.cwd()
    errors = verify(root, args.report)
    if errors:
        print("Promotion blocked:")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    if args.promote:
        revision = q.git(root, "rev-parse", "HEAD")
        branch = q.git(root, "branch", "--show-current")
        if not branch.startswith("codex/"):
            raise SystemExit("Promotion requires the qualified codex/ candidate branch.")
        if "branch refs/heads/working-baseline" in q.git(root, "worktree", "list", "--porcelain"):
            raise SystemExit("The working-baseline branch is checked out elsewhere; it was not moved.")
        # No force, rewind, remote operation or alteration of the other checkout.
        subprocess.run(["git", "merge-base", "--is-ancestor", "main", revision], cwd=root, check=True)
        try:
            old = q.git(root, "rev-parse", "refs/heads/working-baseline")
        except subprocess.CalledProcessError:
            old = "0" * 40
        if old != "0" * 40:
            subprocess.run(["git", "merge-base", "--is-ancestor", old, revision], cwd=root, check=True)
        subprocess.run(["git", "switch", "main"], cwd=root, check=True)
        subprocess.run(["git", "merge", "--ff-only", revision], cwd=root, check=True)
        subprocess.run(["git", "update-ref", "refs/heads/working-baseline", revision, old], cwd=root, check=True)
        subprocess.run(["git", "branch", "-d", branch], cwd=root, check=True)
    print("Exact-revision live qualification verified.")


if __name__ == "__main__":
    main()
