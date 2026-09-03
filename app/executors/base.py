from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


class Executor(Protocol):
    async def run(self, argv: list[str]) -> CommandResult:
        raise NotImplementedError
