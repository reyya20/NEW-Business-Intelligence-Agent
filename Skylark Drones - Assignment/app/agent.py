"""
Conversational BI agent.

Approach: the LLM receives (1) the founder's question + chat history, (2) a
compact set of precomputed, correctly-summed pandas aggregate tables as
markdown, and (3) a data-quality summary. It picks the relevant slice(s),
reasons over them, and answers like an analyst — flagging caveats rather than
hiding them. If the question is genuinely ambiguous (no sector/timeframe and
multiple readings are plausible), it is instructed to ask ONE clarifying
question instead of guessing.

NOTE: this uses Groq's OpenAI-compatible chat completions API
(llama-3.3-70b-versatile) rather than Anthropic or Google's APIs, as a
free-tier-friendly substitution during development. The interface
(BIAgent.answer / .leadership_summary) is unchanged from earlier versions, so
swapping the backend again later only touches this file. See DECISION_LOG.md.
"""

import os
import json
import pandas as pd
from groq import Groq

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a business intelligence analyst embedded inside a founder's \
monday.com workspace. You answer questions about sales pipeline (Deals board) and \
project execution / billing (Work Orders board) for a drone survey / geospatial \
services company (sectors: Mining, Powerline, Construction, Railways, Renewables, \
Aviation, Manufacturing, Security and Surveillance, DSP, Tender, Others).

You are given precomputed aggregate tables (already correctly summed in pandas — \
trust these numbers, do not recompute or second-guess the arithmetic) and a data \
quality summary. Ground every answer in the provided tables.

Rules:
1. Answer like a sharp analyst, not a database: lead with the insight, then the numbers.
2. ALWAYS disclose relevant data quality caveats (e.g. "14 of 62 open deals have no \
   recorded value, so this total is a floor, not the true pipeline size").
3. If the question is genuinely ambiguous (e.g. no sector or timeframe given AND \
   multiple reasonable interpretations exist), ask exactly ONE clarifying question. \
   Otherwise, make a reasonable assumption, state it in one line, and answer fully — \
   do not stall on minor ambiguity.
4. "Energy sector" commonly refers to Powerline + Renewables in this business — if \
   the user says "energy" and there's no exact "Energy" sector label, say so and use \
   that mapping.
5. "This quarter" / "this month" etc: resolve relative to the current date given below.
6. Never invent numbers not present in the provided tables. If the tables don't cover \
   the question, say what data would be needed.
7. Keep answers tight: a founder wants the headline and the caveat, not a report, \
   unless they've asked for a leadership summary.
"""


def _df_to_md(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "(no data)"
    return df.head(max_rows).to_markdown(index=False)


def build_context(aggregates: dict, dq_deals: dict, dq_wo: dict, today: str) -> str:
    parts = [f"CURRENT DATE: {today}\n"]
    parts.append("=== OPEN PIPELINE BY SECTOR ===\n" + _df_to_md(aggregates["open_pipeline_by_sector"]))
    parts.append("=== DEALS BY SECTOR & STAGE ===\n" + _df_to_md(aggregates["deals_by_sector_stage"], 60))
    parts.append("=== WIN RATE BY SECTOR (closed deals) ===\n" + _df_to_md(aggregates["win_rate_by_sector"]))
    parts.append("=== DEALS EXPECTED TO CLOSE IN NEXT 90 DAYS ===\n" + _df_to_md(aggregates["upcoming_close_90d"]))
    parts.append("=== WORK ORDER FINANCIALS BY SECTOR ===\n" + _df_to_md(aggregates["wo_financials_by_sector"]))
    parts.append("=== EXECUTION STATUS BREAKDOWN ===\n" + _df_to_md(aggregates["execution_status_breakdown"]))
    parts.append("=== AT-RISK WORK ORDERS ===\n" + _df_to_md(aggregates["at_risk_work_orders"]))
    parts.append("=== DATA QUALITY SUMMARY — DEALS BOARD ===\n" + json.dumps(dq_deals, indent=2))
    parts.append("=== DATA QUALITY SUMMARY — WORK ORDERS BOARD ===\n" + json.dumps(dq_wo, indent=2))
    return "\n\n".join(parts)


FRIENDLY_ERROR = (
    "Groq API unavailable.\n\n"
    "Check:\n"
    "• API key\n"
    "• Internet\n"
    "• Free quota"
)


class BIAgent:
    def __init__(self, api_key: str | None = None):
        resolved_key = api_key or os.environ.get("GROQ_API_KEY")
        self.client = Groq(api_key=resolved_key)

    def answer(self, history: list[dict], context: str) -> str:
        """history: list of {"role": "user"/"assistant", "content": str}"""
        messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
        for msg in history[-12:]:  # keep recent context, avoid unbounded growth
            messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception:
            return FRIENDLY_ERROR

    def leadership_summary(self, context: str) -> str:
        prompt = (
            "Prepare a leadership update summarizing: (1) overall pipeline health and "
            "value by sector, (2) win rates where known, (3) deals likely to close soon, "
            "(4) work order execution health and any at-risk/stalled projects, "
            "(5) billing/collection health (receivables outstanding), and (6) a short "
            "'data caveats' section listing what's missing or unreliable in the current "
            "data. Format as clean markdown with headers, suitable for pasting into a "
            "leadership deck or memo. Be concise — this is a briefing, not an essay."
        )
        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception:
            return FRIENDLY_ERROR