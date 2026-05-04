"""Domain constants: column names, category & issuer mappings.

Keeping these as plain Python (not Pandera schemas) keeps the domain layer
dependency-free and grep-friendly.
"""

from __future__ import annotations

# --- FDR Category → human-readable asset class --------------------------------
# Verified from fdr.StockListing('ETF/KR') sample on 2026-05-04.

CATEGORY_TO_ASSET_CLASS: dict[int, str] = {
    1: "국내주식 (시장지수)",
    2: "국내주식 (섹터/테마)",
    3: "국내 파생/레버리지/인버스",
    4: "해외주식",
    5: "원자재",
    6: "채권/금리",
    7: "혼합/MMF",
}

ASSET_CLASS_LABELS = list(CATEGORY_TO_ASSET_CLASS.values())


def category_to_asset_class(code: int | None) -> str:
    if code is None:
        return "기타"
    return CATEGORY_TO_ASSET_CLASS.get(int(code), "기타")


# --- Issuer (운용사) inference from name prefix -------------------------------
# Order matters for longest-prefix-match.

_ISSUER_PREFIXES: list[tuple[str, str]] = [
    ("KODEX", "삼성자산운용"),
    ("TIGER", "미래에셋자산운용"),
    ("KBSTAR", "KB자산운용"),  # legacy name pre-RISE rebrand
    ("RISE", "KB자산운용"),
    ("KINDEX", "한국투자신탁운용"),  # legacy
    ("ACE", "한국투자신탁운용"),
    ("KoAct", "한국투자신탁운용"),
    ("ARIRANG", "한화자산운용"),  # legacy
    ("PLUS", "한화자산운용"),
    ("SOL", "신한자산운용"),
    ("KIWOOM", "키움투자자산운용"),
    ("HANARO", "NH-Amundi자산운용"),
    ("1Q", "하나자산운용"),
    ("TIME", "타임폴리오자산운용"),
    ("WON", "우리자산운용"),
    ("BNK", "BNK자산운용"),
    ("HK", "흥국자산운용"),
    ("에셋플러스", "에셋플러스자산운용"),
]


def issuer_from_name(name: str) -> str:
    if not name:
        return "기타"
    upper = name.upper()
    for prefix, issuer in _ISSUER_PREFIXES:
        if upper.startswith(prefix.upper()):
            return issuer
    return "기타"


# --- DataFrame column conventions ---------------------------------------------
# Used by repository <-> analysis to keep names consistent.

class MetaCols:
    TICKER = "ticker"
    NAME = "name"
    CATEGORY = "category"
    ASSET_CLASS = "asset_class"
    ISSUER = "issuer"
    REGION = "region"
    INCEPTION_DATE = "inception_date"
    EXPENSE_RATIO = "expense_ratio"
    BENCHMARK = "benchmark"
    IS_ACTIVE = "is_active"
    UPDATED_AT = "updated_at"


class PriceCols:
    TICKER = "ticker"
    DATE = "date"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
    CHANGE = "change"


class SnapshotCols:
    TICKER = "ticker"
    SNAP_DATE = "snap_date"
    PRICE = "price"
    NAV = "nav"
    MAR_CAP = "mar_cap"  # 억원
    VOLUME = "volume"
    AMOUNT = "amount"  # 백만원 (FDR convention)
    EARNING_RATE = "earning_rate"  # %
    CHANGE_RATE = "change_rate"  # %
