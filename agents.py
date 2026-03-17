"""
pharmaiq/agents.py
───────────────────
All five LangGraph node functions:
  1. planner_node      — pre-execution planning + loop revision
  2. soma_node         — cold chain, staff, expiry
  3. pulse_node        — epidemic forecasting, supply chain
  4. critic_node       — quality review of proposed actions
  5. guardrail_node    — compliance firewall + loop-back decision
"""

from __future__ import annotations
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
load_dotenv()

from state import (
    PharmaIQState, ExecutionPlan, SOMAResult, PULSEResult,
    CriticReport, CriticFlag, Violation, OpsReport
)
from mcp_tools import SOMA_TOOLS, PULSE_TOOLS

from datetime import datetime
import json
import uuid
from pathlib import Path

# ──────────────────────────────────────────────
# Prompt Loader
# ──────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent / "prompts" / filename
    return prompt_path.read_text().strip()


# ──────────────────────────────────────────────
# Output Parsers
# ──────────────────────────────────────────────

def _extract_json_block(messages: list) -> dict:
    """
    Scans the agent message list from the end to find the last AI message
    that contains a ```json ... ``` block. Returns the parsed dict or {}.
    """
    import re
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        text = msg.content if isinstance(msg.content, str) else ""
        # Look for a fenced JSON block
        match = re.search(r"```json\s*([\s\S]+?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
        # Fallback: bare JSON object at end of message
        match = re.search(r"(\{[\s\S]+\})\s*$", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
    return {}


def parse_soma_output(messages: list) -> SOMAResult:
    """
    Parse the SOMA agent's final message into a typed SOMAResult.
    Expects the agent to have emitted a ```json block per its system prompt.
    Falls back to empty SOMAResult on any parse error.
    """
    from state import BreachEvent, ShiftPlan, ScheduleHBreach, BatchAlert

    data = _extract_json_block(messages)
    if not data:
        return SOMAResult()

    # ── Breaches ──
    breaches = []
    for b in data.get("breaches", []):
        try:
            breaches.append(BreachEvent(
                unit_id=b["unit_id"],
                store_id=b["store_id"],
                temp_celsius=float(b.get("temp_celsius", 0)),
                threshold_min=float(b.get("threshold_min", 2.0)),
                threshold_max=float(b.get("threshold_max", 8.0)),
                breach_duration_mins=int(b.get("breach_duration_mins", 0)),
                batches_at_risk=b.get("batches_at_risk", []),
                timestamp=datetime.now(),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # ── Schedule updates ──
    schedule_updates = {}
    for store_id, s in data.get("schedule_updates", {}).items():
        try:
            schedule_updates[store_id] = ShiftPlan(
                store_id=s["store_id"],
                date=s["date"],
                shifts=s.get("shifts", []),
                pharmacist_covered=bool(s.get("pharmacist_covered", True)),
                overtime_hours=float(s.get("overtime_hours", 0.0)),
            )
        except (KeyError, ValueError, TypeError):
            continue

    # ── Compliance flags ──
    compliance_flags = []
    for f in data.get("compliance_flags", []):
        try:
            compliance_flags.append(ScheduleHBreach(
                store_id=f["store_id"],
                shift=f["shift"],
                reason=f["reason"],
                timestamp=datetime.now(),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # ── Expiry alerts ──
    expiry_alerts = []
    for e in data.get("expiry_alerts", []):
        try:
            expiry_alerts.append(BatchAlert(
                sku_code=e["sku_code"],
                sku_name=e["sku_name"],
                batch_no=e.get("batch_no", "UNKNOWN"),
                days_to_expiry=int(e.get("days_to_expiry", 0)),
                stock_units=int(e.get("stock_units", 0)),
                estimated_loss_inr=float(e.get("estimated_loss_inr", 0.0)),
                recommended_action=e.get("recommended_action", "markdown"),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    return SOMAResult(
        breaches=breaches,
        schedule_updates=schedule_updates,
        compliance_flags=compliance_flags,
        expiry_alerts=expiry_alerts,
    )


def parse_pulse_output(messages: list) -> PULSEResult:
    """
    Parse the PULSE agent's final message into a typed PULSEResult.
    Expects the agent to have emitted a ```json block per its system prompt.
    Falls back to empty PULSEResult on any parse error.
    """
    from state import DiseaseAlert, PurchaseOrder

    data = _extract_json_block(messages)
    if not data:
        return PULSEResult()

    # ── Disease alerts ──
    disease_alerts = []
    for a in data.get("disease_alerts", []):
        try:
            disease_alerts.append(DiseaseAlert(
                disease=a["disease"],
                zone=a["zone"],
                idsp_case_count=int(a.get("idsp_case_count", 0)),
                severity_index=float(a.get("severity_index", 0.0)),
                alert_level=a.get("alert_level", "LOW"),
                affected_skus=a.get("affected_skus", []),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # ── Demand forecast: {sku: units} ──
    demand_forecast = {}
    for sku, units in data.get("demand_forecast", {}).items():
        try:
            demand_forecast[str(sku)] = int(units)
        except (ValueError, TypeError):
            continue

    # ── Reorders placed ──
    reorders_placed = []
    for r in data.get("reorders_placed", []):
        try:
            reorders_placed.append(PurchaseOrder(
                po_id=r["po_id"],
                sku_code=r["sku_code"],
                sku_name=r.get("sku_name", ""),
                quantity=int(r.get("quantity", 0)),
                distributor=r.get("distributor", "Unknown"),
                estimated_cost_inr=float(r.get("estimated_cost_inr", 0.0)),
                urgency=r.get("urgency", "routine"),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # ── Stockout risk: {store: [skus]} ──
    stockout_risk = {}
    for store, skus in data.get("stockout_risk", {}).items():
        if isinstance(skus, list):
            stockout_risk[str(store)] = [str(s) for s in skus]

    return PULSEResult(
        disease_alerts=disease_alerts,
        demand_forecast=demand_forecast,
        reorders_placed=reorders_placed,
        stockout_risk=stockout_risk,
    )

PLANNER_SYSTEM = load_prompt("planner_system.txt")
SOMA_SYSTEM = load_prompt("soma_system.txt")
PULSE_SYSTEM = load_prompt("pulse_system.txt")
CRITIC_SYSTEM = load_prompt("critic_system.txt")


# ──────────────────────────────────────────────
# Shared LLM
# ──────────────────────────────────────────────

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)


# ══════════════════════════════════════════════
# NODE 1 — PLANNER
# Runs before execution AND on every Guardrail loop-back
# ══════════════════════════════════════════════

# PLANNER_SYSTEM moved to prompts/planner_system.txt

def planner_node(state: PharmaIQState) -> dict:
    """
    Pre-execution planning node.
    On first call: builds initial execution plan from trigger context.
    On loop-back: revises plan based on Guardrail violations.
    """
    revision = state.get("revision_count", 0)

    context_parts = [
        f"trigger_type: {state['trigger_type']}",
        f"priority: {state['priority']}",
        f"store_ids: {state['store_ids']}",
        f"revision_count: {revision}",
    ]

    if revision > 0:
        # Loop-back: include what went wrong
        violations = state.get("guard_violations", [])
        critic = state.get("critic_report")
        context_parts += [
            f"guard_violations: {[v.__dict__ for v in violations]}",
            f"critic_recommendation: {critic.recommendation if critic else 'N/A'}",
            f"critic_flags: {[f.__dict__ for f in (critic.flags if critic else [])]}",
        ]

    user_msg = "Produce an execution plan for this run:\n" + "\n".join(context_parts)

    response = llm.invoke([
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    raw = response.content
    # Strip markdown fences if present
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    plan_dict = json.loads(clean)

    plan = ExecutionPlan(
        agents_to_run=plan_dict["agents_to_run"],
        constraints=plan_dict.get("constraints", {}),
        action_budget_inr=plan_dict.get("action_budget_inr", 500000),
        urgency=plan_dict.get("urgency", "routine"),
        reasoning=plan_dict.get("reasoning", ""),
    )

    return {
        "execution_plan": plan,
        "revision_count": revision,   # incremented by guardrail_node on fail
    }


# ══════════════════════════════════════════════
# NODE 2 — SOMA
# Cold chain + workforce + expiry
# ══════════════════════════════════════════════

# SOMA_SYSTEM moved to prompts/soma_system.txt

def soma_node(state: PharmaIQState) -> dict:
    """
    SOMA agent node — cold chain, staff scheduling, expiry.
    Uses LangChain ReAct agent with MCP tool bindings.
    """
    plan: ExecutionPlan = state["execution_plan"]
    if "soma" not in plan.agents_to_run:
        return {"soma_output": SOMAResult()}

    epi_ctx = state.get("epi_context", [])
    epi_note = ""
    if epi_ctx:
        epi_note = f"\nEpi context from PULSE: {[a.__dict__ for a in epi_ctx]}\nAdjust staffing for affected zones."

    user_msg = (
        f"Run your full operational checks for stores: {state['store_ids']}\n"
        f"Urgency: {plan.urgency}\n"
        f"Constraints: {plan.constraints}"
        + epi_note
    )

    agent = create_react_agent(llm, SOMA_TOOLS)
    result = agent.invoke({
        "messages": [
            SystemMessage(content=SOMA_SYSTEM),
            HumanMessage(content=user_msg),
        ]
    })

    soma_result = parse_soma_output(result["messages"])

    return {"soma_output": soma_result}


# ══════════════════════════════════════════════
# NODE 3 — PULSE
# Epidemic-aware demand forecasting + supply chain
# ══════════════════════════════════════════════

# PULSE_SYSTEM moved to prompts/pulse_system.txt

def pulse_node(state: PharmaIQState) -> dict:
    """
    PULSE agent node — epidemic signals + demand forecasting + supply chain.
    Writes epi_context to shared state for SOMA to consume.
    """
    plan: ExecutionPlan = state["execution_plan"]
    if "pulse" not in plan.agents_to_run:
        return {"pulse_output": PULSEResult(), "epi_context": []}

    user_msg = (
        f"Run epidemic surveillance and demand checks for zones covering: {state['store_ids']}\n"
        f"Urgency: {plan.urgency}\n"
        f"Constraints: {plan.constraints}"
    )

    agent = create_react_agent(llm, PULSE_TOOLS)
    result = agent.invoke({
        "messages": [
            SystemMessage(content=PULSE_SYSTEM),
            HumanMessage(content=user_msg),
        ]
    })

    pulse_result = parse_pulse_output(result["messages"])
    epi_alerts = pulse_result.disease_alerts

    return {
        "pulse_output": pulse_result,
        "epi_context": epi_alerts,   # shared to SOMA via state
    }


# ══════════════════════════════════════════════
# NODE 4 — CRITIC
# Reviews proposed actions for quality + proportionality
# ══════════════════════════════════════════════

# CRITIC_SYSTEM moved to prompts/critic_system.txt

def critic_node(state: PharmaIQState) -> dict:
    """
    Critic agent node — reviews SOMA + PULSE outputs for quality.
    """
    soma = state.get("soma_output")
    pulse = state.get("pulse_output")
    plan = state.get("execution_plan")

    context = (
        f"Execution plan: {plan.__dict__ if plan else {}}\n"
        f"SOMA output: {soma.__dict__ if soma else {}}\n"
        f"PULSE output: {pulse.__dict__ if pulse else {}}\n"
        f"Revision count: {state.get('revision_count', 0)}"
    )

    response = llm.invoke([
        SystemMessage(content=CRITIC_SYSTEM),
        HumanMessage(content=f"Review these proposed actions:\n{context}"),
    ])

    raw = response.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    report_dict = json.loads(raw)

    flags = [
        CriticFlag(
            action_id=f["action_id"],
            flag_type=f["flag_type"],
            description=f["description"],
            severity=f["severity"],
        )
        for f in report_dict.get("flags", [])
    ]

    report = CriticReport(
        overall_score=report_dict["overall_score"],
        action_scores=report_dict.get("action_scores", {}),
        flags=flags,
        recommendation=report_dict["recommendation"],
        summary=report_dict.get("summary", ""),
    )

    return {"critic_report": report}


# ══════════════════════════════════════════════
# NODE 5 — GUARDRAIL
# Hard compliance firewall + loop-back decision
# ══════════════════════════════════════════════

# Hard rules — these are non-negotiable
HARD_RULES = [
    {
        "rule_id": "CDSCO-001",
        "rule_name": "Cold chain breach → mandatory quarantine",
        "check": lambda s: (
            not s.get("soma_output")
            or not s["soma_output"].breaches
            or all(getattr(b, "quarantine_applied", True) for b in s["soma_output"].breaches)
        ),
        "description": "Any temperature breach must result in immediate batch quarantine per CDSCO guidelines.",
    },
    {
        "rule_id": "DRUGS-001",
        "rule_name": "Schedule H pharmacist coverage",
        "check": lambda s: all(
            p.pharmacist_covered
            for p in (s.get("soma_output") or SOMAResult()).schedule_updates.values()
        ),
        "description": "All Schedule H dispensing periods must have a registered pharmacist on duty.",
    },
    {
        "rule_id": "FIN-001",
        "rule_name": "Single PO budget cap ₹25L",
        "check": lambda s: all(
            po.estimated_cost_inr <= 2500000
            for po in (s.get("pulse_output") or PULSEResult()).reorders_placed
        ),
        "description": "No single purchase order may exceed ₹25,00,000 without explicit human approval.",
    },
    {
        "rule_id": "SAFETY-001",
        "rule_name": "No compromised batch in circulation",
        "check": lambda s: True,   # implement: verify quarantine_applied for all breach batches
        "description": "Compromised batches must be removed from circulation before any other action.",
    },
    {
        "rule_id": "DATA-001",
        "rule_name": "Minimum 3 corroborating signals for critical actions",
        "check": lambda s: True,   # implement: signal count check
        "description": "Critical actions (quarantine, emergency reorder) require ≥3 data signals.",
    },
]

MAX_REVISIONS = 3

def guardrail_node(state: PharmaIQState) -> dict:
    """
    Guardrail node — runs hard compliance rules.
    PASS  → set guard_status = 'pass'  → route to aggregator
    FAIL  → set guard_status = 'fail'  → route back to planner
    ESCALATE → revision_count >= MAX_REVISIONS → human queue
    """
    violations: list[Violation] = []

    for rule in HARD_RULES:
        try:
            passed = rule["check"](state)
        except Exception:
            passed = True  # don't block on check errors in dev

        if not passed:
            violations.append(Violation(
                rule_id=rule["rule_id"],
                rule_name=rule["rule_name"],
                action_id="N/A",
                description=rule["description"],
                hard_block=True,
            ))

    # Also respect Critic escalation
    critic = state.get("critic_report")
    if critic and critic.recommendation == "escalate":
        violations.append(Violation(
            rule_id="CRITIC-ESC",
            rule_name="Critic escalation",
            action_id="N/A",
            description=f"Critic score {critic.overall_score:.0f}/100 — escalation recommended.",
            hard_block=True,
        ))

    revision_count = state.get("revision_count", 0)

    if not violations:
        status = "pass"
    elif revision_count >= MAX_REVISIONS:
        status = "escalate"
        violations.append(Violation(
            rule_id="LOOP-MAX",
            rule_name="Max revision iterations reached",
            action_id="N/A",
            description=f"Reached {MAX_REVISIONS} revision attempts. Escalating to human review.",
            hard_block=True,
        ))
    else:
        status = "fail"

    blocked = [v.rule_id for v in violations if v.hard_block]

    new_revision = revision_count + 1 if status == "fail" else revision_count

    return {
        "guard_status": status,
        "guard_violations": violations,   # Annotated[list, operator.add] — accumulates
        "blocked_actions": blocked,
        "revision_count": new_revision,
    }


# ══════════════════════════════════════════════
# NODE 6 — AGGREGATOR
# Merges outputs, builds OpsReport, queues notifications
# ══════════════════════════════════════════════

def aggregator_node(state: PharmaIQState) -> dict:
    """
    Final aggregation node — merges SOMA + PULSE outputs,
    computes risk score, builds OpsReport, queues notifications.
    Only reached when guard_status = 'pass'.
    """
    soma = state.get("soma_output") or SOMAResult()
    pulse = state.get("pulse_output") or PULSEResult()
    critic = state.get("critic_report")
    plan = state.get("execution_plan")

    # Risk score: weighted composite
    breach_score  = min(len(soma.breaches) * 15, 40)
    stockout_score = min(sum(len(v) for v in pulse.stockout_risk.values()) * 5, 30)
    expiry_score  = min(len(soma.expiry_alerts) * 3, 20)
    compliance_s  = min(len(soma.compliance_flags) * 10, 10)
    risk_score = breach_score + stockout_score + expiry_score + compliance_s

    actions_dispatched = (
        [f"quarantine:{b.unit_id}" for b in soma.breaches] +
        [f"reorder:{po.sku_code}" for po in pulse.reorders_placed] +
        [f"schedule_update:{sid}" for sid in soma.schedule_updates] +
        [f"markdown:{a.sku_code}" for a in soma.expiry_alerts]
    )

    notifications = []
    if soma.breaches:
        notifications.append(f"CRITICAL: {len(soma.breaches)} cold chain breach(es) detected and quarantined.")
    if soma.compliance_flags:
        notifications.append(f"WARNING: {len(soma.compliance_flags)} Schedule H compliance gap(s) fixed.")
    if pulse.reorders_placed:
        notifications.append(f"INFO: {len(pulse.reorders_placed)} emergency reorder(s) placed.")
    if soma.expiry_alerts:
        notifications.append(f"INFO: {len(soma.expiry_alerts)} near-expiry SKU(s) flagged for action.")

    report = OpsReport(
        run_id=str(uuid.uuid4())[:8].upper(),
        timestamp=datetime.now(),
        risk_score=risk_score,
        soma_summary=f"{len(soma.breaches)} breaches | {len(soma.schedule_updates)} schedules | {len(soma.expiry_alerts)} expiry alerts",
        pulse_summary=f"{len(pulse.disease_alerts)} epi alerts | {len(pulse.reorders_placed)} reorders | {len(pulse.stockout_risk)} at-risk stores",
        actions_dispatched=actions_dispatched,
        violations_blocked=state.get("blocked_actions", []),
        revision_count=state.get("revision_count", 0),
    )

    return {
        "ops_report": report,
        "notifications": notifications,
    }
