import os
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
from datetime import datetime

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

app = FastAPI(title="PharmaIQ API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── RAG Setup ──
DB_PATH = os.path.join(os.path.dirname(__file__), "rag_db")
try:
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)

    RAG_PROMPT = ChatPromptTemplate.from_template(
        """You are the PharmaIQ Assistant. Use the context below from the MedChain \
knowledge base to answer the question. If you don't know, say so — don't make up an answer.
Keep the answer concise and professional.

Context:
{context}

Question: {question}

Helpful Answer:"""
    )

    def _format_docs(docs):
        return "\n\n".join(d.page_content for d in docs)

    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    qa_chain = (
        {"context": retriever | _format_docs, "question": RunnablePassthrough()}
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    RAG_READY = True
except Exception as e:
    print(f"[WARNING] RAG not available — run rag_ingestion.py first. Error: {e}")
    RAG_READY = False
    qa_chain = None


# ── In-memory run cache ──
# Stores the latest full PharmaIQ pipeline state after a /run call.
_latest_run_state: Optional[dict] = None
_latest_run_timestamp: Optional[str] = None


# ── Pydantic Models ──
class ChatQuery(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    answer: str
    source_documents: List[dict] = []

class RunRequest(BaseModel):
    trigger_type: str = Field(default="manual", pattern="^(cron|breach|epi|manual)$")
    store_ids: List[str] = Field(default=["STR-001", "STR-042", "STR-080"])
    priority: str = Field(default="med", pattern="^(low|med|high|critical)$")

class RunResponse(BaseModel):
    run_id: Optional[str]
    risk_score: Optional[float]
    soma_summary: Optional[str]
    pulse_summary: Optional[str]
    actions_dispatched: List[str] = []
    notifications: List[str] = []
    timestamp: Optional[str]


# ── Helper: extract dashboard slices from run state ──

def _soma(state: dict) -> object:
    return state.get("soma_output") or _empty_soma()

def _pulse(state: dict) -> object:
    return state.get("pulse_output") or _empty_pulse()

class _empty_soma:
    breaches = []
    schedule_updates = {}
    compliance_flags = []
    expiry_alerts = []

class _empty_pulse:
    disease_alerts = []
    demand_forecast = {}
    reorders_placed = []
    stockout_risk = {}


# ── Endpoints ──

@app.get("/")
async def root():
    return {
        "message": "PharmaIQ API is running",
        "endpoints": {
            "dashboard": "/dashboard/cold-chain",
            "docs": "/docs"
        }
    }

@app.post("/run", response_model=RunResponse)
async def trigger_run(req: RunRequest):
    """
    Trigger a full PharmaIQ LangGraph pipeline run.
    Runs in a thread to avoid blocking. Caches the result for dashboard reads.
    """
    global _latest_run_state, _latest_run_timestamp
    try:
        from graph import run_pharmaiq
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None,
            lambda: run_pharmaiq(req.trigger_type, req.store_ids, req.priority),
        )
        _latest_run_state = state
        _latest_run_timestamp = datetime.now().isoformat()

        report = state.get("ops_report")
        return RunResponse(
            run_id=report.run_id if report else None,
            risk_score=report.risk_score if report else None,
            soma_summary=report.soma_summary if report else None,
            pulse_summary=report.pulse_summary if report else None,
            actions_dispatched=report.actions_dispatched if report else [],
            notifications=state.get("notifications", []),
            timestamp=_latest_run_timestamp,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {str(e)}")


@app.post("/chat", response_model=ChatResponse)
async def chat(query: ChatQuery):
    if not RAG_READY:
        raise HTTPException(
            status_code=503,
            detail="RAG database not initialized. Run rag_ingestion.py first.",
        )
    try:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None, lambda: qa_chain.invoke(query.message)
        )
        return ChatResponse(answer=answer)
    except Exception as e:
        print(f"[ERROR] /chat: {e}")
        raise HTTPException(status_code=500, detail="Unable to process your request.")


@app.get("/dashboard/cold-chain")
async def get_cold_chain():
    if _latest_run_state:
        soma = _soma(_latest_run_state)
        sensors = []
        for b in soma.breaches:
            sensors.append({
                "id": b.unit_id,
                "store": b.store_id,
                "temp": b.temp_celsius,
                "status": "breach",
            })
        # Add a synthetic "ok" entry for stores with no breach
        breach_stores = {b.store_id for b in soma.breaches}
        store_ids = _latest_run_state.get("store_ids", [])
        for sid in store_ids:
            if sid not in breach_stores:
                sensors.append({"id": f"REF-{sid}-01", "store": sid, "temp": 4.2, "status": "ok"})
        breach_count = len(soma.breaches)
        total = max(len(sensors), 1)
        return {
            "status": "breach" if breach_count else "ok",
            "breach_rate": f"{round((breach_count / total) * 100)}%",
            "active_alerts": breach_count,
            "sensors": sensors,
            "run_timestamp": _latest_run_timestamp,
        }

    # Fallback mock
    return {
        "status": "warning",
        "breach_rate": "22%",
        "active_alerts": 12,
        "sensors": [
            {"id": "CC-001", "store": "Preet Vihar", "temp": 4.2, "status": "ok"},
            {"id": "CC-002", "store": "Preet Vihar", "temp": 8.5, "status": "breach"},
            {"id": "CC-003", "store": "Model Town",  "temp": 3.8, "status": "ok"},
        ],
        "run_timestamp": None,
    }


@app.get("/dashboard/demand")
async def get_demand_signals():
    if _latest_run_state:
        pulse = _pulse(_latest_run_state)
        alerts = [
            {
                "disease": a.disease,
                "zone": a.zone,
                "severity": a.alert_level,
                "skus": a.affected_skus,
            }
            for a in pulse.disease_alerts
        ]
        # Revenue at risk: sum of reorder costs as a proxy
        revenue_at_risk = int(sum(po.estimated_cost_inr for po in pulse.reorders_placed))
        return {
            "alerts": alerts,
            "revenue_at_risk": revenue_at_risk,
            "run_timestamp": _latest_run_timestamp,
        }

    # Fallback mock
    return {
        "alerts": [
            {"disease": "Dengue", "zone": "East Delhi",  "severity": "High",     "skus": ["SKU-102", "SKU-205"]},
            {"disease": "Flu",    "zone": "North Delhi", "severity": "Moderate", "skus": ["SKU-301"]},
        ],
        "revenue_at_risk": 1800000,
        "run_timestamp": None,
    }


@app.get("/dashboard/staffing")
async def get_staffing():
    if _latest_run_state:
        soma = _soma(_latest_run_state)
        total_stores = len(_latest_run_state.get("store_ids", []) or ["placeholder"])
        gaps = [
            {
                "store": f.store_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "reason": f.reason,
            }
            for f in soma.compliance_flags
        ]
        covered = sum(
            1 for p in soma.schedule_updates.values() if p.pharmacist_covered
        )
        pct = round((covered / max(total_stores, 1)) * 100)
        return {
            "coverage": f"{pct}%",
            "gaps": gaps,
            "optimized_shifts": covered,
            "run_timestamp": _latest_run_timestamp,
        }

    # Fallback mock
    return {
        "coverage": "94%",
        "gaps": [{"store": "STR-080", "date": "2026-03-12", "reason": "No Pharmacist for Night Shift"}],
        "optimized_shifts": 450,
        "run_timestamp": None,
    }


@app.get("/dashboard/expiry")
async def get_expiry():
    if _latest_run_state:
        soma = _soma(_latest_run_state)
        items = [
            {
                "sku":   a.sku_name,
                "store": "—",
                "days":  a.days_to_expiry,
                "units": a.stock_units,
                "action": a.recommended_action,
            }
            for a in soma.expiry_alerts
        ]
        est_loss = sum(a.estimated_loss_inr for a in soma.expiry_alerts)
        return {
            "nearing_expiry_count": len(soma.expiry_alerts),
            "est_loss": int(est_loss),
            "items": items,
            "run_timestamp": _latest_run_timestamp,
        }

    # Fallback mock
    return {
        "nearing_expiry_count": 84,
        "est_loss": 450000,
        "items": [
            {"sku": "Atorvastatin 40mg",  "store": "Preet Vihar", "days": 12,   "units": 321},
            {"sku": "Azithromycin 250mg", "store": "Model Town",  "days": -124, "units": 73},
        ],
        "run_timestamp": None,
    }


@app.get("/reports")
async def get_reports():
    if _latest_run_state:
        report = _latest_run_state.get("ops_report")
        if report:
            return [{
                "run_id":    report.run_id,
                "timestamp": report.timestamp.isoformat(),
                "score":     report.risk_score,
                "actions":   len(report.actions_dispatched),
            }]

    # Fallback mock
    return [
        {"run_id": "OPS-A12", "timestamp": "2026-03-10T09:00:00", "score": 82, "actions": 5},
        {"run_id": "OPS-B45", "timestamp": "2026-03-11T10:30:00", "score": 45, "actions": 12},
    ]


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8088)
