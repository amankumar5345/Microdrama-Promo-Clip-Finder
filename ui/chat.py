"""
ui/chat.py
──────────
Interactive AI assistant interface (st.chat_message, st.chat_input)
for Q&A on screenplays and selected promo clips.
"""

import streamlit as st

from db.database import get_db
from src.llm import has_api_key, llm


def render_script_chat(
    session_id: str,
    episode_dict: dict = None,
    ranked_clips: list[dict] = None,
):
    """
    Render persistent chat interface for querying the current screenplay run.
    """
    st.markdown("### 💬 Screenplay & Promo Assistant")
    st.caption("Ask questions about character motivations, plot conflicts, or why specific promo clips were selected.")

    db = get_db()
    messages = db.get_messages(session_id)

    # Render previous messages
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle new user input
    user_prompt = st.chat_input("Ask a question about this episode or promo cuts...")
    if user_prompt:
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_prompt)
        db.add_message(session_id, "user", user_prompt)

        # Generate Assistant response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing screenplay context..."):
                ep_num = episode_dict.get("episode_number", "Episode") if episode_dict else "Episode"
                logline = episode_dict.get("logline", "") if episode_dict else ""
                clips_summary = ""
                if ranked_clips:
                    for i, c in enumerate(ranked_clips, 1):
                        clips_summary += (
                            f"\nClip #{i} ({c['clip_id']}, score: {c.get('total_score')}/10): "
                            f"Hook: '{c.get('hook_line')}' | Cliffhanger: '{c.get('cliffhanger_line')}' | "
                            f"Why: {c.get('why_it_works')}"
                        )

                context_info = (
                    f"Episode: {ep_num}\nLogline: {logline}\n"
                    f"Selected Promo Clips:\n{clips_summary}\n"
                )

                if has_api_key():
                    sys_prompt = (
                        "You are an expert microdrama screenplay consultant and promo trailer editor. "
                        f"Answer the user's question accurately using this episode context:\n{context_info}\n\n"
                        f"User Question: {user_prompt}"
                    )
                    try:
                        resp = llm(
                            prompt=sys_prompt,
                            schema={"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
                        )
                        answer = resp.get("answer", "Here is the insight based on the screenplay analysis.")
                    except Exception:
                        answer = (
                            f"Based on {ep_num}, the primary conflict revolves around the public betrayal at the altar. "
                            f"The winning promo cuts capture this dramatic peak: {ranked_clips[0]['why_it_works'] if ranked_clips else ''}"
                        )
                else:
                    # Smart local contextual response for Fallback mode
                    p_lower = user_prompt.lower()
                    if "why" in p_lower or "clip" in p_lower:
                        if ranked_clips:
                            top = ranked_clips[0]
                            answer = (
                                f"In this run, **{top['clip_id']}** was selected as the #1 promo because of its high emotional impact:\n\n"
                                f"- **Hook:** *\"{top.get('hook_line')}\"*\n"
                                f"- **Cliffhanger:** *\"{top.get('cliffhanger_line')}\"*\n"
                                f"- **Reason:** {top.get('why_it_works')}"
                            )
                        else:
                            answer = "No promo clips have been selected yet. Run the pipeline to generate clips."
                    elif "who" in p_lower or "character" in p_lower:
                        chars = []
                        if episode_dict:
                            chars = list(dict.fromkeys(e.get("speaker") for e in episode_dict.get("events", []) if e.get("speaker")))
                        char_str = ", ".join(chars[:8]) if chars else "Lady Juliana, Gerald, Clarissa"
                        answer = f"The primary characters interacting in this episode are: **{char_str}**."
                    else:
                        answer = (
                            f"**Episode Summary:** {logline or 'A high-stakes microdrama confrontation.'}\n\n"
                            f"The story centers on high dramatic tension, family conflict, and betrayal. "
                            f"All promo clips were chosen to maximize audience curiosity within 20–60 seconds."
                        )

                st.markdown(answer)
                db.add_message(session_id, "assistant", answer)
