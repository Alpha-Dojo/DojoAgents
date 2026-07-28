"""Shared Pydantic value objects for attribution payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LocaleText(BaseModel):
    """zh/en display strings. Missing side stays \"\"."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    zh: str = ""
    en: str = ""


class EvidenceSpan(BaseModel):
    """Grounding quote plus optional url/title."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    quote: str = Field(min_length=1)
    url: str | None = None
    title: str | None = None
