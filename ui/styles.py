"""
ui/styles.py
────────────
Custom CSS injection for modern, polished, dark-themed microdrama dashboard.
"""

import streamlit as st


def inject_custom_styles():
    """Inject polished custom CSS styling."""
    st.markdown("""
        <style>
        /* Overall Page adjustments */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 95%;
        }

        /* Hero Header */
        .hero-container {
            background: linear-gradient(135deg, #1E1B4B 0%, #0F172A 50%, #172554 100%);
            border: 1px solid rgba(99, 102, 241, 0.25);
            border-radius: 16px;
            padding: 2.2rem 2.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(99, 102, 241, 0.1);
            position: relative;
            overflow: hidden;
        }
        .hero-title {
            font-size: 2.4rem;
            font-weight: 800;
            background: linear-gradient(90deg, #A5B4FC 0%, #E0E7FF 50%, #38BDF8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.4rem;
            letter-spacing: -0.02em;
        }
        .hero-subtitle {
            font-size: 1.1rem;
            color: #94A3B8;
            max-width: 800px;
            line-height: 1.5;
        }

        /* Metric Cards */
        .metric-card-box {
            background: #1A1D24;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 1.2rem;
            text-align: left;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .metric-card-box:hover {
            transform: translateY(-2px);
            border-color: rgba(99, 102, 241, 0.4);
        }
        .metric-label {
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94A3B8;
            margin-bottom: 0.3rem;
        }
        .metric-val {
            font-size: 1.8rem;
            font-weight: 700;
            color: #F8FAFC;
        }

        /* Clip Card */
        .clip-card {
            background: #161922;
            border: 1px solid rgba(255, 255, 255, 0.09);
            border-radius: 14px;
            padding: 1.4rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.4);
            transition: all 0.2s ease-in-out;
        }
        .clip-card:hover {
            border-color: rgba(99, 102, 241, 0.45);
            box-shadow: 0 12px 24px -6px rgba(99, 102, 241, 0.15);
        }

        .clip-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding-bottom: 0.8rem;
        }

        /* Quotes */
        .quote-box {
            background: rgba(15, 23, 42, 0.6);
            border-left: 3px solid #6366F1;
            border-radius: 6px;
            padding: 0.8rem 1rem;
            margin: 0.6rem 0;
            font-style: italic;
            color: #E2E8F0;
        }
        .quote-cliff {
            border-left-color: #EC4899;
        }

        /* Badges */
        .score-pill {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.85rem;
        }
        .score-emerald {
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }
        .score-blue {
            background: rgba(59, 130, 246, 0.15);
            color: #60A5FA;
            border: 1px solid rgba(59, 130, 246, 0.4);
        }

        /* Aspect ratio preview mockup */
        .aspect-preview-box {
            display: flex;
            align-items: center;
            justify-content: center;
            background: #0B0F19;
            border: 1px dashed rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            color: #64748B;
            font-size: 0.8rem;
            font-weight: 600;
        }

        /* Custom Scrollbars */
        ::-webkit-scrollbar {
            width: 7px;
            height: 7px;
        }
        ::-webkit-scrollbar-track {
            background: #0E1117;
        }
        ::-webkit-scrollbar-thumb {
            background: #334155;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #475569;
        }
        </style>
    """, unsafe_allow_html=True)
