import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import os


SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
STREAM_URL = f"http://{SERVER_IP}:8000/stream"

#  STREAMLIT SETUP
st.set_page_config(page_title="PUB Realtime Dashboard", layout="wide")
st.title("🔴 Real-Time PUB Demand Dashboard")

plot_placeholder = st.empty()
table_placeholder = st.empty()

data_buffer = []

view = st.sidebar.selectbox(
    "📊 View Mode",
    [
        "Today",
        "All Dates",
        "Average",
        "Today vs Average",
        "Latest 7 Days",
        "Latest Records",
    ],
)

# SSE READER
def sse_events(url):
    with requests.get(url, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data:"):
                    yield decoded.replace("data:", "").strip()

# MAIN LOOP
for payload in sse_events(STREAM_URL):

    record = json.loads(payload)
    data_buffer.append(record)

    df = pd.DataFrame(data_buffer)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    if "Hour" in df.columns:
        df["Hour"] = pd.to_numeric(df["Hour"], errors="coerce")

        # -------------------------------
        #  VIEW 1 — TODAY ONLY
        # -------------------------------
        if view == "Today":
            latest_date = df["Date"].max()
            df_today = df[df["Date"] == latest_date]

            fig = px.line(
                df_today,
                x="Hour",
                y="Ontario Demand",
                title=f"Ontario Demand — {latest_date.date()}",
            )
            plot_placeholder.plotly_chart(fig, use_container_width=True)
            table_placeholder.dataframe(df_today.tail(10))

        # -------------------------------
        # VIEW 2 — ALL DATES (multi-line)
        # -------------------------------
        elif view == "All Dates":
            fig = px.line(
                df,
                x="Hour",
                y="Ontario Demand",
                color=df["Date"].dt.date.astype(str),
                title="Ontario Demand by Hour — All Dates",
            )
            plot_placeholder.plotly_chart(fig, use_container_width=True)
            table_placeholder.dataframe(df.tail(10))

        # -------------------------------
        # VIEW 3 — AVERAGE PROFILE
        # -------------------------------
        elif view == "Average":
            df_avg = df.groupby("Hour")["Ontario Demand"].mean().reset_index()

            fig = px.line(
                df_avg,
                x="Hour",
                y="Ontario Demand",
                title="Average Ontario Demand by Hour",
            )
            plot_placeholder.plotly_chart(fig, use_container_width=True)
            table_placeholder.dataframe(df_avg)

        # -------------------------------
        # VIEW 4 — LATEST 7 DAYS
        # -------------------------------
        elif view == "Latest 7 Days":
            latest_date = df["Date"].max()
            cutoff = latest_date - pd.Timedelta(days=7)
            df_7 = df[df["Date"] >= cutoff]

            fig = px.line(
                df_7,
                x="Hour",
                y="Ontario Demand",
                color=df_7["Date"].dt.date.astype(str),
                title="Ontario Demand — Last 7 Days",
            )
            plot_placeholder.plotly_chart(fig, use_container_width=True)
            table_placeholder.dataframe(df_7.tail(20))

        # -------------------------------
        # VIEW 5 — TODAY vs AVERAGE
        # -------------------------------
        elif view == "Today vs Average":
            latest_date = df["Date"].max()
            df_today = df[df["Date"] == latest_date]
            df_avg = df.groupby("Hour")["Ontario Demand"].mean().reset_index()

            fig = px.line(
                df_today,
                x="Hour",
                y="Ontario Demand",
                title=f"Ontario Demand — Today ({latest_date.date()}) vs Average",
            )
            fig.add_scatter(
                x=df_avg["Hour"],
                y=df_avg["Ontario Demand"],
                mode="lines",
                name="Average",
            )

            plot_placeholder.plotly_chart(fig, use_container_width=True)
            table_placeholder.dataframe(df_today.tail(10))

        # -------------------------------
        # VIEW 6 — LATEST RECORDS TABLE
        # -------------------------------
        elif view == "Latest Records":
            plot_placeholder.empty()  # no plot here
            table_placeholder.dataframe(df.tail(25))
