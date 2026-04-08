# agents.py — All agent logic lives here
#
# Architecture:
#   PrimaryAgent  →  classifies intent with OpenAI
#                 →  routes to one or more sub-agents
#   TaskAgent     →  CRUD on the `tasks` table
#   NotesAgent    →  CRUD on the `notes` table
#   CalendarAgent →  CRUD on the `calendar_events` table

import json
import re
import sqlite3
from datetime import datetime, timedelta
import openai
from db import get_connection, get_history, save_message

# ---------------------------------------------------------------------------
# OpenAI client (reads OPENAI_API_KEY from the environment automatically)
# ---------------------------------------------------------------------------
client = openai.OpenAI()
MODEL = "gpt-4o-mini"   # fast + cheap; swap to "gpt-4o" for richer reasoning


# ═══════════════════════════════════════════════════════════════════════════
#  TASK AGENT
# ═══════════════════════════════════════════════════════════════════════════

class TaskAgent:
    """Handles task management: add, update, list, complete."""

    def handle(self, user_input: str) -> str:
        """Parse the user's intent for tasks and call the right method."""
        lowered = user_input.lower()

        if any(w in lowered for w in ["complete", "done", "mark"]) and (
            "task" in lowered or "tasks" in lowered or any(ch.isdigit() for ch in lowered)
        ):
            return self._complete_task(user_input)
        elif any(w in lowered for w in ["list", "show", "what tasks", "pending", "all tasks"]):
            return self._list_tasks()
        else:
            # Default: treat the input as a new task to add
            return self._add_task(user_input)

    # ── internal helpers ────────────────────────────────────────────────────

    def _add_task(self, user_input: str) -> str:
        """Extract a task title (via LLM) and insert into the DB."""
        # Ask the LLM to pull out the task title cleanly
        prompt = (
            f"Extract only the task title from this message. "
            f"Reply with the title only, no extra text.\n\nMessage: {user_input}"
        )
        title = self._quick_completion(prompt).strip().strip('"')

        # Check for a deadline keyword and set a simple relative date
        deadline = self._extract_deadline(user_input)

        conn = get_connection()
        conn.execute(
            "INSERT INTO tasks (title, status, deadline) VALUES (?, 'pending', ?)",
            (title, deadline)
        )
        conn.commit()
        conn.close()

        suffix = f" (due: {deadline})" if deadline else ""
        return f"✅ Task added: **{title}**{suffix}"

    def _list_tasks(self) -> str:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, status, deadline FROM tasks ORDER BY id DESC LIMIT 20"
        ).fetchall()
        conn.close()

        if not rows:
            return "📋 No tasks found. Add one by saying 'Add a task to...'."

        lines = ["📋 **Your tasks:**\n"]
        for r in rows:
            icon = "✅" if r["status"] == "done" else "⏳"
            deadline_str = f"  _(due {r['deadline']})_" if r["deadline"] else ""
            lines.append(f"{icon} [{r['id']}] {r['title']}{deadline_str}")
        return "\n".join(lines)

    def _complete_task(self, user_input: str) -> str:
        """Try to match a task ID or title and mark it done."""
        # Extract an ID if present
        import re
        match = re.search(r"\b(\d+)\b", user_input)
        conn = get_connection()

        if match:
            task_id = int(match.group(1))
            row = conn.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                conn.execute("UPDATE tasks SET status='done' WHERE id=?", (task_id,))
                conn.commit()
                conn.close()
                return f"✅ Marked task **{row['title']}** as done."

        # Fallback: mark the most recent pending task done
        row = conn.execute(
            "SELECT id, title FROM tasks WHERE status='pending' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            conn.execute("UPDATE tasks SET status='done' WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            return f"✅ Marked **{row['title']}** as done."

        conn.close()
        return "❌ Couldn't find a matching task to complete."

    def _extract_deadline(self, text: str) -> str | None:
        """Very simple deadline extraction — returns an ISO date or None."""
        lower = text.lower()
        today = datetime.now().date()
        if "tomorrow" in lower:
            return str(today + timedelta(days=1))
        if "next week" in lower:
            return str(today + timedelta(weeks=1))
        if "today" in lower:
            return str(today)
        return None

    def _quick_completion(self, prompt: str) -> str:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0,
            )
            return resp.choices[0].message.content.strip()
        except openai.OpenAIError as e:
            print(f"[agents] OpenAI fallback in TaskAgent._quick_completion: {e}")
            return self._fallback_task_title(prompt)

    def _fallback_task_title(self, prompt: str) -> str:
        if "Message:" in prompt:
            text = prompt.split("Message:", 1)[1].strip()
        else:
            text = prompt

        for phrase in ["add a task to", "add task to", "add a task", "add task", "please"]:
            text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)

        title = " ".join(text.split()).strip(' ."\'')
        return title or "New task"

    def get_pending_summary(self) -> str:
        """Return a brief count of pending tasks (used for smart suggestions)."""
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
        return f"You have **{count}** pending task(s)." if count else ""


# ═══════════════════════════════════════════════════════════════════════════
#  NOTES AGENT
# ═══════════════════════════════════════════════════════════════════════════

class NotesAgent:
    """Handles note saving and retrieval."""

    def handle(self, user_input: str) -> str:
        lowered = user_input.lower()

        if any(w in lowered for w in ["show", "list", "get", "retrieve", "read", "what notes"]):
            return self._list_notes()
        else:
            return self._save_note(user_input)

    def _save_note(self, user_input: str) -> str:
        """Extract the note content and save it."""
        prompt = (
            "Extract the note content the user wants to save. "
            "Remove phrases like 'note that', 'save a note', 'remember that'. "
            "Return only the clean note text.\n\n"
            f"Message: {user_input}"
        )
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0,
            )
            content = resp.choices[0].message.content.strip().strip('"')
        except openai.OpenAIError as e:
            print(f"[agents] OpenAI fallback in NotesAgent._save_note: {e}")
            content = self._fallback_note_content(user_input)

        conn = get_connection()
        conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        conn.commit()
        conn.close()
        return f"📝 Note saved: *{content}*"

    def _fallback_note_content(self, text: str) -> str:
        content = text
        for phrase in ["save a note that", "save a note", "note that", "save note", "remember that", "remember"]:
            content = re.sub(re.escape(phrase), "", content, flags=re.IGNORECASE)
        content = " ".join(content.split()).strip(' ."\'')
        return content or text.strip()

    def _list_notes(self) -> str:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, content, created FROM notes ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()

        if not rows:
            return "📝 No notes yet. Say 'Save a note that...' to add one."

        lines = ["📝 **Your recent notes:**\n"]
        for r in rows:
            date_str = r["created"][:10]  # YYYY-MM-DD
            lines.append(f"• [{r['id']}] {r['content']}  _({date_str})_")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  CALENDAR AGENT
# ═══════════════════════════════════════════════════════════════════════════

class CalendarAgent:
    """Handles scheduling events on the calendar."""

    def handle(self, user_input: str) -> str:
        lowered = user_input.lower()

        if any(w in lowered for w in ["show", "list", "what events", "schedule", "upcoming"]):
            # "show schedule" or "list events" → list mode
            if not any(w in lowered for w in ["add", "create", "book", "set up", "schedule a"]):
                return self._list_events()

        return self._schedule_event(user_input)

    def _schedule_event(self, user_input: str) -> str:
        """Use LLM to extract event title + datetime, then save."""
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = (
            f"Today is {today}. Extract the event title and date/time from this message. "
            "Reply with JSON only, no extra text, in this format:\n"
            '{"title": "...", "event_time": "YYYY-MM-DD HH:MM"}\n\n'
            f"Message: {user_input}"
        )
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
        except openai.OpenAIError as e:
            print(f"[agents] OpenAI fallback in CalendarAgent._schedule_event: {e}")
            return self._fallback_schedule_event(user_input)

        try:
            # Strip possible markdown fences
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            title = data.get("title", "Untitled event")
            event_time = data.get("event_time", f"{today} 09:00")
        except (json.JSONDecodeError, KeyError):
            # Graceful fallback
            title = "Meeting"
            event_time = f"{today} 09:00"

        conn = get_connection()
        conn.execute(
            "INSERT INTO calendar_events (title, event_time) VALUES (?, ?)",
            (title, event_time)
        )
        conn.commit()
        conn.close()
        return f"📅 Event scheduled: **{title}** on {event_time}"

    def _fallback_schedule_event(self, user_input: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        title = user_input
        for phrase in ["schedule", "set up", "book", "create"]:
            title = re.sub(re.escape(phrase), "", title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip(' ."\'')
        if not title:
            title = "Meeting"
        event_time = f"{today} 09:00"

        conn = get_connection()
        conn.execute(
            "INSERT INTO calendar_events (title, event_time) VALUES (?, ?)",
            (title, event_time)
        )
        conn.commit()
        conn.close()
        return f"📅 Event scheduled: **{title}** on {event_time}"

    def _list_events(self) -> str:
        conn = get_connection()
        rows = conn.execute(
            "SELECT title, event_time FROM calendar_events ORDER BY event_time ASC LIMIT 10"
        ).fetchall()
        conn.close()

        if not rows:
            return "📅 No upcoming events. Say 'Schedule a meeting...' to add one."

        lines = ["📅 **Upcoming events:**\n"]
        for r in rows:
            lines.append(f"• {r['event_time']}  —  {r['title']}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  PRIMARY AGENT  (the controller)
# ═══════════════════════════════════════════════════════════════════════════

class PrimaryAgent:
    """
    The orchestrator.

    1. Loads conversation history (basic memory).
    2. Calls OpenAI to classify which agents are needed.
    3. Dispatches to each sub-agent.
    4. Aggregates results and appends a smart suggestion if relevant.
    5. Saves the exchange to the conversation log.
    """

    def __init__(self):
        self.task_agent = TaskAgent()
        self.notes_agent = NotesAgent()
        self.calendar_agent = CalendarAgent()

    def process(self, user_input: str, session: str = "default") -> dict:
        """
        Main entry point called by FastAPI.
        Returns {"intents": [...], "response": "...", "history_used": int}
        """
        # 1. Load recent conversation history for context
        history = get_history(session=session, limit=8)
        history_count = len(history)

        # 2. Classify intent(s)
        intents = self._classify_intents(user_input, history)

        # 3. Dispatch and collect responses
        responses = []
        for intent in intents:
            try:
                if intent == "task":
                    responses.append(self.task_agent.handle(user_input))
                elif intent == "notes":
                    responses.append(self.notes_agent.handle(user_input))
                elif intent == "calendar":
                    responses.append(self.calendar_agent.handle(user_input))
                elif intent == "general":
                    responses.append(self._general_response(user_input, history))
            except openai.OpenAIError as e:
                print(f"[agents] OpenAI fallback in PrimaryAgent.process for intent {intent}: {e}")
                responses.append(
                    "❌ The AI service is unavailable right now. "
                    "Please try again later or use a simpler command."
                )

        if not responses:
            # Fallback if classification returned nothing usable
            responses.append(self._general_response(user_input, history))
            intents = ["general"]

        # 4. Smart suggestion: remind user of pending tasks
        suggestion = self.task_agent.get_pending_summary()
        if suggestion and "task" not in intents:
            responses.append(f"\n💡 **Suggestion:** {suggestion}")

        full_response = "\n\n".join(responses)

        # 5. Persist this exchange
        save_message("user", user_input, session)
        save_message("assistant", full_response, session)

        return {
            "intents": intents,
            "response": full_response,
            "history_used": history_count,
        }

    # ── private helpers ─────────────────────────────────────────────────────

    def _classify_intents(self, user_input: str, history: list[dict]) -> list[str]:
        """
        Ask GPT to return a JSON list of intents from:
        ["task", "notes", "calendar", "general"]
        """
        system = (
            "You are an intent classifier for a productivity assistant. "
            "Given a user message, return a JSON array of applicable intents. "
            "Valid intents: task, notes, calendar, general. "
            "Return ONLY a JSON array, e.g. [\"task\", \"calendar\"]. "
            "No explanation, no markdown, no extra text."
        )

        # Include recent history so the LLM has context
        messages = [{"role": "system", "content": system}]
        messages.extend(history[-4:])  # last 4 turns max
        messages.append({"role": "user", "content": user_input})

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=30,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()

            intents = json.loads(raw)
            # Validate — only keep known intents
            valid = {"task", "notes", "calendar", "general"}
            return [i for i in intents if i in valid] or ["general"]
        except openai.OpenAIError as e:
            print(f"[agents] OpenAI fallback in PrimaryAgent._classify_intents: {e}")
            return self._basic_intent_classification(user_input)
        except json.JSONDecodeError:
            return ["general"]

    def _general_response(self, user_input: str, history: list[dict]) -> str:
        """For chit-chat or ambiguous queries, respond conversationally."""
        system = (
            "You are a friendly productivity assistant. "
            "You help users manage tasks, notes, and calendar events. "
            "Keep replies concise and helpful."
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(history[-4:])
        messages.append({"role": "user", "content": user_input})

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except openai.OpenAIError as e:
            print(f"[agents] OpenAI fallback in PrimaryAgent._general_response: {e}")
            return (
                "I'm unable to reach the AI service right now. "
                "Please try again later, or simplify your request."
            )

    def _basic_intent_classification(self, user_input: str) -> list[str]:
        lowered = user_input.lower()
        intents = []

        if any(w in lowered for w in ["task", "todo", "complete", "done", "finish", "mark", "list tasks", "pending"]):
            intents.append("task")
        if any(w in lowered for w in ["note", "notes", "remember", "save a note", "show notes"]):
            intents.append("notes")
        if any(w in lowered for w in ["calendar", "meeting", "schedule", "event", "upcoming"]):
            intents.append("calendar")
        if not intents:
            intents = ["general"]

        return intents
