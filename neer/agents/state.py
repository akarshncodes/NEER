"""CaseState: the one shared memory every agent reads and writes during a case.

LangGraph checkpoints it after every step, so a case survives a crash or a
human taking an hour to approve.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional

from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    agent: str
    text: str
    kind: str = "info"            # info | decision | action | alert | verdict | human
    provider: Optional[str] = None
    numbers: dict = Field(default_factory=dict)


class CaseState(BaseModel):
    case_id: str
    scenario: str = ""
    status: str = "open"                       # open | watch | no_alarm | closed | escalated
    tier: str = "NONE"
    zone: Optional[str] = None
    leak_size_lps: float = 0.0
    skeptic_verdict: Optional[str] = None
    skeptic_reason: str = ""
    areas: list[dict] = Field(default_factory=list)          # current ordered search areas
    current_area: Optional[str] = None
    next_action: Optional[str] = None
    last_event: str = "start"                  # start | located | acoustic_yes | acoustic_no | dig_empty |
                                               # dig_rejected | not_fixed | partly | inconclusive
    plan_reason: str = ""
    plan_reviewed: bool = False
    review_sendbacks: int = 0
    plan_approved: bool = False
    visits: int = 0
    replans: int = 0
    inconclusive_waits: int = 0
    work_order: Optional[str] = None
    dig_approver: Optional[str] = None
    verdict: Optional[str] = None
    verdict_reason: str = ""
    llr_trace: list[float] = Field(default_factory=list)
    contractor: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)
    timeline: Annotated[list[dict], operator.add] = Field(default_factory=list)   # TimelineEntry dicts
