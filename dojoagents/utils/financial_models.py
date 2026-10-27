"""Framework-neutral primitives shared by financial API contracts."""

from pydantic import BaseModel


class BilingualText(BaseModel):
    zh: str = ""
    en: str = ""
