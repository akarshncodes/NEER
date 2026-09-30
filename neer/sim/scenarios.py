"""Scripted demo / evaluation scenarios. Same name + seed = same story every time."""
from __future__ import annotations

from pydantic import BaseModel, Field

from neer.schemas import Event, FireDraw, Leak, PlannedWork, PumpTrip, StuckSensor, ValveClosure, SensorOffset


class Scenario(BaseModel):
    name: str
    title: str
    events: list[Event] = Field(default_factory=list)
    days_before_case: int = 2          # how many days the problem runs before NEER looks
    misfix_first: bool = False         # the first "repair" is done on the wrong pipe
    chaos: dict = Field(default_factory=dict)
    expect: str = Field(description="Expected end state: closed_fixed | watch | no_alarm")


SCENARIOS: dict[str, Scenario] = {s.name: s for s in [
    Scenario(name="quiet", title="A normal day", expect="watch_or_no_alarm"),
    Scenario(name="leak_20", title="Hidden 20 L/s leak", events=[Leak(node="239", lps=20)], expect="closed_fixed"),
    Scenario(name="leak_10", title="Small 10 L/s leak", events=[Leak(node="169", lps=10)], expect="closed_fixed"),
    Scenario(name="leak_40", title="Burst 40 L/s", events=[Leak(node="117", lps=40)], expect="closed_fixed"),
    Scenario(name="pump_trip", title="Pump 10 trips (logged)", events=[PumpTrip(start_h=8, end_h=13)],
             days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="valve_closure", title="Valve closed by operator (logged)", events=[ValveClosure(pipe="145")],
             days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="planned_work", title="Planned flushing (in calendar)",
             events=[PlannedWork(node="123", lps=30, h0=9, h1=15)], days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="fire_draw", title="Fire-fighting draw", events=[FireDraw(node="199", lps=40, h0=14, h1=16)],
             days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="stuck_sensor", title="Pressure sensor freezes", events=[StuckSensor(sensor="241", from_h=6)],
             days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="sensor_offset", title="Sensor reads 2 m low", events=[SensorOffset(sensor="117", metres=-2.0)],
             days_before_case=1, expect="watch_or_no_alarm"),
    Scenario(name="two_leaks", title="Two leaks in one zone",
             events=[Leak(node="239", lps=20), Leak(node="251", lps=15)], expect="closed_fixed"),
    Scenario(name="wrong_repair", title="Crew fixes the wrong pipe first", events=[Leak(node="239", lps=20)],
             misfix_first=True, expect="closed_fixed"),
    Scenario(name="chaos_scada", title="Leak + SCADA timeouts", events=[Leak(node="239", lps=20)],
             chaos={"scada_timeout": 2}, expect="closed_fixed"),
    Scenario(name="chaos_llm", title="Leak + broken LLM replies", events=[Leak(node="239", lps=20)],
             chaos={"llm_bad_json": 2}, expect="closed_fixed"),
    Scenario(name="chaos_sensor", title="Leak + a sensor dies", events=[Leak(node="239", lps=20)],
             chaos={"sensor_dies": "241"}, expect="closed_fixed"),
    Scenario(name="chaos_crew", title="Leak + crew hears nothing first", events=[Leak(node="239", lps=20)],
             chaos={"crew_finds_nothing": 1}, expect="closed_fixed"),
]}
