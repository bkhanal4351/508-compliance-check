from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel


class Severity(str, Enum):
    CRITICAL = "Critical"
    SERIOUS  = "Serious"
    MODERATE = "Moderate"
    MINOR    = "Minor"


class Finding(BaseModel):
    id: str
    rule: str
    wcag_sc: str
    sec508_ref: str
    severity: Severity
    title: str
    description: str
    location: str
    snippet: Optional[str] = None
    suggested_fix: Optional[str] = None
    source: Literal["deterministic", "semantic"]
    needs_human_review: bool = False
