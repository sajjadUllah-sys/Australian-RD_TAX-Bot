"""
report_builder.py
─────────────────
Phase 4 — Report compilation and PDF generation.

  compile_report_from_form()  — builds report text from the continuing-project form
  compile_report_from_chat()  — builds report text from the chatbot interview
  generate_pdf()              — converts report text → formatted PDF bytes (fpdf2)

No Streamlit imports; these are pure utility functions usable by any caller
(Streamlit frontend, Django management command, test suite, etc.).
"""

import datetime
import re

from fpdf import FPDF

from config import INDUSTRY_OPTIONS


# ─────────────────────────────────────────────────────────────────────────────
# Text report builders
# ─────────────────────────────────────────────────────────────────────────────

def _report_header(intake: dict) -> list[str]:
    """Return the common header lines shared by both report types."""
    return [
        "=" * 70,
        "   AUSTRALIAN R&D TAX INCENTIVE -- PROJECT REPORT",
        "=" * 70,
        "",
        f"Company Name      : {intake['company_name']}",
        f"Contact Person    : {intake['contact_person']}",
        f"ABN               : {intake['abn']}",
        f"Industry          : {intake['industry']} "
        f"({INDUSTRY_OPTIONS.get(intake['industry'], '')})",
        f"Project Year      : {intake['project_year']}",
        f"Project Type      : {intake['project_type']}",
        f"Report Generated  : "
        f"{datetime.datetime.now().strftime('%d %B %Y, %H:%M AEST')}",
        "",
    ]


def compile_report_from_form(intake: dict, form_answers: dict) -> str:
    """
    Build a structured RDTI report string from a continuing-project form submission.

    Args:
        intake:       Phase 1 intake dict (company_name, abn, etc.)
        form_answers: Phase 3A answers keyed by field name
                      (experiments, evaluation, conclusions, new_knowledge)

    Returns:
        Multi-line plain-text report string.
    """
    lines = _report_header(intake)
    sections = [
        ("SECTION 1 -- EXPERIMENTAL ACTIVITIES", "experiments"),
        ("SECTION 2 -- EVALUATION METHOD",        "evaluation"),
        ("SECTION 3 -- CONCLUSIONS",              "conclusions"),
        ("SECTION 4 -- NEW KNOWLEDGE",            "new_knowledge"),
    ]
    for title, key in sections:
        lines += [
            "-" * 70,
            title,
            "-" * 70,
            form_answers.get(key, ""),
            "",
        ]
    lines += [
        "=" * 70,
        "END OF REPORT -- CONFIDENTIAL",
        "=" * 70,
    ]
    return "\n".join(lines)


def compile_report_from_chat(
    intake: dict, chat_summary: str, messages: list[dict]
) -> str:
    """
    Build a structured RDTI report string from the chatbot interview.

    Args:
        intake:       Phase 1 intake dict.
        chat_summary: AI-generated summary extracted after INTERVIEW_COMPLETE.
        messages:     Full st.session_state["messages"] list.

    Returns:
        Multi-line plain-text report string (includes full transcript).
    """
    lines = _report_header(intake)
    lines += [
        "-" * 70,
        "AI INTERVIEW SUMMARY",
        "-" * 70,
        chat_summary,
        "",
        "-" * 70,
        "FULL CONVERSATION TRANSCRIPT",
        "-" * 70,
    ]
    for msg in messages:
        role_label = "APPLICANT" if msg["role"] == "user" else "RDTI OFFICER"
        lines.append(f"\n[{role_label}]\n{msg['content']}")
    lines += [
        "",
        "=" * 70,
        "END OF REPORT -- CONFIDENTIAL",
        "=" * 70,
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# PDF generation
# ─────────────────────────────────────────────────────────────────────────────

# Characters outside Latin-1 that fpdf's built-in Helvetica cannot render.
_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u2014": "--",   # em-dash
    "\u2013": "-",    # en-dash
    "\u2018": "'",    # left single curly quote
    "\u2019": "'",    # right single curly quote
    "\u201C": '"',    # left double curly quote
    "\u201D": '"',    # right double curly quote
    "\u2026": "...",  # ellipsis
    "\u2500": "-",    # box-drawing horizontal
    "\u2550": "=",    # box-drawing double horizontal
    "\u00A0": " ",    # non-breaking space
}


def _sanitize(text: str) -> str:
    """Replace non-Latin-1 characters so fpdf's built-in fonts can render them."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-Latin-1 characters to prevent encoding crashes
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _RDTIPdf(FPDF):
    """FPDF subclass with consistent RDTI header, dark background, and footer."""

    def header(self):
        # Dark background fill on every page (not just the first)
        self.set_fill_color(13, 17, 23)
        self.rect(0, 0, 210, 297, "F")

        self.set_font("Helvetica", "B", 9)
        self.set_text_color(180, 140, 0)
        self.cell(
            0, 8,
            "AUSTRALIAN R&D TAX INCENTIVE -- CONFIDENTIAL REPORT",
            align="C",
        )
        self.ln(4)
        self.set_draw_color(48, 54, 61)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(139, 148, 158)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def generate_pdf(report_text: str) -> bytes:
    """
    Convert a plain-text report string into a formatted dark-themed PDF.

    Formatting rules applied line-by-line:
      - Lines starting with "-" or "=" -> horizontal rule
      - Lines matching "LABEL   : value" -> label in amber, value in light text
      - Lines starting with "SECTION", "AI INTERVIEW", "FULL CONVER" -> section header
      - All other lines -> standard body text (multi_cell for word-wrap)

    Args:
        report_text: Plain-text string from compile_report_from_form/chat().

    Returns:
        Raw PDF bytes suitable for st.download_button or HTTP file response.
    """
    # Sanitise the entire report text up front
    report_text = _sanitize(report_text)

    pdf = _RDTIPdf()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(230, 237, 243)

    for line in report_text.split("\n"):

        # Horizontal rules
        if line.startswith("-") or line.startswith("="):
            pdf.set_draw_color(48, 54, 61)
            pdf.ln(1)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
            continue

        # Key : value metadata lines (amber key, white value)
        if re.match(r"^[A-Z][A-Za-z\s]+\s+:", line):
            parts = line.split(":", 1)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(240, 165, 0)
            pdf.write(5, parts[0] + ":")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(230, 237, 243)
            pdf.write(5, parts[1] if len(parts) > 1 else "")
            pdf.ln(6)
            continue                        # ← prevent fall-through

        # Section titles (blue)
        if line.startswith(("SECTION", "AI INTERVIEW", "FULL CONVER", "END OF REPORT")):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(88, 166, 255)
            pdf.multi_cell(0, 6, line)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(230, 237, 243)
            continue

        # Body text — reset X to left margin to guard against cursor drift
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, line if line.strip() else " ")

    return bytes(pdf.output())
