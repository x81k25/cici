"""cici frontend - UI for cici personal assistant."""

import streamlit as st

# Start metrics server (runs in background thread)
from metrics import start_metrics_server
start_metrics_server()

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

from config import config

# Store config in session state for pages to access
if "api_url" not in st.session_state:
    st.session_state.api_url = config.mind_url

# ------------------------------------------------------------------------------
# Streamlit Configuration
# ------------------------------------------------------------------------------

st.set_page_config(
    page_title="cici",
    page_icon="terminal",
    layout="centered"
)

# ------------------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------------------

chat_page = st.Page("pages/chat.py", title="Chat", icon=":material/chat:", default=True)
testing_page = st.Page("pages/testing.py", title="Testing", icon=":material/science:")

nav = st.navigation([chat_page, testing_page])
nav.run()
