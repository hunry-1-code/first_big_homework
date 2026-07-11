from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StageResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    version: str = "v1"

    @classmethod
    def success(cls, data: dict[str, Any], version: str = "v1") -> "StageResult":
        return cls(status="success", data=data, version=version)

    @classmethod
    def degraded(
        cls,
        data: dict[str, Any],
        warnings: list[str],
        version: str = "v1",
    ) -> "StageResult":
        return cls(status="degraded", data=data, warnings=warnings, version=version)

    @classmethod
    def failed(
        cls,
        errors: list[str],
        data: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        version: str = "v1",
    ) -> "StageResult":
        return cls(
            status="failed",
            data=data or {},
            warnings=warnings or [],
            errors=errors,
            version=version,
        )
