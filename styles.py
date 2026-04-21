"""
styles.py
─────────
All custom CSS for the RDTI Streamlit app.

inject_css() is called once at the top of app.py main().
"""

import streamlit as st


def inject_css() -> None:
    """Inject the full dark-government stylesheet into the Streamlit page."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

        :root {
            --bg:       #0d1117;
            --surface:  #161b22;
            --border:   #30363d;
            --accent:   #f0a500;
            --accent2:  #58a6ff;
            --danger:   #f85149;
            --success:  #3fb950;
            --text:     #e6edf3;
            --muted:    #8b949e;
            --radius:   8px;
        }

        html, body, [class*="css"] {
            background-color: var(--bg) !important;
            color: var(--text) !important;
            font-family: 'DM Sans', sans-serif;
        }

        /* ── Layout ── */
        .main .block-container { max-width: 860px; padding-top: 2rem; }

        /* ── Headings ── */
        h1 {
            font-family: 'DM Serif Display', serif;
            font-size: 2.4rem;
            color: var(--accent);
            letter-spacing: -0.5px;
        }
        h2 {
            font-family: 'DM Serif Display', serif;
            font-size: 1.6rem;
            color: var(--text);
        }
        h3 {
            font-family: 'DM Sans', sans-serif;
            font-weight: 600;
            font-size: 1.1rem;
            color: var(--accent2);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        /* ── Form controls ── */
        input, textarea, select,
        .stTextInput > div > div > input,
        .stTextArea  > div > div > textarea {
            background-color: var(--surface) !important;
            border: 1px solid var(--border) !important;
            color: var(--text) !important;
            border-radius: var(--radius) !important;
            font-family: 'DM Mono', monospace !important;
            font-size: 0.9rem !important;
        }
        input:focus, textarea:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 2px rgba(240,165,0,0.25) !important;
        }

        /* ── Buttons ── */
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {
            background-color: var(--accent) !important;
            color: #000 !important;
            border: none !important;
            border-radius: var(--radius) !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.4rem !important;
            transition: opacity 0.2s;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover { opacity: 0.85; }

        /* ── Step progress bar ── */
        .step-bar { display: flex; gap: 6px; margin-bottom: 1.8rem; }
        .step      { flex: 1; height: 4px; border-radius: 2px; background: var(--border); }
        .step.done { background: var(--success); }
        .step.active { background: var(--accent); }

        /* ── Card ── */
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem 1.8rem;
            margin-bottom: 1.4rem;
        }

        /* ── Chat bubbles ── */
        .chat-user {
            background: #1c2128;
            border: 1px solid var(--border);
            border-radius: 12px 12px 2px 12px;
            padding: 0.8rem 1rem;
            margin: 0.4rem 0 0.4rem 3rem;
            font-size: 0.93rem;
        }
        .chat-ai {
            background: #161b22;
            border: 1px solid var(--accent2);
            border-radius: 2px 12px 12px 12px;
            padding: 0.8rem 1rem;
            margin: 0.4rem 3rem 0.4rem 0;
            font-size: 0.93rem;
            color: #cdd9e5;
        }

        /* ── Validation feedback ── */
        .val-error { color: var(--danger);  font-size: 0.85rem; }
        .val-ok    { color: var(--success); font-size: 0.85rem; }

        /* ── Character counter ── */
        .char-count      { font-family: 'DM Mono', monospace; font-size: 0.78rem; color: var(--muted); text-align: right; }
        .char-count.warn { color: var(--danger); }

        /* ── Report body ── */
        .report-body {
            background: var(--surface);
            border-left: 3px solid var(--accent);
            padding: 1.5rem;
            border-radius: 0 var(--radius) var(--radius) 0;
            font-family: 'DM Mono', monospace;
            font-size: 0.85rem;
            line-height: 1.7;
            white-space: pre-wrap;
        }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background: var(--surface) !important;
            border-right: 1px solid var(--border) !important;
        }

        /* ── Selectbox / radio ── */
        .stSelectbox > div > div,
        .stRadio     > div {
            background: var(--surface) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
