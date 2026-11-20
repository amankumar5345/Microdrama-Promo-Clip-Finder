"""
ui/history_sidebar.py
─────────────────────
Sidebar history drawer managing persistent SQLite sessions.
"""

from typing import Optional
import streamlit as st

from db.database import get_db


def render_history_sidebar() -> Optional[str]:
    """
    Render past runs drawer in the sidebar.
    Returns session_id to switch to, or None.
    """
    db = get_db()
    sessions = db.get_sessions(limit=30)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🗂️ Previous Runs")

    if st.sidebar.button("➕ Start New Run", use_container_width=True):
        st.session_state["current_session_id"] = None
        st.session_state["ranked_results"] = None
        st.session_state["current_episode"] = None
        st.session_state["reports_md"] = ""
        st.rerun()

    if not sessions:
        st.sidebar.caption("No saved runs yet.")
        return None

    cur_sid = st.session_state.get("current_session_id")

    for s in sessions:
        sid = s["id"]
        title = s["title"]
        clip_cnt = s.get("clip_count", 0)
        mode = s.get("mode", "")

        is_active = (sid == cur_sid)
        label = f"{'👉 ' if is_active else ''}{title} ({clip_cnt} clips)"

        with st.sidebar.expander(label, expanded=is_active):
            st.caption(f"File: `{s['filename']}` | Mode: {mode}")
            st.caption(f"Date: {s.get('created_at', '')[:16]}")

            col_open, col_del = st.columns([1, 1])
            with col_open:
                if st.button("📂 Load", key=f"load_{sid}", use_container_width=True):
                    return sid
            with col_del:
                if st.button("🗑️ Del", key=f"del_{sid}", use_container_width=True):
                    db.delete_session(sid)
                    if cur_sid == sid:
                        st.session_state["current_session_id"] = None
                        st.session_state["ranked_results"] = None
                    st.toast("Deleted session", icon="🗑️")
                    st.rerun()

    return None
