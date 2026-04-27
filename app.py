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

import openai

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
from doc_extractor  import extract_text_from_upload
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
        "phase":            "intake",   # intake | abn_check | continuing_context | continuing | new_project | report
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
        # ── Continuing-project wizard state ───────────────────────────
        "current_step":         1,      # tracks wizard step (1-based)
        "continuing_project_name": "",  # name of the continuing project
        "continuing_file":      None,   # uploaded prior-year claim file
        "historical_text":      "",     # extracted text from prior-year document
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
        f'<p style="color:var(--rdti-muted);font-size:0.8rem;margin-top:-0.8rem;">'
        f'Step {active_step + 1} of {len(STEPS)}: '
        f'<strong style="color:var(--rdti-text)">{STEPS[active_step]}</strong></p>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Intake form
# ─────────────────────────────────────────────────────────────────────────────

def render_intake() -> None:
    render_step_bar(0)
    st.markdown("## 🔬 RDTI Application Intake")
    st.markdown(
        '<p style="color:var(--rdti-muted)">Complete the fields below to begin your '
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
        f'<p style="color:var(--rdti-muted)">Validating ABN '
        f'<code style="color:var(--rdti-accent)">{intake["abn"]}</code> '
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
        f'<code style="color:var(--rdti-accent2)">{abr_result["api_name"]}</code><br>'
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
            "continuing_context" if intake["project_type"] == "Continuing Project"
            else "new_project"
        )
        st.session_state["phase"] = next_phase
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3A-0 — Continuing project: historical context
# ─────────────────────────────────────────────────────────────────────────────

def render_continuing_context() -> None:
    """First step for Continuing Projects — establish which project is being updated."""
    render_step_bar(2)
    st.markdown("## 📂 Continuing Project — Historical Context")
    st.markdown(
        '<p style="color:var(--rdti-muted)">Before we begin the R&D questions, '
        "please provide context about the project you are continuing.</p>",
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Please upload last year's R&D claim data",
        type=["pdf", "docx", "xlsx", "csv", "txt"],
        key="continuing_file_uploader",
    )
    project_name = st.text_input(
        "Or enter the name of the continuing project.",
        value=st.session_state.get("continuing_project_name", ""),
        key="continuing_project_name_input",
    )

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back to ABN Check", use_container_width=True):
            st.session_state["phase"] = "abn_check"
            st.rerun()
    with col_next:
        if st.button("Next →", use_container_width=True, key="ctx_next"):
            st.session_state["continuing_project_name"] = project_name.strip()
            if uploaded_file is not None:
                raw_bytes = uploaded_file.read()
                st.session_state["continuing_file"] = raw_bytes
                # ── Extract text from the uploaded document ───────────
                with st.spinner("Extracting text from uploaded document…"):
                    extracted = extract_text_from_upload(
                        raw_bytes, uploaded_file.name
                    )
                st.session_state["historical_text"] = extracted
            st.session_state["current_step"] = 1
            st.session_state["phase"] = "continuing"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3A — Continuing project: multi-step wizard
# ─────────────────────────────────────────────────────────────────────────────

def render_continuing_form() -> None:
    render_step_bar(2)
    intake = st.session_state["intake"]
    year   = intake["project_year"]
    step   = st.session_state["current_step"]          # 1-based
    total  = len(CONTINUING_FIELDS)
    field  = CONTINUING_FIELDS[step - 1]
    label  = field["label"].replace("{year}", str(year))

    st.markdown("## 📋 Continuing Project — R&D Activity Details")
    st.markdown(
        f'<p style="color:var(--rdti-muted)">'
        f'Question {step} of {total} — answer within the character limits.</p>',
        unsafe_allow_html=True,
    )

    # ── Render only the current step's text area ─────────────────────────────
    st.markdown(f"**{label}**")
    st.markdown(
        f'<p style="color:var(--rdti-muted);font-size:0.82rem;">'
        f'Min: {field["min"]} chars &nbsp;|&nbsp; Max: {field["max"]} chars</p>',
        unsafe_allow_html=True,
    )

    # Retrieve previously saved value (if user navigated back)
    saved_value = st.session_state["form_answers"].get(field["key"], "")
    val = st.text_area(
        label=label,
        key=f"cont_{field['key']}",
        height=field["height"],
        label_visibility="collapsed",
        value=saved_value,
    )

    # Live character counter
    char_len = len(val)
    warn_cls = "warn" if (char_len < field["min"] or char_len > field["max"]) else ""
    st.markdown(
        f'<p class="char-count {warn_cls}">{char_len} / {field["max"]} characters</p>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Navigation buttons ───────────────────────────────────────────────────
    col_back, col_next = st.columns(2)

    with col_back:
        if step == 1:
            # First wizard step → go back to context screen
            if st.button("← Back", use_container_width=True):
                # Save current input before leaving
                st.session_state["form_answers"][field["key"]] = val
                st.session_state["phase"] = "continuing_context"
                st.rerun()
        else:
            if st.button("← Back", use_container_width=True):
                st.session_state["form_answers"][field["key"]] = val
                st.session_state["current_step"] = step - 1
                st.rerun()

    with col_next:
        if step < total:
            if st.button("Next →", use_container_width=True):
                # Validate before advancing
                if char_len < field["min"]:
                    st.markdown(
                        f'<p class="val-error">⚠ Please enter at least '
                        f'{field["min"]} characters (you have {char_len}).</p>',
                        unsafe_allow_html=True,
                    )
                elif char_len > field["max"]:
                    st.markdown(
                        f'<p class="val-error">⚠ Please reduce to under '
                        f'{field["max"]} characters (you have {char_len}).</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.session_state["form_answers"][field["key"]] = val
                    st.session_state["current_step"] = step + 1
                    st.rerun()
        else:
            # Last step → Generate Report via AI compilation
            if st.button("Generate Report →", use_container_width=True):
                if char_len < field["min"]:
                    st.markdown(
                        f'<p class="val-error">⚠ Please enter at least '
                        f'{field["min"]} characters (you have {char_len}).</p>',
                        unsafe_allow_html=True,
                    )
                elif char_len > field["max"]:
                    st.markdown(
                        f'<p class="val-error">⚠ Please reduce to under '
                        f'{field["max"]} characters (you have {char_len}).</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.session_state["form_answers"][field["key"]] = val
                    _generate_continuing_report(intake)


# ─────────────────────────────────────────────────────────────────────────────
# Continuing-project: AI report compilation
# ─────────────────────────────────────────────────────────────────────────────

# Maximum characters of historical text to send in the prompt.
# Prevents token-limit blowout for very large prior-year documents.
_MAX_HISTORICAL_CHARS = 12_000

_CONTINUING_REPORT_SYSTEM_PROMPT = """\
You are an expert Australian R&D Tax Incentive (RDTI) compliance analyst and technical writer.
You have been provided with TWO sources of information:

1. **Historical Prior-Year Claim Document** — extracted text from the applicant's previous year's
   R&D claim submission. This gives you context on the project's origin, baseline knowledge,
   original hypotheses, and prior experimental work.

2. **Current-Year Form Answers** — the applicant's answers to this year's R&D activity questions
   covering: (a) experiments conducted, (b) evaluation methods, (c) conclusions, and (d) new
   knowledge generated.

YOUR TASKS:
A. **Evaluate RDTI Compliance** — Analyse whether the described activities constitute genuine
   Core R&D Activities under Division 355 of the ITAA 1997. Specifically check that:
   - The work represents a *systematic progression of work* based on principles of established
     science, proceeding from hypothesis through experiment to evaluation and logical conclusion.
   - The activities aim to generate *new knowledge* (including new knowledge in the form of new
     or improved materials, products, devices, processes, or services).
   - The outcome could NOT have been known or determined in advance on the basis of current
     knowledge, information, or experience by a competent professional in the field.
   If any deficiency is identified, note it in the report but still compile the best possible output.

B. **Compile Formal Report** — Rewrite and synthesise ALL provided information (historical +
   current-year) into a single, formal, AusIndustry-compliant R&D project report.

OUTPUT FORMAT — You MUST produce your response in well-structured Markdown containing ALL of
the following sections (use ## headings). Synthesise data from BOTH the historical upload AND
the new form inputs:

## Objective
Describe the overarching R&D objective of the continuing project, incorporating context from
the prior year's work and the current year's direction.

## Core R&D Activity
Detail the core R&D activity, explaining what specific technical challenge is being addressed
and why it qualifies as a systematic investigation under Division 355.

## Hypothesis
State the hypothesis or hypotheses being tested, linking prior-year findings to the current
year's experimental direction.

## Sources Investigated
List and describe the established science, prior art, technical literature, and any previous
experimental results that were investigated or relied upon.

## Experiments Conducted
Describe the experiments conducted in the current year, including methodology, variables,
controls, and how they tested the hypothesis.

## Evaluation
Explain the evaluation methods used or planned to assess experimental results, including
criteria for success or failure.

## Conclusions
Present the conclusions drawn from the experiments, including whether the hypothesis was
supported, refuted, or remains inconclusive.

## New Knowledge Generated
Articulate the genuinely new knowledge, capability, or understanding that resulted from the
R&D activities — knowledge that was not previously available in the public domain or
determinable by a competent professional.

IMPORTANT RULES:
- Write in formal, technical language appropriate for an AusIndustry assessor.
- Do NOT fabricate technical details. Only use what is provided in the inputs.
- If the historical document is missing or empty, note this and compile from the form answers alone.
- If you detect compliance risks, include a brief "Compliance Notes" section at the end.
"""


def _generate_continuing_report(intake: dict) -> None:
    """
    Call OpenAI to synthesise the continuing-project form answers and any
    historical document text into a formal, RDTI-compliant report.

    Manages the spinner, error handling, and session-state updates.
    """
    form_answers    = st.session_state["form_answers"]
    historical_text = st.session_state.get("historical_text", "")

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

    # ── Build the user message ────────────────────────────────────────────
    hist_section = historical_text.strip()
    if len(hist_section) > _MAX_HISTORICAL_CHARS:
        hist_section = hist_section[:_MAX_HISTORICAL_CHARS] + "\n\n[...truncated for length]"

    user_content = (
        "=== COMPANY DETAILS ===\n"
        f"Company: {intake['company_name']}\n"
        f"ABN: {intake['abn']}\n"
        f"Industry: {intake['industry']}\n"
        f"Project Year: {intake['project_year']}\n"
        f"Project Name: {st.session_state.get('continuing_project_name', 'N/A')}\n\n"
        "=== HISTORICAL PRIOR-YEAR CLAIM DOCUMENT ===\n"
        f"{hist_section if hist_section else '[No prior-year document was uploaded.]'}\n\n"
        "=== CURRENT-YEAR FORM ANSWERS ===\n"
        f"**Experiments Conducted:**\n{form_answers.get('experiments', 'N/A')}\n\n"
        f"**Evaluation Method:**\n{form_answers.get('evaluation', 'N/A')}\n\n"
        f"**Conclusions:**\n{form_answers.get('conclusions', 'N/A')}\n\n"
        f"**New Knowledge Generated:**\n{form_answers.get('new_knowledge', 'N/A')}\n"
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=_CONTINUING_REPORT_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    with st.spinner("Evaluating compliance and generating R&D Report..."):
        try:
            response = llm.invoke(messages)
            ai_report = response.content

            st.session_state["report_text"] = ai_report
            st.session_state["pdf_bytes"]   = generate_pdf(ai_report)
            st.session_state["phase"]       = "report"
            st.rerun()

        except openai.BadRequestError:
            # Token limit exceeded — try again with truncated historical text
            st.warning(
                "⚠️ The combined input exceeded the model's token limit. "
                "Retrying with a shorter version of the historical document…"
            )
            if hist_section and len(hist_section) > 3000:
                hist_section_short = hist_section[:3000] + "\n\n[...heavily truncated for length]"
                user_content_short = (
                    "=== COMPANY DETAILS ===\n"
                    f"Company: {intake['company_name']}\n"
                    f"ABN: {intake['abn']}\n"
                    f"Industry: {intake['industry']}\n"
                    f"Project Year: {intake['project_year']}\n"
                    f"Project Name: {st.session_state.get('continuing_project_name', 'N/A')}\n\n"
                    "=== HISTORICAL PRIOR-YEAR CLAIM DOCUMENT ===\n"
                    f"{hist_section_short}\n\n"
                    "=== CURRENT-YEAR FORM ANSWERS ===\n"
                    f"**Experiments Conducted:**\n{form_answers.get('experiments', 'N/A')}\n\n"
                    f"**Evaluation Method:**\n{form_answers.get('evaluation', 'N/A')}\n\n"
                    f"**Conclusions:**\n{form_answers.get('conclusions', 'N/A')}\n\n"
                    f"**New Knowledge Generated:**\n{form_answers.get('new_knowledge', 'N/A')}\n"
                )
                messages_retry = [
                    SystemMessage(content=_CONTINUING_REPORT_SYSTEM_PROMPT),
                    HumanMessage(content=user_content_short),
                ]
                try:
                    response = llm.invoke(messages_retry)
                    ai_report = response.content
                    st.session_state["report_text"] = ai_report
                    st.session_state["pdf_bytes"]   = generate_pdf(ai_report)
                    st.session_state["phase"]       = "report"
                    st.rerun()
                except Exception as retry_exc:
                    st.error(
                        "❌ The input is still too large even after truncation. "
                        f"Please shorten your answers and try again. (Error: {retry_exc})"
                    )
            else:
                st.error(
                    "❌ The form answers exceeded the model's maximum token limit. "
                    "Please shorten your responses and try again."
                )

        except (openai.APITimeoutError, openai.RateLimitError):
            st.error(
                "⏳ The server timed out or is rate-limited. "
                "Please wait a moment and try again."
            )

        except Exception as exc:
            st.error(
                "⚠️ An unexpected error occurred while generating the report. "
                f"Please try again. (Error: {exc})"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3B — New project chatbot
# ─────────────────────────────────────────────────────────────────────────────

def render_new_project_chat() -> None:
    render_step_bar(2)
    st.markdown("## 🤖 New Project — RDTI Compliance Interview")
    st.markdown(
        '<p style="color:var(--rdti-muted)">The AI compliance officer will interview you to '
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
            try:
                seed_msgs = build_langchain_messages([])
                response  = llm.invoke(seed_msgs)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": response.content}
                )
            except (openai.APITimeoutError, openai.RateLimitError) as exc:
                st.error(
                    "⏳ The server is currently busy or timed out. "
                    "Please wait a moment and refresh the page to try again."
                )
                st.stop()
            except openai.BadRequestError as exc:
                st.error(
                    "❌ The request was rejected by the API. "
                    f"Details: {exc}"
                )
                st.stop()
            except Exception as exc:
                st.error(
                    "⚠️ An unexpected error occurred while initialising the interview. "
                    f"Please refresh and try again. (Error: {exc})"
                )
                st.stop()

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
        with st.spinner("Processing R&D data. This may take a moment for large inputs..."):
            try:
                # Build messages with the new user input included,
                # but do NOT append to session state yet (state protection).
                pending_messages = st.session_state["messages"] + [
                    {"role": "user", "content": user_input}
                ]
                lc_msgs  = build_langchain_messages(pending_messages)
                response = llm.invoke(lc_msgs)

                # ── Success: commit both messages to session state ────
                st.session_state["messages"].append(
                    {"role": "user", "content": user_input}
                )
                st.session_state["messages"].append(
                    {"role": "assistant", "content": response.content}
                )
                st.rerun()

            except (openai.APITimeoutError, openai.RateLimitError):
                st.error(
                    "⏳ The server timed out or is rate-limited. "
                    "Please try again in a few seconds, or break your "
                    "text into smaller chunks."
                )
            except openai.BadRequestError:
                st.error(
                    "❌ The input was too large and exceeded the model's "
                    "maximum token limit. Please shorten your response "
                    "and try again."
                )
            except Exception as exc:
                st.error(
                    "⚠️ An unexpected error occurred while processing "
                    "your input. Please try again or break your text "
                    f"into smaller chunks. (Error: {exc})"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Report viewer + PDF download + Django POST
# ─────────────────────────────────────────────────────────────────────────────

def render_report() -> None:
    render_step_bar(3)
    st.markdown("## 📄 Final R&D Project Report")
    st.markdown(
        '<p style="color:var(--rdti-muted)">Your compiled RDTI report is ready. '
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
            '<p style="color:var(--rdti-muted);font-size:0.82rem;">Session state snapshot</p>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**Phase:** `{st.session_state.get('phase', '—')}`")
        st.markdown(f"**ABN Valid:** `{st.session_state.get('abn_valid', '—')}`")
        st.markdown(f"**Wizard Step:** `{st.session_state.get('current_step', '—')}`")
        st.markdown(f"**Continuing Project:** `{st.session_state.get('continuing_project_name', '—') or '—'}`")
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
            <p style="color:var(--rdti-muted);margin:0;font-size:0.9rem;">
              Australian Research &amp; Development Tax Incentive — Application Assistant
            </p>
          </div>
        </div>
        <div style="height:1px;background:var(--rdti-border);margin-bottom:1.5rem;"></div>
        """,
        unsafe_allow_html=True,
    )

    phase = st.session_state["phase"]

    if phase == "intake":
        render_intake()
    elif phase == "abn_check":
        render_abn_check()
    elif phase == "continuing_context":
        render_continuing_context()
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
