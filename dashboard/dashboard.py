import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import time
import threading
from queue import Queue

SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
STREAM_URL = f"http://{SERVER_IP}:8000/stream"
MAX_BUFFER_SIZE = 10000

st.set_page_config(page_title="PUB Realtime Dashboard", layout="wide")
st.title("🔴 Real-Time PUB Demand Dashboard")

# ==================== SESSION STATE ====================
if "data_buffer" not in st.session_state:
    st.session_state.data_buffer = []

if "last_render_time" not in st.session_state:
    st.session_state.last_render_time = datetime.now()

if "sse_thread" not in st.session_state:
    st.session_state.sse_thread = None

if "data_queue" not in st.session_state:
    st.session_state.data_queue = Queue(maxsize=MAX_BUFFER_SIZE)

# ==================== PLACEHOLDERS ====================
plot_placeholder = st.empty()
st.divider()
metrics_placeholder = st.empty()
alerts_placeholder = st.empty()
controls_placeholder = st.empty()
table_placeholder = st.empty()

# ==================== VIEW ====================
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

# ==================== FUNCTIONS ====================
def process_dataframe(df):
    if df.empty:
        return df

    # Normalize column names
    df.columns = df.columns.str.strip()

    # Handle column name mismatches
    df = df.rename(columns={
        "Ontario_Demand": "Ontario Demand",
        "ontario demand": "Ontario Demand"
    })

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    if "Hour" in df.columns:
        df["Hour"] = pd.to_numeric(df["Hour"], errors="coerce")

    if "Ontario Demand" in df.columns:
        df["Ontario Demand"] = pd.to_numeric(df["Ontario Demand"], errors="coerce")

    df = df.dropna(subset=["Date", "Hour", "Ontario Demand"])
    df = df[(df["Hour"] >= 0) & (df["Hour"] <= 23)]

    # Sort for proper plotting
    df = df.sort_values(["Date", "Hour"])

    return df


def calculate_anomalies(df):
    if len(df) < 3:
        df["Anomaly"] = False
        return df

    df["Rolling_Avg"] = df["Ontario Demand"].rolling(
        3, center=True, min_periods=1
    ).mean()

    rolling_std = df["Ontario Demand"].std()

    if rolling_std > 0:
        df["Anomaly"] = abs(df["Ontario Demand"] - df["Rolling_Avg"]) > rolling_std * 2
    else:
        df["Anomaly"] = False

    return df


def sse_background_worker(data_queue):
    while True:
        try:
            with requests.get(STREAM_URL, stream=True, timeout=(5, 30)) as r:
                r.raise_for_status()

                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        payload = line.replace("data:", "").strip()

                        try:
                            record = json.loads(payload)
                            data_queue.put_nowait(record)
                        except json.JSONDecodeError:
                            pass

        except requests.exceptions.RequestException:
            time.sleep(2)


def render_metrics(df):
    col1, col2, col3, col4 = st.columns(4)

    peak = df["Ontario Demand"].max()
    avg = df["Ontario Demand"].mean()
    latest_hour = df["Hour"].max()

    col1.metric("Peak Demand", f"{peak:.0f} MW" if pd.notna(peak) else "N/A")
    col2.metric("Avg Demand", f"{avg:.0f} MW" if pd.notna(avg) else "N/A")
    col3.metric("Total Records", f"{len(df)}")
    col4.metric("Latest Hour", f"{int(latest_hour)}" if pd.notna(latest_hour) else "N/A")


def render_chart(df, view_mode):
    if view_mode == "Today":
        latest_date = df["Date"].max()
        df_today = df[df["Date"] == latest_date]

        if df_today.empty:
            plot_placeholder.warning("No data for today yet")
            return

        fig = px.line(
            df_today,
            x="Hour",
            y="Ontario Demand",
            title=f"Ontario Demand — {latest_date.date()}",
            markers=True,
        )
        plot_placeholder.plotly_chart(fig, use_container_width=True)

    elif view_mode == "All Dates":
        fig = px.line(
            df,
            x="Hour",
            y="Ontario Demand",
            color=df["Date"].dt.date.astype(str),
            title="All Dates",
            markers=True,
        )
        plot_placeholder.plotly_chart(fig, use_container_width=True)

    elif view_mode == "Average":
        df_avg = df.groupby("Hour")["Ontario Demand"].mean().reset_index()

        fig = px.line(
            df_avg,
            x="Hour",
            y="Ontario Demand",
            title="Average Demand",
            markers=True,
        )
        plot_placeholder.plotly_chart(fig, use_container_width=True)


# ==================== START SSE THREAD ====================
if st.session_state.sse_thread is None or not st.session_state.sse_thread.is_alive():
    st.session_state.sse_thread = threading.Thread(
        target=sse_background_worker,
        args=(st.session_state.data_queue,),
        daemon=True,
    )
    st.session_state.sse_thread.start()

# ==================== MAIN LOOP ====================
try:
    # Move queue → buffer
    while not st.session_state.data_queue.empty():
        record = st.session_state.data_queue.get_nowait()
        st.session_state.data_buffer.append(record)

        # Limit memory
        if len(st.session_state.data_buffer) > MAX_BUFFER_SIZE:
            st.session_state.data_buffer = st.session_state.data_buffer[-MAX_BUFFER_SIZE:]

    if st.session_state.data_buffer:
        df = pd.DataFrame(st.session_state.data_buffer)

        # DEBUG (remove later if you want)
        #st.write("📦 Incoming data:", st.session_state.data_buffer[-3:])

        df = process_dataframe(df)

        if not df.empty:
            df = calculate_anomalies(df)

            render_metrics(df)

            anomaly_count = int(df["Anomaly"].sum())
            if anomaly_count > 0:
                st.warning(f"⚠️ {anomaly_count} anomalies detected")
            else:
                st.success("✅ No anomalies")

            render_chart(df, view)

            st.dataframe(df.tail(10), use_container_width=True)

    else:
        plot_placeholder.info("⏳ Waiting for data...")

except Exception as e:
    st.error(f"❌ Dashboard Error: {e}")

# ==================== AUTO REFRESH ====================
time.sleep(1)
st.rerun()