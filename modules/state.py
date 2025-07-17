# modules/state.py

import streamlit as st

def initialize_state():
    """Initializes the session state with default values."""
    defaults = {
        "mode": "Chat with AI",
        "mode_last": "Chat with AI",
        "extracted_items": [],
        "final_items": [],
        "filters_ready": False,
        "site_pref": "Any",
        "sort_pref": "Default",
        "why_explanations": {}
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def reset_state_on_mode_change():
    """Resets the state if the input mode is changed."""
    if st.session_state.mode != st.session_state.mode_last:
        st.session_state.extracted_items = []
        st.session_state.final_items = []
        st.session_state.filters_ready = False
        st.session_state.why_explanations = {}
        st.session_state.mode_last = st.session_state.mode
        st.rerun()