"""
llm_agent.py
────────────
Phase 3B — LangChain / ChatOpenAI helpers.

  get_llm()                  — instantiate ChatOpenAI from env / secrets
  build_langchain_messages() — convert st.session_state chat history →
                               LangChain message objects (with system prompt)

No Streamlit rendering lives here; only model setup and message conversion.
"""

import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import RDTI_SYSTEM_PROMPT


def get_llm(api_key: str = "") -> ChatOpenAI:
    """
    Instantiate a ChatOpenAI client.

    API key resolution order:
      1. `api_key` argument (passed in from Streamlit secrets at call-site)
      2. OPENAI_API_KEY environment variable

    Raises:
        ValueError if no key is found (caller should surface this to the UI).

    Returns:
        ChatOpenAI configured for gpt-4o at temperature=0.3.
    """
    resolved_key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not resolved_key:
        raise ValueError(
            "No OpenAI API key found. "
            "Set OPENAI_API_KEY in .env or .streamlit/secrets.toml."
        )
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        openai_api_key=resolved_key,
    )


def build_langchain_messages(session_messages: list[dict]) -> list:
    """
    Convert the Streamlit session-state message list into LangChain objects.

    The system prompt (RDTI_SYSTEM_PROMPT) is always prepended so every API
    call carries the full instruction context — compensating for LangChain's
    stateless nature and Streamlit's script-rerun model.

    Memory architecture:
        st.session_state["messages"] is the single source of truth.
        This function is a pure transformer: list[dict] → list[BaseMessage].
        It is called once per user turn, just before llm.invoke().

    Args:
        session_messages: [{"role": "user"|"assistant", "content": str}, ...]

    Returns:
        [SystemMessage, HumanMessage | AIMessage, ...]
    """
    lc_msgs: list = [SystemMessage(content=RDTI_SYSTEM_PROMPT)]

    for msg in session_messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lc_msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_msgs.append(AIMessage(content=content))
        # Silently skip unknown roles

    return lc_msgs
