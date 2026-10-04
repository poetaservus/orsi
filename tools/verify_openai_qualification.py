"""Read-only qualification audit; never promotes a profile or changes Git."""
import argparse
import json
from pathlib import Path

from app.infrastructure import openai_qualification as gate


def verify(root: Path, path: Path) -> list[str]:
    try:
        return gate.qualification_errors(json.loads(path.read_text()), gate.identity(root), gate.profiles(root))
    except Exception as exc:
        return [f"Qualification report unavailable ({type(exc).__name__})."]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    errors = verify(Path.cwd(), args.report)
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
