"""
styles.py
─────────
All custom CSS for the RDTI Streamlit app.
Supports both dark and light Streamlit themes.

inject_css() is called once at the top of app.py main().
"""

import streamlit as st


def inject_css() -> None:
    """Inject theme-adaptive stylesheet into the Streamlit page."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

        /* ── Dark theme (default) ── */
        :root {
            --rdti-bg:       #0d1117;
            --rdti-surface:  #161b22;
            --rdti-border:   #30363d;
            --rdti-accent:   #f0a500;
            --rdti-accent2:  #58a6ff;
            --rdti-danger:   #f85149;
            --rdti-success:  #3fb950;
            --rdti-text:     #e6edf3;
            --rdti-muted:    #8b949e;
            --rdti-radius:   8px;
            --rdti-chat-user-bg: #1c2128;
            --rdti-chat-ai-bg:   #161b22;
            --rdti-chat-ai-text: #cdd9e5;
        }

        /* ── Light theme overrides ── */
        @media (prefers-color-scheme: light) {
            :root {
                --rdti-bg:       #ffffff;
                --rdti-surface:  #f6f8fa;
                --rdti-border:   #d0d7de;
                --rdti-accent:   #d48d00;
                --rdti-accent2:  #0969da;
                --rdti-danger:   #cf222e;
                --rdti-success:  #1a7f37;
                --rdti-text:     #1f2328;
                --rdti-muted:    #656d76;
                --rdti-chat-user-bg: #f0f2f5;
                --rdti-chat-ai-bg:   #eaf4ff;
                --rdti-chat-ai-text: #1f2328;
            }
        }

        /* ── Typography base ── */
        [class*="css"] {
            font-family: 'DM Sans', sans-serif;
        }

        /* ── Layout ── */
        .main .block-container { max-width: 860px; padding-top: 2rem; }

        /* ── Headings ── */
        h1 {
            font-family: 'DM Serif Display', serif !important;
            font-size: 2.4rem !important;
            color: var(--rdti-accent) !important;
            letter-spacing: -0.5px;
        }
        h2 {
            font-family: 'DM Serif Display', serif !important;
            font-size: 1.6rem !important;
            color: var(--rdti-text) !important;
        }
        h3 {
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 600 !important;
            font-size: 1.1rem !important;
            color: var(--rdti-accent2) !important;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        /* ── Form controls ── */
        input, textarea, select,
        .stTextInput > div > div > input,
        .stTextArea  > div > div > textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            background-color: var(--rdti-surface) !important;
            border: 1px solid var(--rdti-border) !important;
            color: var(--rdti-text) !important;
            border-radius: var(--rdti-radius) !important;
            font-family: 'DM Mono', monospace !important;
            font-size: 0.9rem !important;
        }
        input:focus, textarea:focus {
            border-color: var(--rdti-accent) !important;
            box-shadow: 0 0 0 2px rgba(240,165,0,0.25) !important;
        }

        /* ── Selectbox / radio / dropdown ── */
        .stSelectbox > div > div,
        .stSelectbox [data-baseweb="select"] > div,
        [data-testid="stSelectbox"] > div > div,
        .stRadio > div {
            background: var(--rdti-surface) !important;
            color: var(--rdti-text) !important;
        }
        .stSelectbox [data-baseweb="select"] span,
        [data-testid="stSelectbox"] span {
            color: var(--rdti-text) !important;
        }
        .stRadio label,
        .stRadio label span {
            color: var(--rdti-text) !important;
        }

        /* ── Form labels ── */
        .stTextInput label,
        .stTextArea label,
        .stSelectbox label,
        .stRadio label,
        [data-testid="stWidgetLabel"] {
            color: var(--rdti-text) !important;
        }

        /* ── Buttons ── */
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {
            background-color: var(--rdti-accent) !important;
            color: #000 !important;
            border: none !important;
            border-radius: var(--rdti-radius) !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.4rem !important;
            transition: opacity 0.2s;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover { opacity: 0.85; }

        /* ── Step progress bar ── */
        .step-bar { display: flex; gap: 6px; margin-bottom: 1.8rem; }
        .step      { flex: 1; height: 4px; border-radius: 2px; background: var(--rdti-border); }
        .step.done { background: var(--rdti-success); }
        .step.active { background: var(--rdti-accent); }

        /* ── Card ── */
        .card {
            background: var(--rdti-surface);
            border: 1px solid var(--rdti-border);
            border-radius: 12px;
            padding: 1.5rem 1.8rem;
            margin-bottom: 1.4rem;
        }

        /* ── Chat bubbles ── */
        .chat-user {
            background: var(--rdti-chat-user-bg);
            border: 1px solid var(--rdti-border);
            border-radius: 12px 12px 2px 12px;
            padding: 0.8rem 1rem;
            margin: 0.4rem 0 0.4rem 3rem;
            font-size: 0.93rem;
            color: var(--rdti-text);
        }
        .chat-ai {
            background: var(--rdti-chat-ai-bg);
            border: 1px solid var(--rdti-accent2);
            border-radius: 2px 12px 12px 12px;
            padding: 0.8rem 1rem;
            margin: 0.4rem 3rem 0.4rem 0;
            font-size: 0.93rem;
            color: var(--rdti-chat-ai-text);
        }

        /* ── Validation feedback ── */
        .val-error { color: var(--rdti-danger);  font-size: 0.85rem; }
        .val-ok    { color: var(--rdti-success); font-size: 0.85rem; }

        /* ── Character counter ── */
        .char-count      { font-family: 'DM Mono', monospace; font-size: 0.78rem; color: var(--rdti-muted); text-align: right; }
        .char-count.warn { color: var(--rdti-danger); }

        /* ── Report body ── */
        .report-body {
            background: var(--rdti-surface);
            border-left: 3px solid var(--rdti-accent);
            padding: 1.5rem;
            border-radius: 0 var(--rdti-radius) var(--rdti-radius) 0;
            font-family: 'DM Mono', monospace;
            font-size: 0.85rem;
            line-height: 1.7;
            white-space: pre-wrap;
            color: var(--rdti-text);
        }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background: var(--rdti-surface) !important;
            border-right: 1px solid var(--rdti-border) !important;
        }

        /* ── Markdown / paragraph text ── */
        .stMarkdown p,
        .stMarkdown li,
        .stMarkdown span {
            color: var(--rdti-text);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
