"""
app.py — RDTI AI Agent: Intake + ABN Validation + 5-Stage Processing Pipeline
Run:  streamlit run app.py
"""
import asyncio, os, re, json
import openai
import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

load_dotenv()

from abn_validator  import validate_abn_modulo89, mock_abr_api_call
from config         import INDUSTRY_OPTIONS, PROJECT_YEARS
from doc_extractor  import extract_text_from_upload
from llm_agent      import get_llm
from report_builder import generate_pdf
from styles         import inject_css

st.set_page_config(page_title="RDTI AI Agent", page_icon="🔬", layout="wide", initial_sidebar_state="collapsed")

# ── Constants ─────────────────────────────────────────────────────────────────
STAGE_LABELS = ["Structured Basics", "Document Ingestion", "Chat Interview", "Scoring Engine", "Final Report"]
_MAX_HIST = 12_000

# ── Prompts ───────────────────────────────────────────────────────────────────
STAGE_2_PROMPT = """\
You are an expert Australian RDTI analyst. Given extracted text from a prior-year R&D claim:
1. Extract the core R&D narrative (objectives, hypotheses, experiments, results, new knowledge).
2. Identify REUSABLE baseline knowledge that carries forward.
3. Explicitly FLAG elements needing updates for the new financial year.
Respond in Markdown with two sections:
## Extracted Baseline Knowledge
[Summarise reusable narrative]
## Required Updates for New Year
[Numbered list of items needing update]
Do NOT fabricate details."""

STAGE_3_PROMPT = """\
You are an expert RDTI compliance interviewer. You review data from Stages 1 & 2 and \
systematically collect ALL information for a formal RDTI claim.

COLLECTED CONTEXT (from prior stages) is appended below the conversation.

Collect these topics by asking ONE focused question at a time:
1. CORE R&D ACTIVITY — specific technical challenge, title, dates conducted
2. NEW KNOWLEDGE — gap in industry/scientific knowledge being addressed
3. HYPOTHESIS — testable scientific/technical hypothesis
4. EXPERIMENTS — methodology, parameters, how they tested the hypothesis
5. EVALUATION — metrics and analysis used to evaluate results
6. CONCLUSIONS — technical findings from experiments
7. UNKNOWN IN ADVANCE — sources investigated, why a competent professional couldn't know
8. EVIDENCE KEPT — records, logs, documentation maintained
9. SUPPORTING ACTIVITIES — for each: title, dates, how it supports core, description. \
Ask if there are more after each one.

RULES:
- Ask ONE question at a time. Probe vague answers before moving on.
- Use formal technical language. Redirect off-topic responses.
- When ALL 9 topics are adequately covered, output INTERVIEW_COMPLETE on its own line, \
then a structured Markdown summary of everything collected.
- Do NOT fabricate details.
Begin by greeting the user and asking about their Core R&D Activity."""

STAGE_4_PROMPT = """\
You are an RDTI Pre-Qualification Scorer. Evaluate the R&D narrative for compliance \
under Division 355 of the ITAA 1997.
Score on 4 criteria (25 pts each, 100 total):
1. TECHNICAL UNCERTAINTY — genuine unknowns a competent professional couldn't determine
2. SYSTEMATIC PROGRESSION — hypothesis->experiment->evaluation->conclusion
3. NEW KNOWLEDGE — genuinely new, not routine application of existing techniques
4. EVIDENCE & DOCUMENTATION — adequate records of R&D process
Respond ONLY with valid JSON (no markdown fencing):
{"score":<0-100>,"breakdown":{"technical_uncertainty":<0-25>,"systematic_progression":<0-25>,\
"new_knowledge":<0-25>,"evidence_documentation":<0-25>},\
"red_flags":["..."],"strengths":["..."],"recommendations":["..."]}"""

STAGE_5_SYSTEM_PROMPT = """\
You are an expert Australian R&D Tax Incentive (RDTI) Compliance Officer and Senior Technical Writer.
Your task is to take the user's raw interview notes and rewrite them into a highly formal, technical, and audit-ready document.
DO NOT simply copy-paste the user's input. Synthesize and evaluate it to ensure it demonstrates a 'systematic progression of work' and genuine 'technical uncertainty'.

You MUST output your response in Markdown, and it MUST strictly follow the exact structure, headers, and character limits below. Do not deviate from these headers.

# [INSERT COMPANY NAME] R&D PLAN
## PART A - R&D PLAN AUTHORISATION

**Projects**
| No. | Project Title | Start Date | Finish Date | $ Forecast / Budgeted |
|---|---|---|---|---|
| 1. | [Title] | [Start] | [End] | [$ Amount] |

**Objective (1000 Characters)**
State: The Objective of the Project
[Rewrite the overarching commercial and technical objective here]

**Core R&D Activity [Number]**
[Title of Core Activity]
This activity was/will be conducted from [Start Date] to [End Date].

**What is the New Knowledge? (maximum 1000 characters)**
[Explicitly state the gap in current industry knowledge and the new technical knowledge being generated]

**What was the hypothesis for Core activity [Number]? (maximum 4000 characters)**
[Formulate a clear, testable scientific/technical hypothesis]

**What was the experiment/s and how did it test the hypothesis? (max 4000 characters)**
[Detail the systematic testing parameters, iterations, and methodologies]

**How did you evaluate or plan to evaluate the results from the experiment/s? (maximum 4000 characters)**
[Describe the metrics, analysis, and variables used to evaluate the experiment results]

**Describe the conclusions you've reached from the experiment/s? (max 4000 characters)**
[Summarize the technical findings and whether the hypothesis was proven or disproven]

**How did you determine that the outcome could not be known in advance?**
Please select the fields that apply:
- [x] There was no applicable information in scientific, technical, or professional literature or patents
- [x] Experts in the field provided advice that there wasn't a solution that could be applied
- [x] There wasn't a way to adapt solutions from other companies in, and out of Australia
[Include any other checkboxes applicable based on input]

Please explain what sources were investigated, what information was found, and why a competent professional could not have known or determined the outcome in advance? (maximum 1000 characters)
[Rewrite justification referencing specific sources and the limits of current professional knowledge]

**What evidence did you keep about this Core activity?**
Please select the fields that apply:
- [x] Evidence of searches or enquiries you made to find current knowledge
- [x] Evidence to show that you could only determine the outcome of the core activity by conducting experiments as part of a systematic progression of work
- [x] Evidence of your hypothesis and design of your experiments
- [x] Documented results and evaluation of your experiments
[Include any other checkboxes applicable based on input]

**Supporting R&D Activity [Number.Number] -- [Title]**
This activity was/will be conducted from (Month/Year only) [Start Date] to [End Date].

**How did this activity directly support the core activities? (maximum 1000 characters)**
[Explicitly state the DOMINANT PURPOSE linking this activity to the core experiment]

**Describe the supporting activity (maximum 1000 characters)**
[Briefly detail the specific work undertaken in this supporting role]
"""

# ── Session State ─────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "phase":            "intake",   # intake | abn_check | stages
        "intake":           {},         # company_name, contact_person, abn, industry, project_year, project_type
        "abn_valid":        False,
        "abn_result":       {},
        "current_stage":    1,          # 1-5 within the pipeline
        "project_metadata": {},         # project_title, start_date, finish_date, budget (+ intake fields)
        "historical_text":  "",
        "extracted_baseline": "",
        "required_updates": "",
        "messages":         [],
        "interview_complete": False,
        "interview_summary": "",
        "scoring_result":   {},
        "report_text":      "",
        "pdf_bytes":        None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────
def _resolve_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")

def _llm():
    try:
        return get_llm(_resolve_key())
    except ValueError as e:
        st.error(str(e)); st.stop()

def render_stage_bar(idx):
    bars = "".join(
        f'<div class="step {"done" if i<idx else "active" if i==idx else ""}" title="{l}"></div>'
        for i, l in enumerate(STAGE_LABELS)
    )
    st.markdown(
        f'<div class="step-bar">{bars}</div>'
        f'<p style="color:var(--rdti-muted);font-size:.8rem;margin-top:-.8rem;">'
        f'Stage {idx+1} of {len(STAGE_LABELS)}: '
        f'<strong style="color:var(--rdti-text)">{STAGE_LABELS[idx]}</strong></p>',
        unsafe_allow_html=True,
    )

def _build_full_context():
    """Assemble all collected data for LLM consumption."""
    intake = st.session_state["intake"]
    md = st.session_state["project_metadata"]
    parts = [
        "=== COMPANY / INTAKE DETAILS ===",
        f"Company: {intake.get('company_name','')}",
        f"ABN: {intake.get('abn','')}",
        f"Industry: {intake.get('industry','')}",
        f"Contact: {intake.get('contact_person','')}",
        f"Project Year: {intake.get('project_year','')}",
        f"Project Type: {intake.get('project_type','')}",
        "",
        "=== PROJECT METADATA ===",
        f"Project Title: {md.get('project_title','')}",
        f"Start Date: {md.get('start_date','')}",
        f"Finish Date: {md.get('finish_date','')}",
        f"Budget: {md.get('budget','')}",
    ]
    bl = st.session_state.get("extracted_baseline", "")
    if bl:
        parts += ["", "=== PRIOR-YEAR BASELINE ===", bl]
    ru = st.session_state.get("required_updates", "")
    if ru:
        parts += ["", "=== REQUIRED UPDATES ===", ru]
    summ = st.session_state.get("interview_summary", "")
    if summ:
        parts += ["", "=== INTERVIEW SUMMARY ===", summ]
    return "\n".join(parts)

# ─────────────────────────────────────────────────────────────────────────────
# Pre-Pipeline: Intake Form
# ─────────────────────────────────────────────────────────────────────────────
def render_intake():
    st.markdown("## 🔬 RDTI Application Intake")
    st.markdown(
        '<p style="color:var(--rdti-muted)">Complete the fields below to begin your '
        "R&D Tax Incentive application assessment.</p>",
        unsafe_allow_html=True,
    )
    with st.form("intake_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            company_name   = st.text_input("Company Name *", placeholder="Acme Biotech Pty Ltd")
            abn            = st.text_input("ABN *", placeholder="51 824 753 556", max_chars=14)
            industry       = st.selectbox("Industry *", list(INDUSTRY_OPTIONS.keys()))
        with c2:
            contact_person = st.text_input("Contact Person *", placeholder="Jane Smith")
            project_year   = st.selectbox("Project Year *", PROJECT_YEARS)
            project_type   = st.radio("Project Type *", ["Continuing Project", "New Project"], horizontal=True)
        submitted = st.form_submit_button("Validate & Continue →", use_container_width=True)

    if submitted:
        errors = []
        if not company_name.strip(): errors.append("Company Name is required.")
        if not contact_person.strip(): errors.append("Contact Person is required.")
        abn_clean = re.sub(r"\s", "", abn)
        if not abn_clean.isdigit() or len(abn_clean) != 11:
            errors.append("ABN must contain exactly 11 digits (spaces allowed).")
        if errors:
            for e in errors:
                st.markdown(f'<p class="val-error">⚠ {e}</p>', unsafe_allow_html=True)
        else:
            st.session_state["intake"] = {
                "company_name": company_name.strip(),
                "contact_person": contact_person.strip(),
                "abn": abn_clean,
                "industry": industry,
                "project_year": project_year,
                "project_type": project_type,
            }
            st.session_state["phase"] = "abn_check"
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Pre-Pipeline: ABN Validation
# ─────────────────────────────────────────────────────────────────────────────
def render_abn_check():
    intake = st.session_state["intake"]
    st.markdown("## 🔍 ABN Validation")
    st.markdown(
        f'<p style="color:var(--rdti-muted)">Validating ABN '
        f'<code style="color:var(--rdti-accent)">{intake["abn"]}</code> '
        f'for <strong>{intake["company_name"]}</strong></p>',
        unsafe_allow_html=True,
    )
    # Tier 1: Modulo-89
    st.markdown("### Tier 1 — Modulo-89 Checksum")
    mod89_valid, mod89_msg = validate_abn_modulo89(intake["abn"])
    if mod89_valid:
        st.success(f"✅ {mod89_msg}")
    else:
        st.error(f"❌ {mod89_msg}")
        if st.button("← Go Back and Fix ABN"):
            st.session_state["phase"] = "intake"; st.rerun()
        return

    # Tier 2: ABR API
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
        st.warning(f"⚠ Company name similarity is low ({abr_result['similarity_score']}). Flagged for review.")

    with st.expander("🔎 API Payload Sent (developer reference)"):
        st.json(abr_result["payload_sent"])

    st.session_state["abn_valid"]  = mod89_valid
    st.session_state["abn_result"] = abr_result

    if st.button("Continue to Project Pipeline →", use_container_width=True):
        st.session_state["phase"] = "stages"
        st.session_state["current_stage"] = 1
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Structured Basics (Project-specific details)
# ─────────────────────────────────────────────────────────────────────────────
def render_stage_1():
    render_stage_bar(0)
    intake = st.session_state["intake"]
    st.markdown("## 🔬 Stage 1: Project Details")
    st.markdown(
        f'<p style="color:var(--rdti-muted)">Company: <strong>{intake["company_name"]}</strong> — '
        f'Provide the project-specific details below.</p>',
        unsafe_allow_html=True,
    )
    meta = st.session_state.get("project_metadata", {})
    with st.form("project_form"):
        c1, c2 = st.columns(2)
        with c1:
            project = st.text_input("Project Title *", value=meta.get("project_title",""), placeholder="Advanced Glass Coating R&D")
            budget  = st.text_input("Forecast / Budgeted Amount *", value=meta.get("budget",""), placeholder="$250,000")
        with c2:
            start  = st.text_input("Start Date *", value=meta.get("start_date",""), placeholder="01/07/2022")
            finish = st.text_input("Finish Date *", value=meta.get("finish_date",""), placeholder="30/06/2023")
        submitted = st.form_submit_button("Save & Continue →", use_container_width=True)

    if submitted:
        errs = []
        if not project.strip(): errs.append("Project Title is required.")
        if not start.strip():   errs.append("Start Date is required.")
        if not finish.strip():  errs.append("Finish Date is required.")
        if not budget.strip():  errs.append("Budget is required.")
        if errs:
            for e in errs:
                st.markdown(f'<p class="val-error">⚠ {e}</p>', unsafe_allow_html=True)
        else:
            st.session_state["project_metadata"] = {
                "company_name": intake["company_name"],
                "project_title": project.strip(),
                "start_date": start.strip(),
                "finish_date": finish.strip(),
                "budget": budget.strip(),
            }
            st.session_state["current_stage"] = 2
            st.rerun()

# ── Stage 2: AI Document Ingestion ───────────────────────────────────────────
def render_stage_2():
    render_stage_bar(1)
    st.markdown("## 📂 Stage 2: Prior-Year Document Ingestion")
    st.markdown(
        '<p style="color:var(--rdti-muted)">Upload the prior year\'s R&D claim. '
        "The AI will extract baseline knowledge and flag required updates.</p>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader("Upload prior-year claim (PDF/DOCX)", type=["pdf","docx"], key="s2_upload")

    col_b, col_n = st.columns(2)
    with col_b:
        if st.button("← Back", use_container_width=True):
            st.session_state["current_stage"] = 1; st.rerun()
    with col_n:
        skip = st.button("Skip (no prior year) →", use_container_width=True)
        proceed = st.button("Extract & Continue →", use_container_width=True) if uploaded else False

    if skip:
        st.session_state["extracted_baseline"] = ""
        st.session_state["required_updates"] = ""
        st.session_state["current_stage"] = 3; st.rerun()

    if proceed and uploaded:
        raw = uploaded.read()
        with st.spinner("Extracting text from document…"):
            text = extract_text_from_upload(raw, uploaded.name)
        if len(text) > _MAX_HIST:
            text = text[:_MAX_HIST] + "\n\n[...truncated]"
        st.session_state["historical_text"] = text

        llm = _llm()
        with st.spinner("AI is analysing prior-year document…"):
            try:
                resp = llm.invoke([
                    SystemMessage(content=STAGE_2_PROMPT),
                    HumanMessage(content=text),
                ])
                content = resp.content
                # Parse baseline and updates
                bl, ru = content, ""
                if "## Required Updates" in content:
                    parts = content.split("## Required Updates", 1)
                    bl = parts[0].replace("## Extracted Baseline Knowledge","").strip()
                    ru = parts[1].strip()
                st.session_state["extracted_baseline"] = bl
                st.session_state["required_updates"] = ru
                st.session_state["current_stage"] = 3; st.rerun()
            except Exception as exc:
                st.error(f"⚠️ Error during AI analysis: {exc}")

    # Show existing extraction if available
    if st.session_state.get("extracted_baseline"):
        with st.expander("📋 Extracted Baseline (from prior run)"):
            st.markdown(st.session_state["extracted_baseline"])
        with st.expander("🔄 Required Updates"):
            st.markdown(st.session_state["required_updates"])

# ── Stage 3: Chat Interview ──────────────────────────────────────────────────
def render_stage_3():
    render_stage_bar(2)
    st.markdown("## 🤖 Stage 3: R&D Compliance Interview")
    st.markdown(
        '<p style="color:var(--rdti-muted)">The AI interviewer will guide you through '
        "each section of the RDTI template, one question at a time.</p>",
        unsafe_allow_html=True,
    )

    llm = _llm()
    context = _build_full_context()

    # Build system message with context
    sys_content = STAGE_3_PROMPT + "\n\n--- CONTEXT FROM PRIOR STAGES ---\n" + context

    # Seed first message
    if not st.session_state["messages"]:
        with st.spinner("Initialising interviewer…"):
            try:
                resp = llm.invoke([SystemMessage(content=sys_content)])
                st.session_state["messages"].append({"role":"assistant","content":resp.content})
            except Exception as exc:
                st.error(f"⚠️ {exc}"); st.stop()

    # Render chat history
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">👤 {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">🏛 {msg["content"]}</div>', unsafe_allow_html=True)

    # Detect completion
    last_ai = next((m["content"] for m in reversed(st.session_state["messages"]) if m["role"]=="assistant"), "")
    if "INTERVIEW_COMPLETE" in last_ai and not st.session_state["interview_complete"]:
        st.session_state["interview_complete"] = True
        parts = last_ai.split("INTERVIEW_COMPLETE", 1)
        st.session_state["interview_summary"] = parts[1].strip() if len(parts) > 1 else last_ai

    if st.session_state["interview_complete"]:
        st.success("✅ Interview complete — all required information collected.")
        if st.button("Proceed to Scoring Engine →", use_container_width=True):
            st.session_state["current_stage"] = 4; st.rerun()
        return

    # Chat input
    user_input = st.chat_input("Your response…")
    if user_input:
        with st.spinner("Processing…"):
            try:
                pending = st.session_state["messages"] + [{"role":"user","content":user_input}]
                lc = [SystemMessage(content=sys_content)]
                for m in pending:
                    lc.append(HumanMessage(content=m["content"]) if m["role"]=="user" else AIMessage(content=m["content"]))
                resp = llm.invoke(lc)
                st.session_state["messages"].append({"role":"user","content":user_input})
                st.session_state["messages"].append({"role":"assistant","content":resp.content})
                st.rerun()
            except openai.BadRequestError:
                st.error("❌ Input too large. Please shorten your response.")
            except (openai.APITimeoutError, openai.RateLimitError):
                st.error("⏳ Server busy. Please wait and retry.")
            except Exception as exc:
                st.error(f"⚠️ Error: {exc}")

# ── Stage 4: Scoring Engine ──────────────────────────────────────────────────
def render_stage_4():
    render_stage_bar(3)
    st.markdown("## 📊 Stage 4: RDTI Compliance Scoring")

    # Run scoring if not yet done
    if not st.session_state.get("scoring_result"):
        llm = _llm()
        context = _build_full_context()
        with st.spinner("Running RDTI Pre-Qualification Scoring…"):
            try:
                resp = llm.invoke([
                    SystemMessage(content=STAGE_4_PROMPT),
                    HumanMessage(content=context),
                ])
                raw = resp.content.strip()
                # Clean potential markdown fencing
                raw = re.sub(r"^```json\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
                result = json.loads(raw)
                st.session_state["scoring_result"] = result
            except json.JSONDecodeError:
                st.error("⚠️ Scoring returned invalid JSON. Retrying…")
                st.session_state["scoring_result"] = {
                    "score": 0, "red_flags": ["Scoring failed — please retry"],
                    "strengths": [], "recommendations": [],
                    "breakdown": {"technical_uncertainty":0,"systematic_progression":0,"new_knowledge":0,"evidence_documentation":0}
                }
            except Exception as exc:
                st.error(f"⚠️ Scoring error: {exc}"); return

    result = st.session_state["scoring_result"]
    score = result.get("score", 0)
    bd = result.get("breakdown", {})

    # Dashboard
    st.markdown(
        f'<div style="text-align:center;padding:1.5rem;background:var(--rdti-card);'
        f'border-radius:12px;border:1px solid var(--rdti-border);margin-bottom:1rem;">'
        f'<p style="color:var(--rdti-muted);margin:0;font-size:.9rem;">Compliance Score</p>'
        f'<h1 style="margin:.3rem 0;font-size:3.5rem;color:'
        f'{"#22c55e" if score>=75 else "#eab308" if score>=50 else "#ef4444"}">{score}/100</h1>'
        f'</div>', unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    labels = ["Technical Uncertainty","Systematic Progression","New Knowledge","Evidence & Docs"]
    keys = ["technical_uncertainty","systematic_progression","new_knowledge","evidence_documentation"]
    for col, lbl, k in zip([c1,c2,c3,c4], labels, keys):
        v = bd.get(k, 0)
        col.metric(lbl, f"{v}/25")

    # Red Flags
    flags = result.get("red_flags", [])
    if flags:
        st.markdown("### 🚩 Red Flags / Gaps")
        for f in flags:
            st.markdown(f'<p style="color:#ef4444;">⚠ {f}</p>', unsafe_allow_html=True)

    strengths = result.get("strengths", [])
    if strengths:
        st.markdown("### ✅ Strengths")
        for s in strengths:
            st.markdown(f"- {s}")

    recs = result.get("recommendations", [])
    if recs:
        st.markdown("### 💡 Recommendations")
        for r in recs:
            st.markdown(f"- {r}")

    st.markdown("---")
    c_back, c_fwd = st.columns(2)
    with c_back:
        if st.button("← Go Back & Strengthen Answers", use_container_width=True):
            st.session_state["interview_complete"] = False
            st.session_state["scoring_result"] = {}
            st.session_state["current_stage"] = 3; st.rerun()
    with c_fwd:
        if st.button("Proceed to Final Report →", use_container_width=True):
            st.session_state["current_stage"] = 5; st.rerun()

# ── Stage 5: Final PDF Output ────────────────────────────────────────────────
def render_stage_5():
    render_stage_bar(4)
    st.markdown("## 📄 Stage 5: Final AGLASS R&D Report")

    # Generate if not cached
    if not st.session_state.get("report_text"):
        llm = _llm()
        context = _build_full_context()
        with st.spinner("Evaluating compliance and generating official R&D Report..."):
            try:
                resp = llm.invoke([
                    SystemMessage(content=STAGE_5_SYSTEM_PROMPT),
                    HumanMessage(content=context),
                ])
                st.session_state["report_text"] = resp.content
                st.session_state["pdf_bytes"] = generate_pdf(resp.content)
            except Exception as exc:
                st.error(f"⚠️ Report generation failed: {exc}"); return

    report = st.session_state["report_text"]
    pdf = st.session_state["pdf_bytes"]
    meta = st.session_state["project_metadata"]

    st.markdown('<div class="report-body">', unsafe_allow_html=True)
    st.markdown(report)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### ⬇ Download PDF")
        st.download_button(
            "Download RDTI Report (PDF)", data=pdf,
            file_name=f"RDTI_Report_{meta.get('company_name','report').replace(' ','_')}.pdf",
            mime="application/pdf", use_container_width=True,
        )
    with c2:
        st.markdown("### 🔄 Regenerate")
        if st.button("Regenerate Report", use_container_width=True):
            st.session_state["report_text"] = ""
            st.session_state["pdf_bytes"] = None; st.rerun()

    st.markdown("---")
    if st.button("← Start New Application", use_container_width=True):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("### 🛠 Developer Panel")
        st.markdown(f"**Phase:** `{st.session_state.get('phase','—')}`")
        st.markdown(f"**Stage:** `{st.session_state.get('current_stage','—')}`")
        st.markdown(f"**ABN Valid:** `{st.session_state.get('abn_valid','—')}`")
        st.markdown(f"**Company:** `{st.session_state.get('intake',{}).get('company_name','—')}`")
        st.markdown(f"**Baseline:** `{bool(st.session_state.get('extracted_baseline'))}`")
        st.markdown(f"**Chat msgs:** `{len(st.session_state.get('messages',[]))}`")
        st.markdown(f"**Interview done:** `{st.session_state.get('interview_complete')}`")
        score = st.session_state.get("scoring_result",{}).get("score")
        st.markdown(f"**Score:** `{score if score is not None else '—'}`")
        st.markdown(f"**Report ready:** `{bool(st.session_state.get('report_text'))}`")
        st.markdown("---")
        if st.button("🔄 Reset All State"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

# ── Main Router ───────────────────────────────────────────────────────────────
def main():
    inject_css()
    init_state()
    render_sidebar()
    st.markdown(
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:.5rem;">'
        '<span style="font-size:2.8rem;">🔬</span><div>'
        '<h1 style="margin:0;line-height:1.1;">RDTI AI Agent</h1>'
        '<p style="color:var(--rdti-muted);margin:0;font-size:.9rem;">'
        'Australian R&amp;D Tax Incentive — Application Assistant</p>'
        '</div></div>'
        '<div style="height:1px;background:var(--rdti-border);margin-bottom:1.5rem;"></div>',
        unsafe_allow_html=True,
    )
    phase = st.session_state["phase"]

    # Pre-pipeline phases
    if phase == "intake":
        render_intake()
        return
    if phase == "abn_check":
        render_abn_check()
        return

    # Pipeline stages (phase == "stages")
    stage = st.session_state["current_stage"]
    if stage == 1:   render_stage_1()
    elif stage == 2: render_stage_2()
    elif stage == 3: render_stage_3()
    elif stage == 4: render_stage_4()
    elif stage == 5: render_stage_5()

if __name__ == "__main__":
    main()
