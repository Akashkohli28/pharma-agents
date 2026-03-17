"""
pharmaiq/mcp_tools.py
──────────────────────
LangChain tool wrappers for all five MCP servers.
Each function represents one MCP server tool call.
Replace the stub implementations with real MCP client calls.
"""

from __future__ import annotations
from langchain_core.tools import tool
from datetime import datetime
from state import (
    BreachEvent, ShiftPlan, ScheduleHBreach, BatchAlert,
    DiseaseAlert, PurchaseOrder
)


# ══════════════════════════════════════════════
# MCP-01  ThermoSense — Cold Chain IoT
# ══════════════════════════════════════════════

@tool
def poll_sensors(store_ids: list[str]) -> list[dict]:
    """
    MCP-01 ThermoSense.
    Poll live temperature readings from all refrigeration units
    across the given stores. Returns raw sensor telemetry.
    """
    return [
        {"unit_id": f"REF-{s[4:]}-01", "store_id": s, "temp": 4.5, "status": "ok"}
        for s in store_ids
    ] + [
        {"unit_id": f"REF-{s[4:]}-02", "store_id": s, "temp": 8.1, "status": "breach"}
        for s in store_ids if "042" in s or "080" in s
    ]


@tool
def quarantine_batch(batch_id: str, unit_id: str, reason: str) -> dict:
    """
    MCP-01 ThermoSense + MCP-03 InventoryCore.
    Flag a batch as quarantined due to a temperature breach.
    Writes status to InventoryCore and triggers CDSCO log entry.
    """
    return {"status": "quarantined", "batch_id": batch_id, "logged": True, "reason": reason}


@tool
def dispatch_breach_alert(breach: dict) -> dict:
    """
    MCP-01 ThermoSense.
    Send immediate SMS + app alert to store manager and ops team
    on temperature breach detection.
    """
    return {"alert_sent": True, "channels": ["sms", "app"]}


# ══════════════════════════════════════════════
# MCP-02  WorkforceOS — Staff Scheduling
# ══════════════════════════════════════════════

@tool
def generate_schedule(store_id: str, date: str, predicted_footfall: int,
                       epi_surge: bool = False) -> dict:
    """
    MCP-02 WorkforceOS.
    Generate an optimised shift schedule for a store on a given date.
    Always ensures a registered pharmacist covers Schedule H hours.
    """
    return {
        "store_id": store_id,
        "date": date,
        "shifts": [
            {"staff_id": "STF-01", "role": "Pharmacist", "start": "09:00", "end": "17:00"},
            {"staff_id": "STF-02", "role": "Assistant", "start": "10:00", "end": "18:00"},
        ],
        "pharmacist_covered": True,
        "overtime_hours": 0.0
    }


@tool
def enforce_schedule_h(store_id: str, shift_plan: dict) -> dict:
    """
    MCP-02 WorkforceOS.
    Validate that a Schedule H registered pharmacist is on duty
    for all required hours. Returns compliance status and any gaps.
    """
    return {"compliant": True, "gaps": []}


@tool
def notify_store_manager(store_id: str, message: str, urgency: str) -> dict:
    """
    MCP-02 WorkforceOS.
    Push notification to store manager via app and SMS.
    """
    return {"notified": True, "store_id": store_id}


# ══════════════════════════════════════════════
# MCP-03  InventoryCore — Stock & Batch Data (Shared)
# ══════════════════════════════════════════════

@tool
def scan_expiry(store_ids: list[str], horizon_days: int = 90) -> list[dict]:
    """
    MCP-03 InventoryCore (SOMA).
    Scan all batches across given stores and return any SKU
    with days_to_expiry <= horizon_days.
    """
    return [
        {"sku_code": "SKU-87846", "sku_name": "Atorvastatin 40mg", "days_to_expiry": 15, "stock_units": 120},
        {"sku_code": "SKU-24728", "sku_name": "Azithromycin 250mg", "days_to_expiry": -5, "stock_units": 45}
    ]


@tool
def trigger_markdown(sku_code: str, store_id: str, markdown_pct: float) -> dict:
    """
    MCP-03 InventoryCore (SOMA).
    Apply a markdown to a near-expiry SKU in the given store.
    Updates POS pricing in real time.
    """
    return {"applied": True, "sku_code": sku_code, "markdown_pct": markdown_pct}


@tool
def get_stock_levels(store_ids: list[str], sku_codes: list[str]) -> dict:
    """
    MCP-03 InventoryCore (PULSE).
    Return current stock units and days-of-cover for the given
    SKU list across specified stores.
    """
    return {s: {sku: {"units": 120, "days_cover": 14} for sku in sku_codes} for s in store_ids}


@tool
def redistribute_stock(from_store: str, to_store: str,
                        sku_code: str, units: int) -> dict:
    """
    MCP-03 InventoryCore (PULSE).
    Initiate an inter-store stock transfer for a given SKU.
    Updates inventory records in both stores.
    """
    return {"transfer_id": f"TRF-{from_store}-{to_store}", "units": units, "status": "initiated"}


# ══════════════════════════════════════════════
# MCP-04  EpiSignal — IDSP Disease Surveillance
# ══════════════════════════════════════════════

@tool
def fetch_idsp_feed(zones: list[str]) -> list[dict]:
    """
    MCP-04 EpiSignal.
    Pull latest disease cluster data from India's IDSP surveillance
    system for specified geographic zones.
    """
    return [
        {"disease": "Dengue", "zone": zones[0] if zones else "National", "cases": 42, "severity": "High"}
    ]


@tool
def forecast_demand(disease_alert: dict, current_stock: dict) -> dict:
    """
    MCP-04 EpiSignal.
    Run epidemic-aware demand forecast model.
    Returns predicted demand per SKU for next 7/14/30 days.
    """
    return {"SKU-102": {"7d": 200, "14d": 380, "30d": 700}}


@tool
def calculate_stockout_risk(store_ids: list[str],
                             demand_forecast: dict) -> dict:
    """
    MCP-04 EpiSignal.
    Cross-reference demand forecast with current stock.
    Returns stores and SKUs at risk of stockout within 3 days.
    """
    return {store_ids[0]: ["SKU-102"]} if store_ids else {}


# ══════════════════════════════════════════════
# MCP-05  SupplyChain — Reorders & Distributors
# ══════════════════════════════════════════════

@tool
def trigger_reorder(sku_code: str, quantity: int,
                     distributor: str, urgency: str) -> dict:
    """
    MCP-05 SupplyChain.
    Place an emergency purchase order with the distributor.
    Returns PO ID and estimated delivery window.
    """
    return {
        "po_id": f"PO-{sku_code}-{datetime.now().strftime('%Y%m%d%H%M')}",
        "status": "placed",
        "eta_hours": 24,
        "estimated_cost_inr": quantity * 150
    }


@tool
def get_distributor_availability(sku_codes: list[str]) -> dict:
    """
    MCP-05 SupplyChain.
    Check distributor inventory availability for a list of SKUs.
    Returns available units and lead times per distributor.
    """
    return {sku: {"available_units": 500, "lead_time_hours": 18} for sku in sku_codes}


@tool
def initiate_rtvs(batch_ids: list[str], reason: str) -> dict:
    """
    MCP-05 SupplyChain.
    Initiate return-to-vendor (RTV) for expired or compromised batches.
    Coordinates with distributor for collection and credit notes.
    """
    return {"rtvs_initiated": len(batch_ids), "batch_ids": batch_ids, "status": "confirmed"}


# ══════════════════════════════════════════════
# Tool registries (passed to each agent)
# ══════════════════════════════════════════════

SOMA_TOOLS = [
    poll_sensors,
    quarantine_batch,
    dispatch_breach_alert,
    generate_schedule,
    enforce_schedule_h,
    notify_store_manager,
    scan_expiry,
    trigger_markdown,
]

PULSE_TOOLS = [
    fetch_idsp_feed,
    forecast_demand,
    calculate_stockout_risk,
    get_stock_levels,
    trigger_reorder,
    get_distributor_availability,
    initiate_rtvs,
    redistribute_stock,
]
