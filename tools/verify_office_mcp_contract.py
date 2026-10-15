"""Verify the accepted Office manifest and budget without Office, credentials or APIs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mcp.office_budget import accepted_office_manifest, office_budget_report


def verify(manifest_path: Path) -> dict:
    accepted = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = office_budget_report()
    report["manifest_matches"] = accepted == accepted_office_manifest()
    report["passed"] = report["manifest_matches"] and report["within_budget"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config/office_mcp_v1.json")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.manifest)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
