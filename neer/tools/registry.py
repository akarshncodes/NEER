"""The 19 tools, grouped by the MCP server that exposes them."""
from neer.tools import audit, field, scada, twin

SERVERS = {
    "scada": [scada.get_zone_flow, scada.get_pressure, scada.sensor_health, scada.get_ops_log,
              scada.get_supply_calendar],
    "twin": [twin.simulate, twin.replay_operation, twin.locate_leak, twin.estimate_leak_size,
             twin.plan_search_areas],
    "field": [field.acoustic_check, field.create_work_order, field.crew_status, field.notify_residents,
              field.slow_refill_instruction],
    "audit": [audit.verify_repair, audit.release_contractor, audit.case_memory, audit.kpi_report],
}
ALL_TOOLS = {fn.__name__: fn for fns in SERVERS.values() for fn in fns}
