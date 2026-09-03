from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.executors.base import CommandResult


class LocalExecutor:
    def __init__(self, *, root_dir: Path) -> None:
        self._root_dir = root_dir

    async def run(self, argv: list[str]) -> CommandResult:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._root_dir)
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=self._root_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return CommandResult(
            exit_code=process.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
