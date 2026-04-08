# ui.py — Streamlit frontend
#
# Run with:  streamlit run ui.py
# Requires the FastAPI backend to be running on localhost:8000

import streamlit as st
import requests
import uuid

API_URL = "http://localhost:8000"

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Productivity Assistant",
    page_icon="🤖",
    layout="centered",
)

# ── Session state ─────────────────────────────────────────────────────────────
# Generate a unique session ID per browser tab so histories don't collide
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "messages" not in st.session_state:
    st.session_state.messages = []   # list of {role, content, intents}

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 AI Productivity Assistant")
st.caption(
    "Powered by a multi-agent system — manages **tasks**, **notes**, and **calendar** events. "
    "Try combining them in one sentence!"
)

# ── Sidebar: quick commands and session info ──────────────────────────────────
with st.sidebar:
    st.header("Quick commands")
    examples = [
        "Add a task to finish the report by tomorrow",
        "Save a note that the API key is in the .env file",
        "Schedule a team meeting tomorrow at 3pm",
        "Add a task to review PR and schedule a code review Friday",
        "List all my tasks",
        "Show my notes",
        "Show upcoming events",
        "Mark task 1 as done",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state._prefill = ex

    st.divider()
    st.caption(f"Session: `{st.session_state.session_id}`")

    if st.button("🗑️ Clear history", use_container_width=True):
        try:
            requests.delete(f"{API_URL}/clear", params={"session": st.session_state.session_id})
        except Exception:
            pass
        st.session_state.messages = []
        st.rerun()

# ── Chat history display ──────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("intents"):
            badge_html = " ".join(
                f'<span style="background:#e8eaf6;color:#3949ab;'
                f'border-radius:4px;padding:2px 8px;font-size:12px;'
                f'margin-right:4px">#{i}</span>'
                for i in msg["intents"]
            )
            st.markdown(badge_html, unsafe_allow_html=True)

# ── Input box ─────────────────────────────────────────────────────────────────
# Use sidebar prefill if a quick command was clicked
prefill_value = st.session_state.pop("_prefill", "")

user_input = st.chat_input(
    "Type your request…  e.g. 'Add a task and schedule a meeting tomorrow'",
)

# Merge prefill + direct input (prefill takes priority)
final_input = prefill_value or user_input

if final_input:
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": final_input})
    with st.chat_message("user"):
        st.markdown(final_input)

    # Call the FastAPI backend
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                resp = requests.post(
                    f"{API_URL}/query",
                    json={"message": final_input, "session": st.session_state.session_id},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                response_text = data["response"]
                intents = data["intents"]
                history_used = data["history_used"]

                # Display assistant reply
                st.markdown(response_text)

                # Show intent badges
                badge_html = " ".join(
                    f'<span style="background:#e8eaf6;color:#3949ab;'
                    f'border-radius:4px;padding:2px 8px;font-size:12px;'
                    f'margin-right:4px">#{i}</span>'
                    for i in intents
                )
                st.markdown(badge_html, unsafe_allow_html=True)
                st.caption(f"🧠 Memory: {history_used} prior turn(s) in context")

                # Save to local display history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "intents": intents,
                })

            except requests.exceptions.ConnectionError:
                st.error(
                    "❌ Cannot reach the backend. "
                    "Make sure you ran:  `uvicorn main:app --reload --port 8000`"
                )
            except requests.exceptions.HTTPError as e:
                st.error(f"❌ API error: {e.response.text}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Multi-Agent AI Productivity Assistant · FastAPI + OpenAI + SQLite + Streamlit")
