"""Owned export scratch files are reclaimed even when the bridge is aborted."""
import asyncio
from pathlib import Path
import sys

from app.mcp.stdio_transport import OwnedStdioTransport


def test_worker_abort_reclaims_its_private_export_directory(tmp_path):
    transport=OwnedStdioTransport([sys.executable,"-c","import time;time.sleep(30)"],root=tmp_path)
    async def exercise():
        async with transport.open():
            folder=Path(transport._temporary.name)
            assert folder.resolve().is_relative_to(tmp_path.resolve())
            (folder/"interrupted.pdf").write_bytes(b"synthetic export")
            transport.abort()
            assert transport.temporary_released and not folder.exists()
    asyncio.run(exercise())
    assert transport.process.poll() is not None


def test_replaced_temporary_directory_is_not_deleted(tmp_path):
    transport=OwnedStdioTransport([sys.executable,"-c","import time;time.sleep(30)"],root=tmp_path)
    async def exercise():
        async with transport.open():
            folder=Path(transport._temporary.name)
            preserved=folder.with_name(folder.name+"-preserved")
            folder.rename(preserved)
            folder.mkdir()
            foreign=folder/"foreign.txt"
            foreign.write_text("foreign fixture",encoding="utf-8")
            transport.abort()
            assert not transport.temporary_released and foreign.read_text()=="foreign fixture"
    asyncio.run(exercise())
    assert transport.process.poll() is not None
