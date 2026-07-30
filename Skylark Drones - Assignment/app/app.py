import os
import datetime
import streamlit as st
import pandas as pd

from monday_client import MondayClient, MondayAPIError
from normalize import clean_deals, clean_work_orders, data_quality_summary
import aggregates as agg
from agent import BIAgent, build_context

st.set_page_config(page_title="Founder BI Agent", page_icon="📊", layout="wide")

st.title("📊 Founder BI Agent")
st.caption("Ask business questions across your Deals and Work Orders boards in monday.com")

# ---------------------------------------------------------------------------
# Config — read from environment (set these in Streamlit Cloud "Secrets")
# ---------------------------------------------------------------------------
MONDAY_TOKEN = os.environ.get("MONDAY_API_TOKEN", "")
DEALS_BOARD_ID = os.environ.get("MONDAY_DEALS_BOARD_ID", "")
WO_BOARD_ID = os.environ.get("MONDAY_WORK_ORDERS_BOARD_ID", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

missing = [
    name for name, val in [
        ("MONDAY_API_TOKEN", MONDAY_TOKEN),
        ("MONDAY_DEALS_BOARD_ID", DEALS_BOARD_ID),
        ("MONDAY_WORK_ORDERS_BOARD_ID", WO_BOARD_ID),
        ("GROQ_API_KEY", GROQ_KEY),
    ] if not val
]
if missing:
    st.error(
        "Missing configuration: " + ", ".join(missing) +
        ". Set these as environment variables / Streamlit secrets before using the app."
    )
    st.stop()


@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    client = MondayClient(MONDAY_TOKEN)
    deals_raw = client.fetch_board_items(DEALS_BOARD_ID)
    wo_raw = client.fetch_board_items(WO_BOARD_ID)
    deals = clean_deals(deals_raw)
    wo = clean_work_orders(wo_raw)
    return deals, wo


with st.spinner("Fetching latest data from monday.com..."):
    try:
        deals_df, wo_df = load_data()
    except MondayAPIError as e:
        st.error(f"Could not reach monday.com: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Unexpected error loading data: {e}")
        st.stop()

dq_deals = data_quality_summary(deals_df, "Deals")
dq_wo = data_quality_summary(wo_df, "Work Orders")
aggregates = agg.build_context_bundle(deals_df, wo_df)
today = datetime.date.today().isoformat()
context = build_context(aggregates, dq_deals, dq_wo, today)

# ---------------------------------------------------------------------------
# Sidebar: data health + refresh + leadership summary
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Data health")
    st.metric("Deals loaded", dq_deals["total_rows"], help=f"{dq_deals.get('rows_with_issues',0)} rows flagged")
    st.metric("Work orders loaded", dq_wo["total_rows"], help=f"{dq_wo.get('rows_with_issues',0)} rows flagged")
    if dq_deals["issues"] or dq_wo["issues"]:
        with st.expander("Data quality issues"):
            st.json({"deals": dq_deals["issues"], "work_orders": dq_wo["issues"]})

    if st.button("🔄 Refresh from monday.com"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.header("Leadership update")
    if st.button("📝 Generate leadership summary"):
        st.session_state["gen_summary"] = True

if "agent" not in st.session_state:
    st.session_state["agent"] = BIAgent(GROQ_KEY)
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if st.session_state.get("gen_summary"):
    st.session_state["gen_summary"] = False
    with st.spinner("Preparing leadership summary..."):
        summary = st.session_state["agent"].leadership_summary(context)
    st.subheader("Leadership Summary")
    st.markdown(summary)
    st.download_button("Download as Markdown", summary, file_name="leadership_summary.md")
    st.divider()

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("e.g. How's our pipeline looking for energy sector this quarter?"):
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                reply = st.session_state["agent"].answer(st.session_state["messages"], context)
            except Exception as e:
                reply = f"Sorry — something went wrong calling the AI backend: {e}"
        st.markdown(reply)
    st.session_state["messages"].append({"role": "assistant", "content": reply})