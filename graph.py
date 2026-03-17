"""
pharmaiq/graph.py
──────────────────
Assembles the full PharmaIQ LangGraph StateGraph.

Flow:
  START
    → orchestrator_router          (decides initial routing)
    → planner_node                 (builds / revises execution plan)
    → [soma_node ∥ pulse_node]     (parallel fan-out)
    → critic_node                  (quality review)
    → guardrail_node               (compliance check)
    → aggregator_node  (PASS)      (merge + dispatch)
    → END

    ↑_________guardrail FAIL_______↓  (loop back to planner, max 3x)
"""

from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from state import PharmaIQState
from agents import (
    planner_node,
    soma_node,
    pulse_node,
    critic_node,
    guardrail_node,
    aggregator_node,
)


# ──────────────────────────────────────────────
# Conditional edge: after Guardrail
# ──────────────────────────────────────────────

def guard_router(state: PharmaIQState) -> str:
    """
    Routes after guardrail_node:
      pass      → aggregator  (happy path)
      fail      → planner     (revision loop)
      escalate  → END         (human review queue — handle externally)
    """
    status = state.get("guard_status", "pass")
    if status == "pass":
        return "aggregator"
    elif status == "fail":
        return "planner"
    else:  # escalate
        return END


# ──────────────────────────────────────────────
# Parallel fan-out helper
# LangGraph runs nodes listed in Send() concurrently
# Here we use a simple router that triggers both agents
# ──────────────────────────────────────────────

def execution_router(state: PharmaIQState) -> list[str]:
    """
    After planner: decide which agent nodes to activate.
    Returns a list of node names — LangGraph runs them in parallel
    when multiple names are returned from a conditional edge.
    """
    plan = state.get("execution_plan")
    if not plan:
        return ["soma"]

    nodes = []
    if "soma" in plan.agents_to_run:
        nodes.append("soma")
    if "pulse" in plan.agents_to_run:
        nodes.append("pulse")

    return nodes if nodes else ["soma"]


# ──────────────────────────────────────────────
# Build the graph
# ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(PharmaIQState)

    # ── Register nodes ──
    builder.add_node("planner",    planner_node)
    builder.add_node("soma",       soma_node)
    builder.add_node("pulse",      pulse_node)
    builder.add_node("critic",     critic_node)
    builder.add_node("guardrail",  guardrail_node)
    builder.add_node("aggregator", aggregator_node)

    # ── Edges ──

    # Entry
    builder.add_edge(START, "planner")

    # Planner → parallel fan-out (soma and/or pulse)
    builder.add_conditional_edges(
        "planner",
        execution_router,
        {
            "soma":  "soma",
            "pulse": "pulse",
        }
    )

    # Both agents converge at critic
    builder.add_edge("soma",  "critic")
    builder.add_edge("pulse", "critic")

    # Critic → Guardrail
    builder.add_edge("critic", "guardrail")

    # Guardrail → branch (pass/fail/escalate)
    builder.add_conditional_edges(
        "guardrail",
        guard_router,
        {
            "aggregator": "aggregator",
            "planner":    "planner",
            END:          END,
        }
    )

    # Aggregator → done
    builder.add_edge("aggregator", END)

    return builder


# ──────────────────────────────────────────────
# Compile with checkpointer (state persistence)
# ──────────────────────────────────────────────

def compile_graph():
    """
    Compile the graph with an in-memory checkpointer.
    Swap MemorySaver for SqliteSaver / RedisSaver in production.
    """
    builder = build_graph()
    memory  = MemorySaver()
    graph   = builder.compile(checkpointer=memory)
    return graph


# ──────────────────────────────────────────────
# Entry point helpers
# ──────────────────────────────────────────────

def run_pharmaiq(
    trigger_type: str,
    store_ids: list[str],
    priority: str = "med",
) -> dict:
    """
    Main entry point for a PharmaIQ run.

    Args:
        trigger_type:  'cron' | 'breach' | 'epi' | 'manual'
        store_ids:     list of store IDs to process
        priority:      'low' | 'med' | 'high' | 'critical'

    Returns:
        Final state dict with ops_report and notifications.
    """
    from datetime import datetime

    graph = compile_graph()

    initial_state: PharmaIQState = {
        "trigger_type":    trigger_type,
        "timestamp":       datetime.now(),
        "store_ids":       store_ids,
        "priority":        priority,
        "execution_plan":  None,
        "soma_output":     None,
        "pulse_output":    None,
        "epi_context":     [],
        "critic_report":   None,
        "guard_status":    None,
        "guard_violations": [],
        "blocked_actions": [],
        "revision_count":  0,
        "ops_report":      None,
        "notifications":   [],
    }

    # Thread ID enables state persistence / resumption
    config = {"configurable": {"thread_id": f"run-{trigger_type}-{store_ids[0]}"}}

    final_state = graph.invoke(initial_state, config=config)
    return final_state


# ──────────────────────────────────────────────
# Stream version (for real-time UI updates)
# ──────────────────────────────────────────────

def stream_pharmaiq(trigger_type: str, store_ids: list[str], priority: str = "med"):
    """
    Streaming version — yields node-by-node updates.
    Useful for dashboard real-time display.

    Usage:
        for event in stream_pharmaiq("breach", ["STR-042"], "critical"):
            print(event)
    """
    from datetime import datetime

    graph = compile_graph()

    initial_state: PharmaIQState = {
        "trigger_type":    trigger_type,
        "timestamp":       datetime.now(),
        "store_ids":       store_ids,
        "priority":        priority,
        "execution_plan":  None,
        "soma_output":     None,
        "pulse_output":    None,
        "epi_context":     [],
        "critic_report":   None,
        "guard_status":    None,
        "guard_violations": [],
        "blocked_actions": [],
        "revision_count":  0,
        "ops_report":      None,
        "notifications":   [],
    }

    config = {"configurable": {"thread_id": f"stream-{trigger_type}"}}

    for event in graph.stream(initial_state, config=config, stream_mode="updates"):
        yield event
