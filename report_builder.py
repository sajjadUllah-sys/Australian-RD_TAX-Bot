"""
report_builder.py
─────────────────
Phase 4 — Report compilation and PDF generation.

  compile_report_from_form()  — builds report text from the continuing-project form
  compile_report_from_chat()  — builds report text from the chatbot interview
  generate_pdf()              — converts Markdown report text → formatted PDF bytes (fpdf2)

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
# PDF generation — Markdown-aware
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
    """FPDF subclass with consistent RDTI header, white background, and footer."""

    def header(self):
        # ── White background on every page ────────────────────────────────
        self.set_fill_color(255, 255, 255)          # #FFFFFF
        self.rect(0, 0, 210, 297, "F")

        self.set_font("Helvetica", "B", 9)
        self.set_text_color(0, 51, 102)              # dark navy title
        self.cell(
            0, 8,
            "AUSTRALIAN R&D TAX INCENTIVE -- CONFIDENTIAL REPORT",
            align="C",
        )
        self.ln(4)
        self.set_draw_color(180, 180, 180)            # light-gray rule
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)            # mid-gray page number
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _render_markdown_line(pdf: _RDTIPdf, line: str) -> None:
    """
    Render a single line of text that may contain inline **bold** markers.
    Splits the line on bold boundaries and toggles font weight accordingly.
    """
    # Split on **...**  patterns, keeping the delimited text
    parts = re.split(r"\*\*(.+?)\*\*", line)
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:
            # Odd-index parts are the bold-delimited text
            pdf.set_font("Helvetica", "B", 9)
            pdf.write(5, part)
            pdf.set_font("Helvetica", "", 9)
        else:
            pdf.write(5, part)
    pdf.ln(6)


def generate_pdf(report_text: str) -> bytes:
    """
    Convert a Markdown-formatted report string into a formatted white-background PDF.

    The function understands these Markdown constructs produced by the LLM:
      - # H1 / ## H2 / ### H3 headings
      - **bold** inline markers
      - Lines starting with "- " or "* " → bullet list items
      - Lines starting with "-" or "=" (plain-text separators) → horizontal rule
      - Lines matching "LABEL   : value" → label in dark blue, value in black
      - Lines starting with "SECTION", "AI INTERVIEW", "FULL CONVER" → legacy section header
      - All other lines → standard body text (with inline bold support)

    Args:
        report_text: Markdown string from the LLM or compile_report_from_form/chat().

    Returns:
        Raw PDF bytes suitable for st.download_button or HTTP file response.
    """
    # Sanitise the entire report text up front
    report_text = _sanitize(report_text)

    pdf = _RDTIPdf()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── Default body text: black on white ─────────────────────────────────
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)                       # #000000

    for line in report_text.split("\n"):
        stripped = line.strip()

        # ── Markdown headings ─────────────────────────────────────────────
        if stripped.startswith("### "):
            heading_text = stripped[4:].strip()
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 70, 140)            # blue heading
            pdf.multi_cell(0, 6, heading_text)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            continue

        if stripped.startswith("## "):
            heading_text = stripped[3:].strip()
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 51, 102)            # dark navy
            pdf.multi_cell(0, 7, heading_text)
            # Thin rule under H2
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            continue

        if stripped.startswith("# "):
            heading_text = stripped[2:].strip()
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(0, 40, 80)             # deep navy
            pdf.multi_cell(0, 8, heading_text)
            pdf.set_draw_color(0, 51, 102)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            continue

        # ── Markdown tables ────────────────────────────────────────────
        if stripped.startswith("|") and stripped.endswith("|"):
            # Table separator row (|---|---|...) → skip
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Detect header row (first table row) vs data row
            is_header = all("**" not in c for c in cells) and pdf.get_y() > 0
            col_w = (190 - pdf.l_margin) / max(len(cells), 1)
            pdf.set_x(pdf.l_margin)
            for cell in cells:
                # Strip inline bold markers for clean text
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", cell)
                pdf.set_font("Helvetica", "B" if is_header else "", 8)
                pdf.set_text_color(0, 51, 102) if is_header else pdf.set_text_color(0, 0, 0)
                pdf.cell(col_w, 6, clean, border=1, align="C" if is_header else "L")
            pdf.ln()
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            continue

        # ── Checkbox list items (- [x] or - [ ]) ─────────────────────
        chk_match = re.match(r"^- \[([ xX])\]\s*(.*)", stripped)
        if chk_match:
            checked = chk_match.group(1).lower() == "x"
            chk_text = chk_match.group(2)
            pdf.set_x(pdf.l_margin + 6)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            marker = "[X] " if checked else "[ ] "
            pdf.write(5, marker)
            # Handle inline bold within checkbox text
            parts = re.split(r"\*\*(.+?)\*\*", chk_text)
            for i, part in enumerate(parts):
                if not part:
                    continue
                if i % 2 == 1:
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.write(5, part)
                    pdf.set_font("Helvetica", "", 9)
                else:
                    pdf.write(5, part)
            pdf.ln(5)
            continue

        # ── Bullet list items ─────────────────────────────────────────────
        if re.match(r"^[-*]\s+", stripped):
            bullet_text = re.sub(r"^[-*]\s+", "", stripped)
            pdf.set_x(pdf.l_margin + 6)               # indent bullets
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.write(5, "- ")                      # Latin-1 safe bullet marker
            # Handle inline bold within bullet text
            parts = re.split(r"\*\*(.+?)\*\*", bullet_text)
            for i, part in enumerate(parts):
                if not part:
                    continue
                if i % 2 == 1:
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.write(5, part)
                    pdf.set_font("Helvetica", "", 9)
                else:
                    pdf.write(5, part)
            pdf.ln(5)
            continue

        # ── Plain-text horizontal rules ───────────────────────────────────
        if stripped and all(c in "-=" for c in stripped) and len(stripped) >= 3:
            pdf.set_draw_color(180, 180, 180)
            pdf.ln(1)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
            continue

        # ── Key : value metadata lines (dark-blue key, black value) ───────
        if re.match(r"^[A-Z][A-Za-z\s]+\s+:", stripped):
            parts = stripped.split(":", 1)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(0, 51, 102)
            pdf.write(5, parts[0] + ":")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.write(5, parts[1] if len(parts) > 1 else "")
            pdf.ln(6)
            continue

        # ── Legacy section titles (dark blue) ─────────────────────────────
        if stripped.startswith(("SECTION", "AI INTERVIEW", "FULL CONVER", "END OF REPORT")):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 70, 140)
            pdf.multi_cell(0, 6, stripped)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            continue

        # ── Body text with inline bold support ────────────────────────────
        pdf.set_x(pdf.l_margin)
        if not stripped:
            pdf.ln(3)                                  # blank line → small gap
        elif "**" in stripped:
            _render_markdown_line(pdf, stripped)
        else:
            pdf.multi_cell(0, 5, stripped)

    return bytes(pdf.output())
