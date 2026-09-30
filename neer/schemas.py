"""NEER contracts: every tool input/output and the shared case state.

These Pydantic models are the "language" agents, tools, MCP servers and the
dashboard use to talk to each other. Field descriptions become the MCP tool
schemas, so keep them clear.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# ============================================================ events (things that happen in the city)
class Leak(BaseModel):
    kind: Literal["leak"] = "leak"
    node: str = Field(description="Junction where water escapes")
    lps: float = Field(gt=0, le=200, description="Leak flow in litres per second")


class PumpTrip(BaseModel):
    kind: Literal["pump_trip"] = "pump_trip"
    pump: str = Field(default="10", description="Pump that switched off")
    start_h: int = Field(ge=0, le=23)
    end_h: int = Field(ge=1, le=24)


class ValveClosure(BaseModel):
    kind: Literal["valve_closure"] = "valve_closure"
    pipe: str = Field(description="Pipe closed by an operator")


class FireDraw(BaseModel):
    kind: Literal["fire_draw"] = "fire_draw"
    node: str
    lps: float = Field(gt=0, le=200)
    h0: int = Field(ge=0, le=23)
    h1: int = Field(ge=1, le=24)


class PlannedWork(BaseModel):
    """Scheduled water draw, e.g. mains flushing or a tanker-filling point (in the supply calendar)."""
    kind: Literal["planned_work"] = "planned_work"
    node: str
    lps: float = Field(gt=0, le=200)
    h0: int = Field(ge=0, le=23)
    h1: int = Field(ge=1, le=24)


class StuckSensor(BaseModel):
    kind: Literal["stuck_sensor"] = "stuck_sensor"
    sensor: str
    from_h: int = Field(default=6, ge=0, le=23)


class SensorOffset(BaseModel):
    kind: Literal["sensor_offset"] = "sensor_offset"
    sensor: str
    metres: float = Field(default=-2.0)


Event = Annotated[
    Union[Leak, PumpTrip, ValveClosure, FireDraw, PlannedWork, StuckSensor, SensorOffset],
    Field(discriminator="kind"),
]


class OpsEvent(BaseModel):
    """An operator action recorded by SCADA (visible to NEER)."""
    op_id: str
    day: int
    kind: Literal["pump_trip", "valve_closure"]
    detail: str = Field(description="Human-readable description")
    event: dict = Field(description="The event parameters, for replay in the twin")


class CalendarEntry(BaseModel):
    """Planned work from the water board's schedule (flushing, tanker filling)."""
    entry_id: str
    day: int
    zone: str
    h0: int
    h1: int
    detail: str
    event: dict = Field(description="The event parameters, for replay in the twin")


# ============================================================ monitoring reports
class ZoneFlow(BaseModel):
    zone: str
    inflow_lps: list[float] = Field(description="Hourly net inflow (after bulk meters), L/s")
    normal_lps: list[float] = Field(description="Hourly normal inflow, L/s")
    excess_lps: float = Field(description="Unexplained extra water, L/s (weighted daily)")
    t_score: float = Field(description="Excess divided by its normal spread; > 4 is suspicious")


class ZoneFlowReport(BaseModel):
    day: int
    zones: list[ZoneFlow]


class SensorPressure(BaseModel):
    sensor: str
    residual_m: list[float] = Field(description="Normal minus observed pressure per hour (positive = drop)")
    z_rms: float


class PressureReport(BaseModel):
    day: int
    score: float = Field(description="Overall pressure anomaly score")
    threshold: float
    sensors: list[SensorPressure]


class SensorStatus(str, Enum):
    ok = "ok"
    frozen = "frozen"
    outlier = "outlier"
    offline = "offline"


class SensorHealthItem(BaseModel):
    sensor: str
    status: SensorStatus
    reason: str = ""


class SensorHealth(BaseModel):
    sensors: list[SensorHealthItem]

    @property
    def unhealthy(self) -> list[str]:
        return [s.sensor for s in self.sensors if s.status != SensorStatus.ok]


class Tier(str, Enum):
    none = "NONE"
    watch = "WATCH"
    probable = "PROBABLE"
    confirmed = "CONFIRMED"


class Detection(BaseModel):
    alarm: bool
    tier: Tier
    water: bool = Field(description="Witness 1: a zone takes more water than normal")
    pressure: bool = Field(description="Witness 2: pressure dips like a leak")
    persistence: bool = Field(description="Witness 3: it is still there late in the day")
    zone_t: dict[str, float]
    zone_excess_lps: dict[str, float]
    pressure_score: float
    top_dips: list[tuple[str, float]] = Field(default_factory=list, description="(sensor, mean drop m)")


class SkepticKind(str, Enum):
    no_alarm = "no_alarm"
    sensor_fault = "sensor_fault"
    operation = "operation"
    planned_work = "planned_work"
    temporary = "temporary"
    leak = "leak"


class SkepticVerdict(BaseModel):
    verdict: SkepticKind
    reason: str
    masked_sensors: list[str] = Field(default_factory=list)
    numbers: dict[str, float] = Field(default_factory=dict)


# ============================================================ localisation & search
class SearchArea(BaseModel):
    area_id: str = Field(description="A-<junction>")
    junctions: list[str]
    probability: float
    pipe_km: float


class LocateResult(BaseModel):
    zone: str
    leak_size_lps: float
    zone_t: dict[str, float]
    areas: list[SearchArea]
    evidence: list[str]


class AcousticResult(BaseModel):
    area_id: str
    result: Literal["yes", "no"]
    confidence: float


class WorkOrder(BaseModel):
    work_order_id: str
    case_id: str
    area_id: str
    action: Literal["acoustic", "dig", "repair"]
    status: Literal["open", "done"] = "open"
    result: Optional[str] = None


class CrewStatus(BaseModel):
    work_order_id: str
    status: str
    result: Optional[Literal["found_leak", "nothing_found", "repaired"]] = None


class AuditKind(str, Enum):
    fixed = "FIXED"
    partly_fixed = "PARTLY_FIXED"
    not_fixed = "NOT_FIXED"
    inconclusive = "INCONCLUSIVE"


class AuditVerdict(BaseModel):
    verdict: AuditKind
    hours_used: int
    llr_trace: list[float] = Field(description="Evidence after each hour; +ln99 = NOT FIXED, -ln99 = FIXED")
    pre_excess_lps: float
    post_excess_lps: float
    reason: str


class ToolError(BaseModel):
    """Returned instead of raising, so an agent can read it and correct itself."""
    error: Literal[True] = True
    code: Literal["invalid_input", "timeout", "degraded", "refused", "internal"]
    message: str
    hint: str = ""


# ============================================================ case state (shared by all agents)
class EvidenceItem(BaseModel):
    source: str = Field(description="Agent or tool that produced it")
    text: str
    numbers: dict[str, float] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step: int
    action: Literal["acoustic_check", "request_dig", "next_area", "wait_more_data", "escalate"]
    area_id: Optional[str] = None
    reason: str


class CaseStatus(str, Enum):
    open = "open"
    watch = "watch"
    closed = "closed"
    escalated = "escalated"
    no_alarm = "no_alarm"
