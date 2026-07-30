"""
Normalization layer for messy monday.com board exports.

Handles, based on direct inspection of the real sample data:
- Stray header rows embedded as data rows (spreadsheet export artifact)
- Inconsistent / blank dates -> pd.NaT via coercion, never crashes
- Sector vocabulary mismatch between the two boards (Deals has 12 sectors,
  Work Orders has 6) -> canonical mapping so cross-board queries work
- Multi-value "Type of Work" fields (comma separated) -> exploded/split
- Numeric fields arriving as text with blanks -> coerced to float, NaN-safe
- Every row gets a `data_quality_flags` list so the agent can disclose
  caveats instead of silently dropping or fabricating data
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# Canonical sector mapping. Deals board has a superset of sectors vs Work
# Orders. We map both to one canonical vocabulary so "energy sector" style
# queries can span both boards. "Energy" isn't a literal label in this data —
# founders often mean Renewables/Powerline when they say "energy sector", so
# the agent (agent.py) also does a light semantic alias step for that term.
# ---------------------------------------------------------------------------
CANONICAL_SECTORS = [
    "Mining", "Powerline", "Construction", "Railways", "Renewables",
    "Aviation", "Manufacturing", "Security and Surveillance", "DSP",
    "Tender", "Others",
]


def _canonical_sector(raw: str | float) -> str:
    if pd.isna(raw) or not str(raw).strip():
        return "Unspecified"
    raw = str(raw).strip()
    match = process.extractOne(raw, CANONICAL_SECTORS, scorer=fuzz.WRatio)
    if match and match[1] >= 80:
        return match[0]
    return raw  # keep original if no confident match, flagged separately


def _is_stray_header_row(row: pd.Series, columns: list[str]) -> bool:
    """Detect rows where cell values literally equal their own column names —
    a known artifact in the Deals export (e.g. Deal Stage == 'Deal Stage')."""
    hits = 0
    for col in columns:
        val = row.get(col)
        if isinstance(val, str) and val.strip() == col.strip():
            hits += 1
    return hits >= 2  # require 2+ matches to avoid false positives


def _safe_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="mixed")


def _safe_float(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def clean_deals(raw_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return df

    header_check_cols = ["Deal Status", "Deal Stage", "Sector/service", "Closure Probability"]
    header_check_cols = [c for c in header_check_cols if c in df.columns]
    stray_mask = df.apply(lambda r: _is_stray_header_row(r, header_check_cols), axis=1)
    n_stray = int(stray_mask.sum())
    df = df[~stray_mask].copy()

    df["data_quality_flags"] = [[] for _ in range(len(df))]

    # Dates
    for col in ["Close Date (A)", "Tentative Close Date", "Created Date"]:
        if col in df.columns:
            df[col + "_parsed"] = _safe_date(df[col])

    # Deal value
    if "Masked Deal value" in df.columns:
        df["deal_value_num"] = _safe_float(df["Masked Deal value"])
        df.loc[df["deal_value_num"].isna(), "data_quality_flags"] = df.loc[
            df["deal_value_num"].isna(), "data_quality_flags"
        ].apply(lambda flags: flags + ["missing_deal_value"])

    # Sector normalization
    if "Sector/service" in df.columns:
        df["sector_canonical"] = df["Sector/service"].apply(_canonical_sector)
        df.loc[df["sector_canonical"] == "Unspecified", "data_quality_flags"] = df.loc[
            df["sector_canonical"] == "Unspecified", "data_quality_flags"
        ].apply(lambda flags: flags + ["missing_sector"])

    # Missing close date flag (only meaningful for Won/Lost deals)
    if "Deal Status" in df.columns and "Close Date (A)_parsed" in df.columns:
        won_lost = df["Deal Status"].isin(["Won", "Dead"])
        missing_close = df["Close Date (A)_parsed"].isna()
        idx = df.index[won_lost & missing_close]
        for i in idx:
            df.at[i, "data_quality_flags"] = df.at[i, "data_quality_flags"] + ["missing_close_date"]

    df.attrs["rows_dropped_stray_header"] = n_stray
    df.attrs["total_rows"] = len(df)
    return df


def clean_work_orders(raw_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return df

    df["data_quality_flags"] = [[] for _ in range(len(df))]

    date_cols = [
        "Data Delivery Date", "Date of PO/LOI", "Probable Start Date",
        "Probable End Date", "Last invoice date", "Collection Date",
    ]
    for col in date_cols:
        if col in df.columns:
            df[col + "_parsed"] = _safe_date(df[col])

    amount_cols = [
        "Amount in Rupees (Excl of GST) (Masked)",
        "Amount in Rupees (Incl of GST) (Masked)",
        "Billed Value in Rupees (Excl of GST.) (Masked)",
        "Billed Value in Rupees (Incl of GST.) (Masked)",
        "Collected Amount in Rupees (Incl of GST.) (Masked)",
        "Amount to be billed in Rs. (Exl. of GST) (Masked)",
        "Amount to be billed in Rs. (Incl. of GST) (Masked)",
        "Amount Receivable (Masked)",
    ]
    for col in amount_cols:
        if col in df.columns:
            df[col + "_num"] = _safe_float(df[col])

    if "Sector" in df.columns:
        df["sector_canonical"] = df["Sector"].apply(_canonical_sector)

    # Multi-value Type of Work -> list
    if "Type of Work" in df.columns:
        df["type_of_work_list"] = df["Type of Work"].fillna("").apply(
            lambda s: [t.strip() for t in s.split(",") if t.strip()]
        )

    # Flag rows with no billed/collected data despite being "Completed"
    if "Execution Status" in df.columns and "Collected Amount in Rupees (Incl of GST.) (Masked)_num" in df.columns:
        completed = df["Execution Status"] == "Completed"
        no_collection = df["Collected Amount in Rupees (Incl of GST.) (Masked)_num"].isna()
        idx = df.index[completed & no_collection]
        for i in idx:
            df.at[i, "data_quality_flags"] = df.at[i, "data_quality_flags"] + ["completed_but_uncollected"]

    df.attrs["total_rows"] = len(df)
    return df


def join_deal_name(name: str | float) -> str:
    """Normalize a deal name for cross-board joining (case/whitespace only —
    these are masked codename fields like 'Scooby-Doo', not free text)."""
    if pd.isna(name):
        return ""
    return str(name).strip().lower()


def data_quality_summary(df: pd.DataFrame, label: str) -> dict:
    if df.empty:
        return {"board": label, "total_rows": 0, "issues": {}}
    all_flags = [f for flags in df.get("data_quality_flags", []) for f in flags]
    from collections import Counter
    counts = Counter(all_flags)
    return {
        "board": label,
        "total_rows": len(df),
        "rows_with_issues": int((df["data_quality_flags"].apply(len) > 0).sum())
        if "data_quality_flags" in df else 0,
        "issues": dict(counts),
    }