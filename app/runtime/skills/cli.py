"""Local skill management commands, independent of UI and inference startup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app.runtime.skills.installer import SkillInstaller, SkillInstallError
from app.runtime.skills.registry import SkillRegistry


def _label(value, limit=512):
    return json.dumps(value if len(value) <= limit else value[:limit] + "...", ensure_ascii=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="orsi skill", description="Manage local instruction-only skills.")
    parser.add_argument("--storage", type=Path, help="Explicit global skill storage (default: ~/.orsi/skills).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List available skills.")
    install = commands.add_parser("install", help="Inspect and install a local directory; copy SKILL.md only.")
    install.add_argument("path", type=Path)
    remove = commands.add_parser("remove", help="Remove a global skill containing SKILL.md alone.")
    remove.add_argument("name")
    info = commands.add_parser("info", help="Show skill metadata without loading its instructions into a model.")
    info.add_argument("name")
    args = parser.parse_args(argv)
    try:
        installer = SkillInstaller(SkillRegistry(global_root=args.storage))
        if args.command == "list":
            skills = installer.list()
            for skill in skills:
                print(f"{_label(skill.name, 128)}: {_label(skill.description)}")
            if not skills:
                print("No skills available.")
            for issue in installer.registry.report.issues:
                print(f"Rejected catalog entry: {issue.code}", file=sys.stderr)
            return 1 if installer.registry.report.issues else 0
        if args.command == "info":
            skill = installer.info(args.name)
            print(json.dumps({"name": skill.name, "description": skill.description,
                              "source_path": str(skill.source_path), "supported_files": ["SKILL.md"]},
                             ensure_ascii=True, indent=2))
        elif args.command == "install":
            def preview(skills):
                print("Validated local skills (SKILL.md only):")
                for skill in skills:
                    print(f"{_label(skill.name, 128)}: {_label(skill.description)}")
            result = installer.install(args.path, on_discovered=preview)
            for name in result.installed:
                print(f"Installed {_label(name, 128)}.")
            for name in result.already_installed:
                print(f"Already installed {_label(name, 128)} with identical content.")
        elif args.command == "remove":
            installer.remove(args.name)
            print(f"Removed {_label(args.name, 128)}.")
    except SkillInstallError as error:
        print(f"Skill operation failed ({error.code.value}): {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        print("Skill operation failed: invalid or inaccessible local storage.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
