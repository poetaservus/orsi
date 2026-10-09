"""Repeatable synthetic experiment; reports contain only fixed labels/counts.

Defaults simulate both locations under ignored state. Supplying parent paths
exercises other locations but does not qualify a physical SSD or another host.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import struct
from time import perf_counter
from uuid import uuid4
import zlib

import nacl

from app.vault.prototype import Domain, KdfCost, VaultError, VaultPrototype


def synthetic_png(width=3072, height=3072):
    """A valid, large RGB PNG created entirely in memory, with no personal input."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    compressor = zlib.compressobj(level=0)
    compressed = BytesIO()
    for _ in range(height):
        compressed.write(compressor.compress(b"\0" + os.urandom(width * 3)))
    compressed.write(compressor.flush())
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", compressed.getvalue()) + chunk(b"IEND", b""))


def run_experiment(output_root: Path, *, local_parent: Path | None = None,
                   portable_parent: Path | None = None, image_width=3072, image_height=3072,
                   cost: KdfCost = KdfCost()):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    image = synthetic_png(image_width, image_height)
    marker = b"SYNTHETIC-VAULT-PERSONAL-MARKER-v1"
    credential = b"SYNTHETIC-VAULT-CREDENTIAL-MARKER-v1"
    password = os.urandom(32)
    report = {"schema_version": 1, "python_version": platform.python_version(),
              "platform": platform.system(), "pynacl_version": nacl.__version__,
              "kdf_operations": cost.operations, "kdf_memory_bytes": cost.memory_bytes,
              "image_bytes": len(image), "image_width": image_width, "image_height": image_height,
              "minimum_machine_qualified": False, "physical_ssd_qualified": False, "locations": []}
    for mode, parent in (("local", local_parent), ("portable", portable_parent)):
        simulated = parent is None
        parent = output_root / (mode + "-simulation") if simulated else Path(parent)
        root = parent / ("synthetic-vault-" + run_id)
        start = perf_counter()
        vault = VaultPrototype.create(root, password, synthetic=True, cost=cost)
        create_ms = (perf_counter() - start) * 1000
        personal = vault.put("history/synthetic-title", BytesIO(marker))
        secret = vault.put("connections/synthetic-provider", BytesIO(credential), domain=Domain.CREDENTIAL)
        start = perf_counter()
        asset = vault.put("outputs/synthetic-private-name.png", BytesIO(image))
        write_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        if vault.read(asset).content != image:
            raise VaultError("Synthetic image verification failed.")
        read_ms = (perf_counter() - start) * 1000
        timings = []
        for _ in range(3):
            vault.lock()
            start = perf_counter()
            vault.unlock(password)
            timings.append(round((perf_counter() - start) * 1000, 3))
        if vault.read(personal).content != marker or vault.read(secret).content != credential:
            raise VaultError("Synthetic record verification failed.")
        vault.lock()
        # Explicit encrypted copy, original retained. Both copies stay closed
        # until this single-process test opens the copy. No synchronization.
        relocated = parent / ("synthetic-relocated-" + run_id)
        shutil.copytree(root, relocated)
        restored = VaultPrototype(relocated)
        restored.unlock(password)
        if restored.read(asset).content != image:
            raise VaultError("Synthetic relocation verification failed.")
        restored.lock()
        plaintext_found = False
        for base in (root, relocated):
            for path in base.rglob("*"):
                if path.is_file():
                    raw = path.read_bytes()
                    plaintext_found |= any(value in raw for value in (
                        marker, credential, password, b"synthetic-private-name.png", image[:64]))
        if plaintext_found:
            raise VaultError("Synthetic plaintext marker scan failed.")
        encrypted_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        report["locations"].append({"mode": mode, "location_simulated": simulated,
            "create_ms": round(create_ms, 3), "unlock_ms": timings,
            "unlock_median_ms": round(statistics.median(timings), 3),
            "image_write_ms": round(write_ms, 3), "image_read_ms": round(read_ms, 3),
            "encrypted_bytes": encrypted_bytes, "relocation_verified": True,
            "plaintext_marker_found": False})
    report_path = output_root / ("report-" + run_id + ".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("state/vault-phase1-experiment"))
    parser.add_argument("--local-parent", type=Path)
    parser.add_argument("--portable-parent", type=Path)
    parser.add_argument("--kdf-policy", choices=("interactive", "moderate"), default="interactive")
    args = parser.parse_args()
    try:
        cost = KdfCost(3, 256 * 1024 * 1024) if args.kdf_policy == "moderate" else KdfCost()
        report = run_experiment(args.output_root, local_parent=args.local_parent,
                                portable_parent=args.portable_parent, cost=cost)
    except (VaultError, OSError):
        print("Synthetic vault experiment failed; no personal data was used.")
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
