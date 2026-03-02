from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .base import EntityCompiler
from .generic import GenericCompiler


@dataclass
class CompilerRegistry:
    _compilers: Dict[str, EntityCompiler[Any]] = field(default_factory=dict)

    def register(self, compiler: EntityCompiler[Any]) -> None:
        self._compilers[compiler.endpoint] = compiler

    def resolve(self, endpoint: str) -> EntityCompiler[Any]:
        compiler = self._compilers.get(endpoint)
        if compiler is None:
            compiler = GenericCompiler(endpoint=endpoint)
            self._compilers[endpoint] = compiler
        return compiler

    def has(self, endpoint: str) -> bool:
        return endpoint in self._compilers

    def endpoints(self) -> list[str]:
        return sorted(self._compilers)
