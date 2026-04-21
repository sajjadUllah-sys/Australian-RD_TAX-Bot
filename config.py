"""
config.py
─────────
App-wide constants: years, industry map, ABN weights, form field specs,
LangChain system prompt, and wizard step labels.
"""

import datetime

# ── Date / year ──────────────────────────────────────────────────────────────
CURRENT_YEAR  = datetime.datetime.now().year
PROJECT_YEARS = list(range(CURRENT_YEAR, 1998, -1))   # newest first

# ── Industry options (plain-language → ANZSIC code) ──────────────────────────
INDUSTRY_OPTIONS: dict[str, str] = {
    "Software & IT":             "ANZSIC 7000 - Computer System Design",
    "Manufacturing":             "ANZSIC 2000 - Manufacturing",
    "Agriculture":               "ANZSIC 0100 - Agriculture, Forestry & Fishing",
    "Mining & Resources":        "ANZSIC 0600 - Mining",
    "Biotechnology & Pharma":    "ANZSIC 1800 - Basic Chemical & Chemical Product Mfg",
    "Construction & Engineering":"ANZSIC 3000 - Construction",
    "Energy & Environment":      "ANZSIC 2600 - Electricity, Gas, Water & Waste Services",
    "Finance & FinTech":         "ANZSIC 6200 - Finance",
    "Health & Medical Devices":  "ANZSIC 8401 - Hospitals",
    "Other":                     "ANZSIC 9999 - Other",
}

# ── ABN validation ────────────────────────────────────────────────────────────
# ATO-specified weighting factors for the Modulo-89 checksum.
ABN_WEIGHTS: list[int] = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]

# ── Continuing-project form field specs ──────────────────────────────────────
CONTINUING_FIELDS: list[dict] = [
    {
        "key":    "experiments",
        "label":  "What experiment/s were conducted in {year} and how did it test the hypothesis?",
        "min":    650,
        "max":    4000,
        "height": 220,
    },
    {
        "key":    "evaluation",
        "label":  "How did you evaluate or plan to evaluate the results from those experiment/s?",
        "min":    530,
        "max":    4000,
        "height": 180,
    },
    {
        "key":    "conclusions",
        "label":  "Describe the conclusions you've reached from the experiment/s.",
        "min":    340,
        "max":    4000,
        "height": 150,
    },
    {
        "key":    "new_knowledge",
        "label":  "What is the New Knowledge?",
        "min":    600,
        "max":    4000,
        "height": 180,
    },
]

# ── Wizard step labels ────────────────────────────────────────────────────────
STEPS: list[str] = ["Intake", "ABN Check", "Project Details", "Report"]

# ── LangChain system prompt ───────────────────────────────────────────────────
RDTI_SYSTEM_PROMPT: str = """
You are a strict but helpful Australian R&D Tax Incentive (RDTI) compliance officer and technical interviewer.
Your role is to guide the applicant through a structured interview to capture all information required
for a valid RDTI claim under AusIndustry guidelines.

You must systematically collect:
1. BASELINE KNOWLEDGE      — What did the applicant already know before the project started?
2. TECHNICAL UNCERTAINTIES — What specific technical unknowns or hypotheses were they testing?
3. CORE R&D ACTIVITIES     — The experimental activities, including hypothesis → methodology → results.
4. EVALUATION METHODS      — How were/will experimental results be evaluated?
5. CONCLUSIONS             — What conclusions were drawn from the experiments?
6. NEW KNOWLEDGE           — What genuinely new knowledge or capability was generated?

Rules:
- Ask ONE focused question at a time.
- Do not accept vague or generic answers — probe with follow-up questions.
- Use precise scientific language. Flag any responses that appear non-technical or commercially motivated
  rather than scientifically driven.
- When you have collected all six categories, say exactly: "INTERVIEW_COMPLETE" on its own line,
  then provide a brief summary of what was gathered.
- Do NOT fabricate technical details. Only use what the applicant tells you.
- If the applicant says something off-topic, redirect them politely but firmly.

Begin by welcoming the applicant and asking them to describe their R&D project in one or two sentences.
"""
