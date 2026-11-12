"""CSS Design System and styling tokens for STRATOS interactive dashboard.

Implements the high-fidelity dark motorsport pit-wall visual identity matching the
STRATOS Race Strategy Intelligence specification.
"""

from __future__ import annotations


def get_css(is_dark: bool = True) -> str:
    """Generate dynamic CSS stylesheet matching the reference pit-wall dashboard."""
    bg = "#0b111e" if is_dark else "#f8fafc"
    sidebar_bg = "#0d1527" if is_dark else "#ffffff"
    card = "#111b2e" if is_dark else "#ffffff"
    card_subtle = "#0e1829" if is_dark else "#f1f5f9"
    card_hover = "#15233c" if is_dark else "#f1f5f9"
    border = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
    border_strong = "rgba(255, 255, 255, 0.14)" if is_dark else "rgba(0, 0, 0, 0.14)"
    text = "#f8fafc" if is_dark else "#0f172a"
    text_muted = "#94a3b8" if is_dark else "#64748b"
    text_dim = "#64748b" if is_dark else "#94a3b8"

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {{
        --bg: {bg};
        --sidebar-bg: {sidebar_bg};
        --card: {card};
        --card-subtle: {card_subtle};
        --card-hover: {card_hover};
        --border: {border};
        --border-strong: {border_strong};
        --text: {text};
        --text-muted: {text_muted};
        --text-dim: {text_dim};
        --accent-blue: #0284c7;
        --accent-cyan: #38bdf8;
        --accent-green: #10b981;
        --accent-yellow: #f59e0b;
        --accent-red: #ef4444;
        --radius: 8px;
    }}

    /* Hide Streamlit default chrome */
    header[data-testid="stHeader"], #MainMenu, footer,
    [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton,
    div[data-testid="stSidebarCollapsedControl"] {{
        display: none !important;
    }}

    /* Canvas & Global typography */
    html, body, [data-testid="stAppViewContainer"],
    [data-testid="stApp"], .main, section[data-testid="stMain"] {{
        background-color: var(--bg) !important;
        color: var(--text) !important;
        font-family: 'DM Sans', -apple-system, sans-serif !important;
    }}

    .block-container {{
        padding: 1rem 1.8rem 2.5rem !important;
        max-width: 1560px !important;
    }}

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {{
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--border) !important;
        padding-top: 1rem !important;
    }}

    section[data-testid="stSidebar"] div.block-container {{
        padding: 1rem 1.1rem !important;
    }}

    /* Brand Logo Sidebar */
    .sidebar-brand {{
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding-bottom: 1.25rem;
        margin-bottom: 0.75rem;
        border-bottom: 1px solid var(--border);
    }}
    .sidebar-brand-icon {{
        font-size: 1.5rem;
        color: var(--accent-cyan);
    }}
    .sidebar-brand-title {{
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: 0.05em;
        color: #ffffff;
        line-height: 1.1;
    }}
    .sidebar-brand-sub {{
        font-size: 0.62rem;
        letter-spacing: 0.12em;
        color: var(--accent-cyan);
        font-weight: 600;
        margin-top: 2px;
    }}

    .sidebar-section-title {{
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: var(--text-dim);
        text-transform: uppercase;
        margin: 1.25rem 0 0.5rem 0.4rem;
    }}

    .sidebar-item {{
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        font-size: 0.84rem;
        font-weight: 500;
        color: var(--text-muted);
        text-decoration: none;
        margin-bottom: 0.15rem;
        transition: all 0.15s ease;
    }}
    .sidebar-item:hover {{
        background-color: rgba(255, 255, 255, 0.04);
        color: #ffffff;
    }}
    .sidebar-item.active {{
        background-color: var(--accent-blue);
        color: #ffffff;
        font-weight: 600;
    }}

    /* Top Navigation Header */
    .top-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 0.9rem;
        margin-bottom: 0.9rem;
        border-bottom: 1px solid var(--border);
        flex-wrap: wrap;
        gap: 0.8rem;
    }}
    .event-info {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }}
    .event-flag {{
        font-size: 1.7rem;
        line-height: 1;
    }}
    .event-title {{
        font-size: 1.35rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.01em;
    }}
    .event-subtitle {{
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-top: 2px;
    }}

    .telemetry-pills {{
        display: flex;
        align-items: center;
        gap: 1.25rem;
        background: var(--card);
        padding: 0.4rem 1rem;
        border-radius: 8px;
        border: 1px solid var(--border);
    }}
    .telemetry-pill-item {{
        display: flex;
        flex-direction: column;
        font-size: 0.72rem;
        color: var(--text-dim);
    }}
    .telemetry-pill-val {{
        font-size: 0.92rem;
        font-weight: 700;
        color: #ffffff;
        font-family: 'JetBrains Mono', monospace;
    }}

    /* Sub-Navigation Pill Tabs */
    button[data-baseweb="tab"] {{
        background: transparent !important;
        color: var(--text-muted) !important;
        font-size: 0.84rem !important;
        font-weight: 500 !important;
        padding: 0.45rem 1.1rem !important;
        border: 1px solid transparent !important;
        border-radius: 6px !important;
        margin-right: 0.3rem !important;
        transition: all 0.15s ease !important;
    }}
    button[data-baseweb="tab"]:hover {{
        background: rgba(255, 255, 255, 0.04) !important;
        color: #ffffff !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        background: var(--accent-blue) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }}
    div[data-baseweb="tab-highlight"] {{
        display: none !important;
    }}
    div[data-baseweb="tab-border"] {{
        display: none !important;
    }}

    /* Card Panels */
    .dashboard-card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.1rem 1.2rem;
        margin-bottom: 1.1rem;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
    }}
    .card-header-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.75rem;
    }}
    .card-title {{
        font-size: 0.92rem;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: -0.01em;
    }}
    .card-subtitle {{
        font-size: 0.74rem;
        color: var(--text-muted);
        margin-top: 1px;
    }}

    /* Recommended Strategy Banner */
    .rec-strategy-box {{
        background: var(--card-subtle);
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        padding: 0.85rem 1rem;
        margin: 0.6rem 0 0.8rem;
    }}
    .rec-strategy-title {{
        font-size: 0.98rem;
        font-weight: 700;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}
    .rec-metrics-row {{
        display: flex;
        gap: 1.4rem;
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-top: 0.5rem;
        flex-wrap: wrap;
    }}
    .rec-metrics-row strong {{
        color: #ffffff;
        font-family: 'JetBrains Mono', monospace;
    }}

    /* Key Drivers List */
    .driver-list-item {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.35rem 0;
        font-size: 0.8rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    }}
    .driver-pill-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        font-size: 0.68rem;
        font-weight: 700;
        margin-right: 0.45rem;
    }}

    /* Badges */
    .badge {{
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.70rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }}
    .badge-green {{
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .badge-blue {{
        background: rgba(2, 132, 199, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(2, 132, 199, 0.3);
    }}
    .badge-soft {{
        color: #ef4444; background: rgba(239,68,68,0.14); border: 1px solid rgba(239,68,68,0.3);
    }}
    .badge-medium {{
        color: #eab308; background: rgba(234,179,8,0.14); border: 1px solid rgba(234,179,8,0.3);
    }}
    .badge-hard {{
        color: #f8fafc; background: rgba(248,250,252,0.12); border: 1px solid rgba(248,250,252,0.3);
    }}

    /* Tables */
    .f1-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.78rem;
    }}
    .f1-table th {{
        text-align: left;
        padding: 0.55rem 0.6rem;
        color: var(--text-dim);
        font-size: 0.70rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-bottom: 1px solid var(--border);
    }}
    .f1-table td {{
        padding: 0.55rem 0.6rem;
        color: var(--text-muted);
        border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        font-family: 'DM Sans', sans-serif;
    }}
    .f1-table tr:hover td {{
        background: rgba(255, 255, 255, 0.02);
    }}
    .f1-table tr.highlight-stratos td {{
        background: rgba(2, 132, 199, 0.12) !important;
        color: #ffffff !important;
        font-weight: 600;
    }}
    .f1-table td.mono {{
        font-family: 'JetBrains Mono', monospace;
    }}

    /* Statistical KPI Grid */
    .stat-kpi-box {{
        background: var(--card-subtle);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.65rem 0.8rem;
    }}
    .stat-kpi-label {{
        font-size: 0.70rem;
        color: var(--text-dim);
        margin-bottom: 0.2rem;
    }}
    .stat-kpi-value {{
        font-size: 1.18rem;
        font-weight: 700;
        color: #ffffff;
        font-family: 'JetBrains Mono', monospace;
    }}
    .stat-kpi-delta {{
        font-size: 0.68rem;
        margin-top: 0.15rem;
    }}
    .delta-pos {{ color: #10b981; }}
    .delta-neg {{ color: #ef4444; }}

    /* AI Reasoning Box */
    .reasoning-item {{
        display: flex;
        gap: 0.5rem;
        margin-bottom: 0.5rem;
        font-size: 0.76rem;
        line-height: 1.4;
        color: var(--text-muted);
    }}
    .reasoning-bullet {{
        color: #10b981;
        font-size: 0.85rem;
        line-height: 1;
        flex-shrink: 0;
    }}

    /* Action Buttons */
    .stratos-btn {{
        background: var(--accent-blue);
        color: #ffffff !important;
        border: none;
        padding: 0.45rem 1rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        display: inline-block;
        transition: opacity 0.15s ease;
    }}
    .stratos-btn:hover {{
        opacity: 0.9;
    }}
    .stratos-btn-outline {{
        background: transparent;
        color: var(--text-muted) !important;
        border: 1px solid var(--border-strong);
        padding: 0.35rem 0.85rem;
        border-radius: 6px;
        font-size: 0.74rem;
        cursor: pointer;
        display: inline-block;
        text-decoration: none;
    }}
    .stratos-btn-outline:hover {{
        background: rgba(255, 255, 255, 0.04);
        color: #ffffff !important;
    }}

    /* Multi-Agent Dialogue Speech Bubbles */
    .dialogue-bubble {{
        background: var(--card-subtle);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.65rem 0.85rem;
        margin-bottom: 0.65rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}
    .dialogue-bubble:hover {{
        border-color: var(--border-strong);
        transform: translateX(2px);
    }}
    .dialogue-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.3rem;
    }}
    .dialogue-agent {{
        font-weight: 700;
        font-size: 0.82rem;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}
    .dialogue-role {{
        font-size: 0.68rem;
        color: var(--text-dim);
        font-weight: 500;
    }}
    .dialogue-text {{
        font-size: 0.77rem;
        line-height: 1.45;
        color: var(--text-muted);
    }}
    .dialogue-directive {{
        display: inline-block;
        font-size: 0.70rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        padding: 0.2rem 0.55rem;
        border-radius: 4px;
        margin-top: 0.45rem;
        letter-spacing: 0.04em;
    }}
    </style>
    """

