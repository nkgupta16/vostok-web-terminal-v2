"""
Vostok Web Terminal - Triple-Layer Credential System
Priority: 1) Manual Override (sidebar) -> 2) Local .env -> 3) Streamlit Secrets
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Load .env at module import (layer 2)
load_dotenv()


def get_invest_token() -> str:
    """
    Resolve T-Bank Invest API token using triple-layer priority.

    1. **Manual Override** – value typed into the sidebar password input
       (stored in ``st.session_state["manual_token"]``).
    2. **Local .env** – ``INVEST_TOKEN`` loaded via python-dotenv.
    3. **Streamlit Cloud Secrets** – ``st.secrets["INVEST_TOKEN"]``.

    Returns
    -------
    str
        The resolved token string, or ``""`` if none found.
    """
    # Layer 1: Manual sidebar override
    manual = st.session_state.get("manual_token", "").strip()
    if manual:
        return manual

    # Layer 2: Local .env file
    env_token = os.getenv("INVEST_TOKEN", "").strip()
    if env_token:
        return env_token

    # Layer 3: Streamlit Cloud secrets
    try:
        secret = st.secrets.get("INVEST_TOKEN", "").strip()
        if secret:
            return secret
    except Exception:
        pass

    return ""


def get_token_source() -> str:
    """Return a human-readable label for the active token source."""
    manual = st.session_state.get("manual_token", "").strip()
    if manual:
        return "Manual Override"

    env_token = os.getenv("INVEST_TOKEN", "").strip()
    if env_token:
        return ".env File"

    try:
        secret = st.secrets.get("INVEST_TOKEN", "").strip()
        if secret:
            return "Streamlit Secrets"
    except Exception:
        pass

    return "None"


def verify_token(token: str) -> tuple[bool, str]:
    """
    Verify token by calling T-Bank ``get_accounts()``.

    Returns
    -------
    tuple[bool, str]
        ``(True, account_info)`` on success, ``(False, error_message)`` on failure.
    """
    if not token:
        return False, "No token provided"

    try:
        from t_tech.invest import Client
        with Client(token) as client:
            accounts = client.users.get_accounts()
            count = len(accounts.accounts)
            ids = ", ".join(a.id for a in accounts.accounts[:3])
            return True, f"{count} account(s): {ids}"
    except Exception as exc:
        return False, str(exc)[:120]


def render_sidebar_auth():
    """
    Render the authentication controls in the Streamlit sidebar.

    Includes manual token input, connection status indicator, and source badge.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔑 API Credentials")

    # Manual token input (Layer 1)
    st.sidebar.text_input(
        "Token Override",
        type="password",
        key="manual_token",
        placeholder="Paste T-Bank token...",
        help="Overrides .env and Streamlit secrets when set.",
    )

    token = get_invest_token()
    source = get_token_source()

    if token:
        st.sidebar.success(f"Source: **{source}**")

        # Verify connection (cached per session run to avoid spamming API)
        if "token_verified" not in st.session_state or st.session_state.get("_last_token") != token:
            ok, info = verify_token(token)
            st.session_state["token_verified"] = ok
            st.session_state["token_info"] = info
            st.session_state["_last_token"] = token

        if st.session_state.get("token_verified"):
            st.sidebar.markdown(f"🟢 **Connected** - {st.session_state['token_info']}")
        else:
            st.sidebar.markdown(f"🔴 **Error** - {st.session_state.get('token_info', 'Unknown')}")
    else:
        st.sidebar.warning("No token — set via sidebar, `.env`, or Streamlit secrets.")
