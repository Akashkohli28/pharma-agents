#Pharma

The project has 3 simple parts
Part 1 — The Website (frontend folder)
This is what you see in the browser. A React app built with Vite. It shows 4 cards (cold chain, demand, staffing, expiry) and has a chatbot. When you click "Run Pipeline", it sends a signal to the backend.
Part 2 — The Backend Server (main.py)
Built with FastAPI (a Python web framework). It receives requests from the frontend and exposes endpoints like /run, /chat, /dashboard/cold-chain, etc. Think of it as the receptionist who takes your request and hands it to the right department.
Part 3 — The AI Brain (agents.py + graph.py)
This is where the real work happens. It's a chain of 6 AI agents that run one after another (with some running in parallel).

The 6 agents explained simply
AgentWhat it doesReal-world jobPlannerDecides what needs to be checked today and sets rulesOperations ManagerSOMAChecks fridges, staff, and drug expiry across all storesStore InspectorPULSEChecks disease outbreaks and predicts which medicines will run outEpidemiologist + Procurement OfficerCriticReviews everything SOMA and PULSE decided to doQuality AuditorGuardrailEnforces strict rules (e.g. no huge orders without approval)Compliance OfficerAggregatorCombines everything into a final report and dashboard updateReport Writer

The key files and what they actually are
state.py — Think of this as a shared notepad that all 6 agents can read and write. It defines what information exists in the system — things like "what is a temperature breach?" or "what does a purchase order look like?" Every piece of data has a clearly defined shape (called a dataclass).
agents.py — Contains the actual Python functions for each agent. For example, soma_node() creates an AI agent using create_react_agent(), gives it tools like "poll sensors" and "quarantine batch", and runs it. The agent automatically decides which tool to call and in what order (this is called ReAct — Reasoning + Acting).
graph.py — This wires all agents together in the correct sequence using LangGraph. The key insight: SOMA and PULSE run at the same time (parallel). Then they both feed into the Critic. If the Guardrail rejects the actions, the whole process loops back to the Planner (max 3 times) before giving up and asking a human.
mcp_tools.py — These are the tools the AI agents use, like a toolkit. For example, poll_sensors() fetches fridge temperatures, trigger_reorder() places an order, fetch_idsp_feed() checks disease outbreak data from the government's IDSP system. Right now they return dummy/mock data, but in production they'd call real APIs.
rag_ingestion.py — Reads the Excel file (MedChain_PharmaIQ_DummyData.xlsx), converts every row into text, and stores it in a ChromaDB database (a local vector database). This is so the chatbot can answer questions like "what is the stock level of Atorvastatin?" by searching the database.
main.py — The chatbot (/chat endpoint) searches that ChromaDB database, sends the results to Gemini, and returns an answer. This is called RAG (Retrieval-Augmented Generation) — instead of the AI guessing, it first looks up the actual data.
prompts/ folder — Text files containing the instructions given to each AI agent. For example, soma_system.txt tells SOMA: "When you detect a breach, quarantine the batch immediately — don't just report it, ACT." These are the agent's personalities and rules.

The most important concept — the feedback loop
Planner → SOMA + PULSE → Critic → Guardrail
                                      |
                    If rules broken ──┘ (loops back to Planner, max 3 times)
                                      |
                    If rules pass ────→ Aggregator → Dashboard updates
