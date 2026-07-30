"""
Precomputed aggregate tables.

Design decision: rather than building a brittle natural-language-to-SQL/pandas
translator, we precompute a set of standard business rollups with real pandas
math (so numbers are always correct), and hand these — plus row-level data
where useful — to Claude as grounding context. Claude's job is to pick the
relevant slice, reason over it, and write the founder-facing narrative with
caveats. This is far more robust within a short build window than a custom
query-DSL, at the cost of being less "open ended" for extremely novel numeric
questions (see DECISION_LOG.md for the trade-off discussion).
"""

from __future__ import annotations
import pandas as pd
from normalize import join_deal_name


def deals_by_sector_stage(deals: pd.DataFrame) -> pd.DataFrame:
    if deals.empty:
        return deals
    return (
        deals.groupby(["sector_canonical", "Deal Stage"], dropna=False)
        .agg(count=("Deal Name", "count"), total_value=("deal_value_num", "sum"))
        .reset_index()
        .sort_values(["sector_canonical", "total_value"], ascending=[True, False])
    )


def open_pipeline_by_sector(deals: pd.DataFrame) -> pd.DataFrame:
    if deals.empty:
        return deals
    open_deals = deals[deals["Deal Status"] == "Open"]
    return (
        open_deals.groupby("sector_canonical", dropna=False)
        .agg(
            open_deal_count=("Deal Name", "count"),
            open_pipeline_value=("deal_value_num", "sum"),
            missing_value_count=("deal_value_num", lambda s: s.isna().sum()),
        )
        .reset_index()
        .sort_values("open_pipeline_value", ascending=False)
    )


def win_rate_by_sector(deals: pd.DataFrame) -> pd.DataFrame:
    if deals.empty:
        return deals
    closed = deals[deals["Deal Status"].isin(["Won", "Dead"])]
    if closed.empty:
        return pd.DataFrame()
    grp = closed.groupby("sector_canonical")["Deal Status"]
    won = grp.apply(lambda s: (s == "Won").sum())
    total = grp.count()
    out = pd.DataFrame({"won": won, "closed_total": total})
    out["win_rate_pct"] = (out["won"] / out["closed_total"] * 100).round(1)
    return out.reset_index().sort_values("win_rate_pct", ascending=False)


def upcoming_close_deals(deals: pd.DataFrame, days: int = 90) -> pd.DataFrame:
    if deals.empty or "Tentative Close Date_parsed" not in deals.columns:
        return pd.DataFrame()
    now = pd.Timestamp.now()
    horizon = now + pd.Timedelta(days=days)
    mask = (
        (deals["Deal Status"] == "Open")
        & deals["Tentative Close Date_parsed"].between(now, horizon)
    )
    cols = [c for c in ["Deal Name", "sector_canonical", "Deal Stage",
                         "deal_value_num", "Tentative Close Date_parsed"] if c in deals.columns]
    return deals.loc[mask, cols].sort_values("Tentative Close Date_parsed")


def work_order_financials_by_sector(wo: pd.DataFrame) -> pd.DataFrame:
    if wo.empty:
        return wo
    value_col = "Amount in Rupees (Incl of GST) (Masked)_num"
    billed_col = "Billed Value in Rupees (Incl of GST.) (Masked)_num"
    collected_col = "Collected Amount in Rupees (Incl of GST.) (Masked)_num"
    receivable_col = "Amount Receivable (Masked)_num"
    agg_map = {}
    for c, label in [(value_col, "total_contract_value"), (billed_col, "total_billed"),
                      (collected_col, "total_collected"), (receivable_col, "total_receivable")]:
        if c in wo.columns:
            agg_map[label] = (c, "sum")
    if not agg_map:
        return pd.DataFrame()
    return (
        wo.groupby("sector_canonical", dropna=False)
        .agg(count=("Serial #", "count"), **agg_map)
        .reset_index()
        .sort_values("total_contract_value", ascending=False)
    )


def execution_status_breakdown(wo: pd.DataFrame) -> pd.DataFrame:
    if wo.empty or "Execution Status" not in wo.columns:
        return pd.DataFrame()
    return wo["Execution Status"].value_counts(dropna=False).reset_index(
        name="count"
    ).rename(columns={"index": "Execution Status"})


def at_risk_work_orders(wo: pd.DataFrame) -> pd.DataFrame:
    """Work orders that are stalled, paused, or completed-but-uncollected."""
    if wo.empty or "Execution Status" not in wo.columns:
        return pd.DataFrame()
    risky_statuses = ["Pause / struck", "Details pending from Client"]
    mask = wo["Execution Status"].isin(risky_statuses)
    if "data_quality_flags" in wo.columns:
        mask = mask | wo["data_quality_flags"].apply(lambda f: "completed_but_uncollected" in f)
    cols = [c for c in ["Deal name masked", "Customer Name Code", "sector_canonical",
                         "Execution Status", "Amount Receivable (Masked)_num"] if c in wo.columns]
    return wo.loc[mask, cols]


def cross_board_join(deals: pd.DataFrame, wo: pd.DataFrame) -> pd.DataFrame:
    """Join deals to their work orders via normalized deal name. Not every
    deal has a matching work order (pre-execution stage) and vice versa —
    this is expected, not a data error."""
    if deals.empty or wo.empty:
        return pd.DataFrame()
    d = deals.copy()
    w = wo.copy()
    d["_join_key"] = d["Deal Name"].apply(join_deal_name)
    w["_join_key"] = w["Deal name masked"].apply(join_deal_name)
    merged = d.merge(w, on="_join_key", how="inner", suffixes=("_deal", "_wo"))
    return merged


def build_context_bundle(deals: pd.DataFrame, wo: pd.DataFrame) -> dict:
    """Everything the agent needs to answer most questions, precomputed."""
    return {
        "open_pipeline_by_sector": open_pipeline_by_sector(deals),
        "deals_by_sector_stage": deals_by_sector_stage(deals),
        "win_rate_by_sector": win_rate_by_sector(deals),
        "upcoming_close_90d": upcoming_close_deals(deals, 90),
        "wo_financials_by_sector": work_order_financials_by_sector(wo),
        "execution_status_breakdown": execution_status_breakdown(wo),
        "at_risk_work_orders": at_risk_work_orders(wo),
    }