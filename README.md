# Multi-Agent AI Productivity Assistant

A hackathon-ready multi-agent system built with **FastAPI**, **OpenAI**, **SQLite**, and **Streamlit**.

## Project structure

```
multi_agent_assistant/
├── main.py           # FastAPI app  (POST /query)
├── agents.py         # PrimaryAgent + TaskAgent + NotesAgent + CalendarAgent
├── db.py             # SQLite setup + conversation memory helpers
├── ui.py             # Streamlit frontend
├── requirements.txt
└── .env              # your OPENAI_API_KEY goes here (not committed)
```

## Setup (5 minutes)

### 1. Clone / copy the files
```bash
mkdir multi_agent_assistant && cd multi_agent_assistant
# paste all four .py files here
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set your OpenAI API key
Create a `.env` file:
```
OPENAI_API_KEY=sk-...your-key-here...
```
Then load it before running (or export it directly):
```bash
export OPENAI_API_KEY=sk-...      # Mac/Linux
set OPENAI_API_KEY=sk-...         # Windows CMD
```

### 5. Start the backend (terminal 1)
```bash
uvicorn main:app --reload --port 8000
```
Swagger docs: http://localhost:8000/docs

### 6. Start the frontend (terminal 2)
```bash
streamlit run ui.py
```
Opens at: http://localhost:8501

---

## Example inputs and outputs

| Input | Intents detected | Response |
|---|---|---|
| `Add a task to finish the report` | `[task]` | ✅ Task added: **Finish the report** |
| `Schedule a team meeting tomorrow at 3pm` | `[calendar]` | 📅 Event scheduled: **Team meeting** on 2025-08-15 15:00 |
| `Add a task to review PR and schedule a code review Friday` | `[task, calendar]` | ✅ Task added: **Review PR** ... 📅 Event scheduled: **Code review** on ... |
| `Save a note that the DB password is in 1Password` | `[notes]` | 📝 Note saved: *The DB password is in 1Password* |
| `List all my tasks` | `[task]` | 📋 Your tasks: ⏳ [1] Finish the report ... |
| `What meetings do I have?` | `[calendar]` | 📅 Upcoming events: ... |
| `Mark task 1 as done` | `[task]` | ✅ Marked **Finish the report** as done. |

---

## Architecture overview

```
User input
    │
    ▼
POST /query  (FastAPI)
    │
    ▼
PrimaryAgent
  ├─ load conversation history (SQLite)
  ├─ classify intents (OpenAI gpt-4o-mini)
  │     returns: ["task", "calendar"]
  ├─ dispatch to sub-agents in parallel
  │     TaskAgent     → tasks table
  │     NotesAgent    → notes table
  │     CalendarAgent → calendar_events table
  ├─ smart suggestion (pending task count)
  └─ save exchange to conversations table
    │
    ▼
Combined response  →  Streamlit UI
```

## Advanced features included

- **Multi-step workflow handling** — a single sentence like "Add a task and schedule a meeting" is split into multiple intents and handled independently.
- **Basic memory** — the last 8 conversation turns are loaded into the LLM context on every request, enabling follow-up questions.
- **Smart suggestions** — after every response, the system checks for pending tasks and surfaces a reminder if there are any.

## Demo talking points (for judges)

1. **Multi-agent coordination**: one natural language input → intent classifier → multiple sub-agents → single coherent response.
2. **Persistence**: all data survives restarts (SQLite file on disk).
3. **Memory**: the assistant remembers what you said earlier in the session.
4. **Extensibility**: adding a new agent takes ~40 lines — just add a class in `agents.py` and register it in `PrimaryAgent.process()`.
5. **Clean separation**: each file has a single responsibility, making it easy to demo and explain.
