# main.py — FastAPI backend
#
# Run with:  uvicorn main:app --reload --port 8000
# Open:      http://localhost:8000

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import openai

from db import init_db
from agents import PrimaryAgent

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="NexusAI — Intelligent Assistant",
    description="Routes natural language to Task, Notes, and Calendar agents.",
    version="2.0.0",
)

# Allow any frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise DB tables on startup
@app.on_event("startup")
def startup():
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  WARNING: OPENAI_API_KEY is not set! The OpenAI model won't work.")
        print("💡 TIP: Use the Gemini (free) option in the web UI instead.")
    init_db()

# Singleton agent — keeps the OpenAI client alive between requests
agent = PrimaryAgent()


# ── Request / Response models ────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str                        # The user's natural language input
    session: str = "default"            # Optional: isolate conversations per user


class QueryResponse(BaseModel):
    intents: list[str]                  # e.g. ["task", "calendar"]
    response: str                       # Human-readable answer
    history_used: int                   # How many prior turns were included


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """
    Main endpoint.  Accepts a natural language message and returns the
    combined output from all relevant sub-agents.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        result = agent.process(user_input=req.message, session=req.session)
        return QueryResponse(**result)
    except openai.OpenAIError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                "AI service error: "
                "Please check your OpenAI API key, quota, or billing settings."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@app.get("/history")
def history(session: str = "default", limit: int = 10):
    """Return recent conversation history for a session (for debugging)."""
    from db import get_history
    return {"session": session, "history": get_history(session=session, limit=limit)}


@app.delete("/clear")
def clear_history(session: str = "default"):
    """Wipe the conversation log for a session (fresh start)."""
    from db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM conversations WHERE session=?", (session,))
    conn.commit()
    conn.close()
    return {"status": "cleared", "session": session}


# ── Serve the Web UI ─────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"

@app.get("/")
def serve_index():
    """Serve the main web interface."""
    return FileResponse(STATIC_DIR / "index.html")

# Mount static files (CSS, JS, images)
app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")
