"""
pharmaiq/state.py
─────────────────
Shared TypedDict state that flows through every node in the LangGraph.
All agents read from and write to this single state object.
"""

from __future__ import annotations
from typing import TypedDict, Annotated, Literal, Optional
from dataclasses import dataclass, field
from datetime import datetime
import operator


# ──────────────────────────────────────────────
# Domain types
# ──────────────────────────────────────────────

@dataclass
class BreachEvent:
    unit_id: str
    store_id: str
    temp_celsius: float
    threshold_min: float
    threshold_max: float
    breach_duration_mins: int
    batches_at_risk: list[str]
    timestamp: datetime


@dataclass
class ShiftPlan:
    store_id: str
    date: str
    shifts: list[dict]          # [{staff_id, role, start, end}]
    pharmacist_covered: bool
    overtime_hours: float


@dataclass
class ScheduleHBreach:
    store_id: str
    shift: str
    reason: str
    timestamp: datetime


@dataclass
class BatchAlert:
    sku_code: str
    sku_name: str
    batch_no: str
    days_to_expiry: int
    stock_units: int
    estimated_loss_inr: float
    recommended_action: Literal["markdown", "return", "redistribute", "destroy"]


@dataclass
class DiseaseAlert:
    disease: str
    zone: str
    idsp_case_count: int
    severity_index: float
    alert_level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    affected_skus: list[str]


@dataclass
class PurchaseOrder:
    po_id: str
    sku_code: str
    sku_name: str
    quantity: int
    distributor: str
    estimated_cost_inr: float
    urgency: Literal["routine", "urgent", "critical"]


@dataclass
class CriticFlag:
    action_id: str
    flag_type: Literal["disproportionate", "unsupported", "conflict", "incomplete"]
    description: str
    severity: Literal["low", "medium", "high"]


@dataclass
class Violation:
    rule_id: str
    rule_name: str
    action_id: str
    description: str
    hard_block: bool


@dataclass
class ExecutionPlan:
    agents_to_run: list[Literal["soma", "pulse"]]
    constraints: dict                   # e.g. {"max_po_inr": 250000}
    action_budget_inr: float
    urgency: Literal["routine", "urgent", "critical"]
    reasoning: str                      # Planner's chain-of-thought


@dataclass
class CriticReport:
    overall_score: float                # 0–100
    action_scores: dict[str, float]     # action_id → score
    flags: list[CriticFlag]
    recommendation: Literal["approve", "revise", "escalate"]
    summary: str


@dataclass
class OpsReport:
    run_id: str
    timestamp: datetime
    risk_score: float
    soma_summary: str
    pulse_summary: str
    actions_dispatched: list[str]
    violations_blocked: list[str]
    revision_count: int


# ──────────────────────────────────────────────
# SOMA output
# ──────────────────────────────────────────────

@dataclass
class SOMAResult:
    breaches: list[BreachEvent] = field(default_factory=list)
    schedule_updates: dict[str, ShiftPlan] = field(default_factory=dict)
    compliance_flags: list[ScheduleHBreach] = field(default_factory=list)
    expiry_alerts: list[BatchAlert] = field(default_factory=list)


# ──────────────────────────────────────────────
# PULSE output
# ──────────────────────────────────────────────

@dataclass
class PULSEResult:
    disease_alerts: list[DiseaseAlert] = field(default_factory=list)
    demand_forecast: dict[str, int] = field(default_factory=dict)   # sku → units
    reorders_placed: list[PurchaseOrder] = field(default_factory=list)
    stockout_risk: dict[str, list[str]] = field(default_factory=dict)  # store → skus


# ──────────────────────────────────────────────
# Shared LangGraph State
# ──────────────────────────────────────────────

class PharmaIQState(TypedDict):
    # ── Entry ──
    trigger_type:     Literal["cron", "breach", "epi", "manual"]
    timestamp:        datetime
    store_ids:        list[str]
    priority:         Literal["low", "med", "high", "critical"]

    # ── Planning ──
    execution_plan:   Optional[ExecutionPlan]

    # ── Agent outputs ──
    soma_output:      Optional[SOMAResult]
    pulse_output:     Optional[PULSEResult]

    # ── Cross-agent context (PULSE → SOMA) ──
    epi_context:      Optional[list[DiseaseAlert]]

    # ── Review ──
    critic_report:    Optional[CriticReport]

    # ── Compliance ──
    guard_status:     Optional[Literal["pass", "fail", "escalate"]]
    guard_violations: Annotated[list[Violation], operator.add]  # accumulates across loops
    blocked_actions:  list[str]

    # ── Loop control ──
    revision_count:   int

    # ── Output ──
    ops_report:       Optional[OpsReport]
    notifications:    Annotated[list[str], operator.add]   # accumulates alerts
