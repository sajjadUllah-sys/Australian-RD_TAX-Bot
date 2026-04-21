"""
app.py
──────
Streamlit entry point — UI rendering only.

Run:
    streamlit run app.py

All business logic lives in separate modules:
    config.py          — constants, form specs, system prompt
    abn_validator.py   — Modulo-89 checksum + ABR API mock
    llm_agent.py       — LangChain / ChatOpenAI setup
    report_builder.py  — report text compilation + PDF generation
    backend_client.py  — Django backend POST
    styles.py          — CSS injection
"""

import asyncio
import os
import re

import streamlit as st
from dotenv import load_dotenv

# ── Load environment variables from .env ─────────────────────────────────────
load_dotenv()

# ── Local modules ─────────────────────────────────────────────────────────────
from abn_validator  import validate_abn_modulo89, mock_abr_api_call
from backend_client import post_to_django_backend
from config         import (
    CONTINUING_FIELDS,
    INDUSTRY_OPTIONS,
    PROJECT_YEARS,
    STEPS,
)
from llm_agent      import build_langchain_messages, get_llm
from report_builder import (
    compile_report_from_chat,
    compile_report_from_form,
    generate_pdf,
)
from styles         import inject_css

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be the very first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RDTI AI Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─────────────────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────────────────

def init_state() -> None:
    """Seed st.session_state with default values on first run."""
    defaults = {
        "phase":            "intake",   # intake | abn_check | continuing | new_project | report
        "intake":           {},         # Phase 1 form data
        "abn_valid":        False,
        "abn_result":       {},
        "messages":         [],         # Phase 3B chat history  [{role, content}]
        "interview_done":   False,
        "chat_summary":     "",
        "form_answers":     {},         # Phase 3A text-area answers
        "report_text":      "",
        "pdf_bytes":        None,
        "backend_response": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# Shared UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def render_step_bar(active_step: int) -> None:
    """Render the 4-segment progress bar above each phase."""
    bars = ""
    for i, label in enumerate(STEPS):
        cls = "done" if i < active_step else ("active" if i == active_step else "")
        bars += f'<div class="step {cls}" title="{label}"></div>'
    st.markdown(
        f'<div class="step-bar">{bars}</div>'
        f'<p style="color:var(--muted);font-size:0.8rem;margin-top:-0.8rem;">'
        f'Step {active_step + 1} of {len(STEPS)}: '
        f'<strong style="color:var(--text)">{STEPS[active_step]}</strong></p>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Intake form
# ─────────────────────────────────────────────────────────────────────────────

def render_intake() -> None:
    render_step_bar(0)
    st.markdown("## 🔬 RDTI Application Intake")
    st.markdown(
        '<p style="color:var(--muted)">Complete the fields below to begin your '
        "R&D Tax Incentive application assessment.</p>",
        unsafe_allow_html=True,
    )

    with st.form("intake_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company Name *",  placeholder="Acme Biotech Pty Ltd")
            abn          = st.text_input("ABN *",           placeholder="51 824 753 556", max_chars=14)
            industry     = st.selectbox("Industry *",       list(INDUSTRY_OPTIONS.keys()))
        with col2:
            contact_person = st.text_input("Contact Person *", placeholder="Jane Smith")
            project_year   = st.selectbox("Project Year *",    PROJECT_YEARS)
            project_type   = st.radio(
                "Project Type *",
                ["Continuing Project", "New Project"],
                horizontal=True,
            )

        submitted = st.form_submit_button("Validate & Continue →", use_container_width=True)

    if submitted:
        errors = []
        if not company_name.strip():
            errors.append("Company Name is required.")
        if not contact_person.strip():
            errors.append("Contact Person is required.")
        abn_clean = re.sub(r"\s", "", abn)
        if not abn_clean.isdigit() or len(abn_clean) != 11:
            errors.append("ABN must contain exactly 11 digits (spaces allowed).")

        if errors:
            for e in errors:
                st.markdown(f'<p class="val-error">⚠ {e}</p>', unsafe_allow_html=True)
        else:
            st.session_state["intake"] = {
                "company_name":  company_name.strip(),
                "contact_person": contact_person.strip(),
                "abn":           abn_clean,
                "industry":      industry,
                "project_year":  project_year,
                "project_type":  project_type,
            }
            st.session_state["phase"] = "abn_check"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — ABN validation
# ─────────────────────────────────────────────────────────────────────────────

def render_abn_check() -> None:
    render_step_bar(1)
    intake = st.session_state["intake"]

    st.markdown("## 🔍 ABN Validation")
    st.markdown(
        f'<p style="color:var(--muted)">Validating ABN '
        f'<code style="color:var(--accent)">{intake["abn"]}</code> '
        f'for <strong>{intake["company_name"]}</strong></p>',
        unsafe_allow_html=True,
    )

    # ── Tier 1: Modulo-89 ────────────────────────────────────────────────────
    st.markdown("### Tier 1 — Modulo-89 Checksum")
    mod89_valid, mod89_msg = validate_abn_modulo89(intake["abn"])

    if mod89_valid:
        st.success(f"✅ {mod89_msg}")
    else:
        st.error(f"❌ {mod89_msg}")
        if st.button("← Go Back and Fix ABN"):
            st.session_state["phase"] = "intake"
            st.rerun()
        return

    # ── Tier 2: ABR API ──────────────────────────────────────────────────────
    st.markdown("### Tier 2 — ABR Register Verification")
    with st.spinner("Contacting Australian Business Register…"):
        abr_result = asyncio.run(mock_abr_api_call(intake["abn"], intake["company_name"]))

    st.markdown(
        f'<p>API returned legal name: '
        f'<code style="color:var(--accent2)">{abr_result["api_name"]}</code><br>'
        f'Name similarity score: <code>{abr_result["similarity_score"]}</code></p>',
        unsafe_allow_html=True,
    )

    if abr_result["match"]:
        st.success("✅ Company name matches ABR record (similarity ≥ 0.60).")
    else:
        st.warning(
            f"⚠ Company name similarity is low ({abr_result['similarity_score']}). "
            "Proceeding, but flagged for manual review."
        )

    with st.expander("🔎 API Payload Sent (developer reference)"):
        st.json(abr_result["payload_sent"])

    st.session_state["abn_valid"]  = mod89_valid
    st.session_state["abn_result"] = abr_result

    if st.button("Continue to Project Details →", use_container_width=True):
        next_phase = (
            "continuing" if intake["project_type"] == "Continuing Project"
            else "new_project"
        )
        st.session_state["phase"] = next_phase
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3A — Continuing project form
# ─────────────────────────────────────────────────────────────────────────────

def render_continuing_form() -> None:
    render_step_bar(2)
    intake = st.session_state["intake"]
    year   = intake["project_year"]

    st.markdown("## 📋 Continuing Project — R&D Activity Details")
    st.markdown(
        '<p style="color:var(--muted)">Answer each question within the character limits. '
        "Minimum and maximum counts are enforced on submission.</p>",
        unsafe_allow_html=True,
    )

    with st.form("continuing_form"):
        field_values: dict[str, str] = {}

        for field in CONTINUING_FIELDS:
            label = field["label"].replace("{year}", str(year))
            st.markdown(f"**{label}**")
            st.markdown(
                f'<p style="color:var(--muted);font-size:0.82rem;">'
                f'Min: {field["min"]} chars &nbsp;|&nbsp; Max: {field["max"]} chars</p>',
                unsafe_allow_html=True,
            )
            val = st.text_area(
                label=label,
                key=f"cont_{field['key']}",
                height=field["height"],
                label_visibility="collapsed",
                value=st.session_state["form_answers"].get(field["key"], ""),
            )
            field_values[field["key"]] = val

            # Live character counter
            char_len  = len(val)
            warn_cls  = "warn" if (char_len < field["min"] or char_len > field["max"]) else ""
            st.markdown(
                f'<p class="char-count {warn_cls}">{char_len} / {field["max"]} characters</p>',
                unsafe_allow_html=True,
            )
            st.markdown("---")

        submitted = st.form_submit_button("Generate Report →", use_container_width=True)

    if submitted:
        errors = []
        for field in CONTINUING_FIELDS:
            val = field_values[field["key"]]
            if len(val) < field["min"]:
                errors.append(
                    f'"{field["label"][:50]}…" requires at least {field["min"]} characters '
                    f"(you have {len(val)})."
                )
            elif len(val) > field["max"]:
                errors.append(
                    f'"{field["label"][:50]}…" exceeds {field["max"]} characters '
                    f"(you have {len(val)})."
                )

        if errors:
            for e in errors:
                st.markdown(f'<p class="val-error">⚠ {e}</p>', unsafe_allow_html=True)
        else:
            st.session_state["form_answers"] = field_values
            report = compile_report_from_form(intake, field_values)
            st.session_state["report_text"] = report
            st.session_state["pdf_bytes"]   = generate_pdf(report)
            st.session_state["phase"]       = "report"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3B — New project chatbot
# ─────────────────────────────────────────────────────────────────────────────

def render_new_project_chat() -> None:
    render_step_bar(2)
    st.markdown("## 🤖 New Project — RDTI Compliance Interview")
    st.markdown(
        '<p style="color:var(--muted)">The AI compliance officer will interview you to '
        "extract all information needed for a valid RDTI claim. "
        "Answer each question thoroughly and technically.</p>",
        unsafe_allow_html=True,
    )

    # Resolve API key: Streamlit secrets first, then .env / environment
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except (FileNotFoundError, KeyError, Exception):
        api_key = os.getenv("OPENAI_API_KEY", "")
    try:
        llm = get_llm(api_key)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    # Seed the conversation with the first AI greeting if the chat is empty
    if not st.session_state["messages"]:
        with st.spinner("Initialising compliance officer…"):
            seed_msgs = build_langchain_messages([])
            response  = llm.invoke(seed_msgs)
            st.session_state["messages"].append(
                {"role": "assistant", "content": response.content}
            )

    # Render full chat history
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">👤 {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">🏛 {msg["content"]}</div>', unsafe_allow_html=True)

    # Detect interview completion signal from the AI
    last_ai = next(
        (m["content"] for m in reversed(st.session_state["messages"]) if m["role"] == "assistant"),
        "",
    )
    if "INTERVIEW_COMPLETE" in last_ai and not st.session_state["interview_done"]:
        st.session_state["interview_done"] = True
        parts = last_ai.split("INTERVIEW_COMPLETE", 1)
        st.session_state["chat_summary"] = parts[1].strip() if len(parts) > 1 else last_ai

    if st.session_state["interview_done"]:
        st.success("✅ Interview complete. The compliance officer has sufficient information.")
        if st.button("Generate Final Report →", use_container_width=True):
            report = compile_report_from_chat(
                st.session_state["intake"],
                st.session_state["chat_summary"],
                st.session_state["messages"],
            )
            st.session_state["report_text"] = report
            st.session_state["pdf_bytes"]   = generate_pdf(report)
            st.session_state["phase"]       = "report"
            st.rerun()
        return

    # Accept user input
    user_input = st.chat_input("Your response…")
    if user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.spinner("Processing…"):
            lc_msgs  = build_langchain_messages(st.session_state["messages"])
            response = llm.invoke(lc_msgs)
        st.session_state["messages"].append(
            {"role": "assistant", "content": response.content}
        )
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Report viewer + PDF download + Django POST
# ─────────────────────────────────────────────────────────────────────────────

def render_report() -> None:
    render_step_bar(3)
    st.markdown("## 📄 Final R&D Project Report")
    st.markdown(
        '<p style="color:var(--muted)">Your compiled RDTI report is ready. '
        "Download the PDF and submit to AusIndustry via your registered portal.</p>",
        unsafe_allow_html=True,
    )

    report_text = st.session_state["report_text"]
    pdf_bytes   = st.session_state["pdf_bytes"]
    intake      = st.session_state["intake"]

    # Render the report inline
    st.markdown(
        f'<div class="report-body">{report_text}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    col_dl, col_submit = st.columns(2)

    with col_dl:
        st.markdown("### ⬇ Download PDF")
        st.download_button(
            label="Download RDTI Report (PDF)",
            data=pdf_bytes,
            file_name=f"RDTI_Report_{intake['abn']}_{intake['project_year']}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    with col_submit:
        st.markdown("### 🚀 Submit to Backend")
        if st.button("POST to Django Backend", use_container_width=True):
            with st.spinner("Submitting to backend…"):
                resp = post_to_django_backend(intake, report_text, pdf_bytes)
                st.session_state["backend_response"] = resp
            st.success(f"✅ Submitted! Submission ID: `{resp.get('submission_id')}`")

    if st.session_state["backend_response"]:
        with st.expander("📡 Backend API Response (developer reference)"):
            st.json(st.session_state["backend_response"])

    st.markdown("---")
    if st.button("← Start New Application", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — developer state inspector
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 🛠 Developer Panel")
        st.markdown(
            '<p style="color:var(--muted);font-size:0.82rem;">Session state snapshot</p>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**Phase:** `{st.session_state.get('phase', '—')}`")
        st.markdown(f"**ABN Valid:** `{st.session_state.get('abn_valid', '—')}`")
        st.markdown(f"**Chat msgs:** `{len(st.session_state.get('messages', []))}`")
        st.markdown(f"**Interview done:** `{st.session_state.get('interview_done', '—')}`")
        st.markdown(f"**Report ready:** `{bool(st.session_state.get('report_text'))}`")
        st.markdown("---")
        st.markdown(
            "**Env variables required:**\n"
            "```\n"
            "OPENAI_API_KEY\n"
            "ABR_AUTH_GUID\n"
            "DJANGO_API_URL\n"
            "DJANGO_API_TOKEN\n"
            "```"
        )
        if st.button("🔄 Reset All State"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main router
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    inject_css()
    init_state()
    render_sidebar()

    # Hero header
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:0.5rem;">
          <span style="font-size:2.8rem;">🔬</span>
          <div>
            <h1 style="margin:0;line-height:1.1;">RDTI AI Agent</h1>
            <p style="color:var(--muted);margin:0;font-size:0.9rem;">
              Australian Research &amp; Development Tax Incentive — Application Assistant
            </p>
          </div>
        </div>
        <div style="height:1px;background:var(--border);margin-bottom:1.5rem;"></div>
        """,
        unsafe_allow_html=True,
    )

    phase = st.session_state["phase"]

    if phase == "intake":
        render_intake()
    elif phase == "abn_check":
        render_abn_check()
    elif phase == "continuing":
        render_continuing_form()
    elif phase == "new_project":
        render_new_project_chat()
    elif phase == "report":
        render_report()
    else:
        st.error(f"Unknown phase: '{phase}'")
        if st.button("Reset to Intake"):
            st.session_state["phase"] = "intake"
            st.rerun()


if __name__ == "__main__":
    main()
