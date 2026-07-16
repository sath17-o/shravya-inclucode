from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class ContextCompletenessIssue(BaseModel):
    code: str
    section: str
    field: str | None = None
    message_key: str
    recovery_action: str


class ContextCompletenessResult(BaseModel):
    context_version_id: str
    is_complete: bool
    issues: list[ContextCompletenessIssue] = Field(default_factory=list)
    completed_sections: list[str] = Field(default_factory=list)
    incomplete_sections: list[str] = Field(default_factory=list)


@dataclass
class DomainError(Exception):
    code: str
    message_key: str
    category: Literal["not_found", "validation", "conflict", "forbidden"]
    details: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.code
