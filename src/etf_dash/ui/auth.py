"""Simple password gate for the Streamlit app.

Usage at the top of app.py and every page:
    from etf_dash.ui.auth import require_password
    require_password()

Password is read from .streamlit/secrets.toml (key: app_password) or the
APP_PASSWORD env var. If neither is set, the gate refuses to start so we
never accidentally serve the app without auth.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st


def _expected_password() -> str | None:
    pw = os.environ.get("APP_PASSWORD")
    if pw:
        return pw
    try:
        return st.secrets["app_password"]
    except Exception:  # noqa: BLE001 — st.secrets failure modes vary across versions
        return None


def require_password() -> None:
    """Block rendering until the user enters the correct password.

    On first visit, shows a password input. On match, stores
    `authenticated=True` in session_state so subsequent reruns skip the gate.
    """
    if st.session_state.get("authenticated"):
        return

    expected = _expected_password()
    if not expected or expected == "change-me-to-a-long-password":
        st.error(
            "🔒 인증이 설정되지 않았습니다.\n\n"
            "`.streamlit/secrets.toml`을 만들고 `app_password = \"...\"`를 설정한 다음 "
            "Streamlit을 재시작하세요. 외부 노출 시 안전을 위해 비번 없이는 동작하지 않습니다."
        )
        st.stop()

    st.markdown("### 🔒 DeepPool")
    pw = st.text_input("비밀번호", type="password", key="_pw_input")
    if not pw:
        st.stop()
    if hmac.compare_digest(pw, expected):
        st.session_state["authenticated"] = True
        # Clear the input from state and rerun to load the actual page.
        del st.session_state["_pw_input"]
        st.rerun()
    else:
        st.error("비밀번호가 올바르지 않습니다.")
        st.stop()
