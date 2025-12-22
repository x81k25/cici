"""cici frontend - UI for cici personal assistant."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Build API URL from environment
API_HOST = os.getenv("CICI_API_HOST", "localhost")
API_PORT = os.getenv("CICI_API_PORT", "8765")
API_SECURE = os.getenv("CICI_API_SECURE", "false").lower() == "true"
API_PROTOCOL = "https" if API_SECURE else "http"
API_URL = f"{API_PROTOCOL}://{API_HOST}:{API_PORT}"

# Store config in session state for pages to access
if "api_url" not in st.session_state:
    st.session_state.api_url = API_URL

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
