import streamlit as st


def aplicar_tema():
    st.markdown("""
    <style>
    div.stButton > button,
    div.stFormSubmitButton > button,
    div.stDownloadButton > button {
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        height: auto !important;
        min-height: 2.8rem !important;
        padding: 0.5rem 0.6rem !important;
    }

    div.stButton > button *,
    div.stFormSubmitButton > button *,
    div.stDownloadButton > button * {
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        text-overflow: clip !important;
        overflow: visible !important;
        line-height: 1.25 !important;
        text-align: center !important;
    }

    pre, code {
        white-space: pre-wrap !important;
        word-break: break-word !important;
    }

    @media (max-width: 980px) {
        section.main div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        section.main div[data-testid="column"],
        section.main div[data-testid="stColumn"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
