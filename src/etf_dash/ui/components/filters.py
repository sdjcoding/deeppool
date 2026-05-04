"""Sidebar filter widgets for the screener."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def screener_sidebar(meta: pd.DataFrame) -> dict:
    """Render filters in the sidebar and return the active filter spec."""
    st.sidebar.header("필터")

    name_query = st.sidebar.text_input("이름/코드 검색", value="").strip()

    asset_class_options = sorted(meta["asset_class"].dropna().unique().tolist())
    asset_classes = st.sidebar.multiselect(
        "자산군", asset_class_options, default=[]
    )

    issuer_options = sorted(meta["issuer"].dropna().unique().tolist())
    issuers = st.sidebar.multiselect(
        "운용사", issuer_options, default=[]
    )

    return {
        "name_query": name_query,
        "asset_classes": asset_classes,
        "issuers": issuers,
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = df
    if filters["name_query"]:
        q = filters["name_query"].lower()
        out = out[
            out["name"].str.lower().str.contains(q, na=False)
            | out["ticker"].str.lower().str.contains(q, na=False)
        ]
    if filters["asset_classes"]:
        out = out[out["asset_class"].isin(filters["asset_classes"])]
    if filters["issuers"]:
        out = out[out["issuer"].isin(filters["issuers"])]
    return out
