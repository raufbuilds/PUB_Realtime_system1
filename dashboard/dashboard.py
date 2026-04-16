import json
import os
import threading
import time
from queue import Empty, Full, Queue

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
BASE_URL = f"http://{SERVER_IP}:8000"
STREAM_URL = f"{BASE_URL}/stream"
RECORDS_URL = f"{BASE_URL}/records"
MAX_BUFFER_SIZE = 20000


st.set_page_config(
    page_title="PUB Real-Time Demand Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("PUB Real-Time Demand Dashboard")
st.caption(f"Connected to {BASE_URL}")


def ensure_state():
    if "records" not in st.session_state:
        st.session_state.records = []
    if "record_ids" not in st.session_state:
        st.session_state.record_ids = set()
    if "data_queue" not in st.session_state:
        st.session_state.data_queue = Queue(maxsize=MAX_BUFFER_SIZE)
    if "stream_thread" not in st.session_state:
        st.session_state.stream_thread = None
    if "history_loaded" not in st.session_state:
        st.session_state.history_loaded = False
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "selected_anomaly_id" not in st.session_state:
        st.session_state.selected_anomaly_id = None


def normalize_record(raw):
    if not isinstance(raw, dict):
        return None

    record_id = raw.get("id")
    date_value = raw.get("Date", raw.get("date"))
    hour_value = raw.get("Hour", raw.get("hour"))
    demand_value = raw.get("Ontario Demand", raw.get("demand"))

    if date_value is None or hour_value is None or demand_value is None:
        return None

    date_value = pd.to_datetime(date_value, errors="coerce")
    hour_value = pd.to_numeric(hour_value, errors="coerce")
    demand_value = pd.to_numeric(demand_value, errors="coerce")

    if pd.isna(date_value) or pd.isna(hour_value) or pd.isna(demand_value):
        return None

    hour_value = int(hour_value)
    if hour_value < 0 or hour_value > 23:
        return None

    if record_id is None:
        record_id = f"{date_value.date()}-{hour_value}-{float(demand_value)}"

    return {
        "id": record_id,
        "Date": date_value.normalize(),
        "Hour": hour_value,
        "Ontario Demand": float(demand_value),
    }


def add_record(raw_record):
    record = normalize_record(raw_record)
    if record is None:
        return False

    record_id = record["id"]
    if record_id in st.session_state.record_ids:
        return False

    st.session_state.records.append(record)
    st.session_state.record_ids.add(record_id)

    overflow = len(st.session_state.records) - MAX_BUFFER_SIZE
    if overflow > 0:
        removed = st.session_state.records[:overflow]
        st.session_state.records = st.session_state.records[overflow:]
        for item in removed:
            st.session_state.record_ids.discard(item["id"])

    return True


def load_history():
    try:
        response = requests.get(RECORDS_URL, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        st.session_state.last_error = f"History load failed: {exc}"
        return

    loaded = 0
    if isinstance(payload, list):
        for raw in payload:
            if add_record(raw):
                loaded += 1

    st.session_state.history_loaded = True
    if loaded:
        st.session_state.last_error = None


def enqueue_latest(data_queue, record):
    try:
        data_queue.put_nowait(record)
    except Full:
        try:
            data_queue.get_nowait()
        except Empty:
            pass
        try:
            data_queue.put_nowait(record)
        except Full:
            pass


def stream_worker(data_queue):
    backoff = 2

    while True:
        try:
            with requests.get(STREAM_URL, stream=True, timeout=(5, 30)) as response:
                response.raise_for_status()
                backoff = 2

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        payload = line.replace("data:", "", 1).strip()
                        try:
                            record = json.loads(payload)
                            enqueue_latest(data_queue, record)
                        except json.JSONDecodeError:
                            continue

        except requests.RequestException as exc:
            st.session_state.last_error = f"Stream error: {exc}"
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


def drain_queue():
    changed = False
    while True:
        try:
            raw = st.session_state.data_queue.get_nowait()
        except Empty:
            break
        if add_record(raw):
            changed = True
    return changed


def dataframe_from_state():
    if not st.session_state.records:
        return pd.DataFrame(columns=["id", "Date", "Hour", "Ontario Demand"])

    df = pd.DataFrame(st.session_state.records).copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Hour"] = pd.to_numeric(df["Hour"], errors="coerce")
    df["Ontario Demand"] = pd.to_numeric(df["Ontario Demand"], errors="coerce")
    df = df.dropna(subset=["Date", "Hour", "Ontario Demand"])
    df["Hour"] = df["Hour"].astype(int)
    df = df.sort_values(["Date", "Hour", "id"]).reset_index(drop=True)
    df["Timestamp"] = df["Date"] + pd.to_timedelta(df["Hour"], unit="h")
    df["Date Label"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def calculate_anomalies(df):
    if df.empty:
        return df

    df = df.copy()
    hour_median = df.groupby("Hour")["Ontario Demand"].transform("median")
    hour_mad = df.groupby("Hour")["Ontario Demand"].transform(
        lambda series: (series - series.median()).abs().median()
    )

    global_mad = (df["Ontario Demand"] - df["Ontario Demand"].median()).abs().median()
    global_std = df["Ontario Demand"].std()
    fallback_scale = max(
        [value for value in [global_mad * 1.4826, global_std] if pd.notna(value) and value > 0]
        or [1.0]
    )

    scale = hour_mad.fillna(fallback_scale) * 1.4826
    scale = scale.replace(0, fallback_scale)

    df["Expected Demand"] = hour_median
    df["Deviation"] = df["Ontario Demand"] - df["Expected Demand"]
    df["Anomaly Score"] = (df["Deviation"].abs() / scale).fillna(0)
    df["Anomaly"] = df["Anomaly Score"] >= 3
    df["Status"] = df["Anomaly"].map(lambda value: "Anomaly detected" if value else "System normal")
    return df


def sidebar_controls(df):
    st.sidebar.header("Controls")
    refresh_seconds = st.sidebar.slider("Dashboard refresh interval (seconds)", 1, 10, 2)
    st.sidebar.caption(f"History buffer: {len(st.session_state.records)} records")
    st.sidebar.caption(
        f"Connection: {'Streaming' if st.session_state.stream_thread and st.session_state.stream_thread.is_alive() else 'Starting'}"
    )

    if st.session_state.last_error:
        st.sidebar.warning(st.session_state.last_error)

    if not df.empty:
        latest_date = df["Date"].max().date()
        earliest_date = df["Date"].min().date()
        st.sidebar.caption(f"Date range: {earliest_date} to {latest_date}")

    view = st.sidebar.selectbox(
        "View Mode",
        [
            "Today",
            "All Dates",
            "Average",
            "Today vs Average",
            "Latest 7 Days",
            "Latest Records",
        ],
    )

    return view, refresh_seconds


def render_metrics(df):
    peak = df["Ontario Demand"].max()
    avg = df["Ontario Demand"].mean()
    latest_hour = df["Hour"].max()
    latest_date = df["Date"].max()

    cols = st.columns(4)
    cols[0].metric("Peak Demand", f"{peak:.0f} MW" if pd.notna(peak) else "N/A")
    cols[1].metric("Avg Demand", f"{avg:.0f} MW" if pd.notna(avg) else "N/A")
    cols[2].metric("Total Records", f"{len(df)}")
    cols[3].metric("Latest Hour", f"{int(latest_hour)}" if pd.notna(latest_hour) else "N/A")

    if df["Anomaly"].any():
        st.warning(f"{int(df['Anomaly'].sum())} anomalies detected")
    else:
        st.success("System normal")


def render_today(df):
    latest_date = df["Date"].max()
    df_today = df[df["Date"] == latest_date]

    if df_today.empty:
        st.info("No data for the latest date yet")
        return

    fig = px.line(
        df_today,
        x="Hour",
        y="Ontario Demand",
        title=f"Ontario Demand - {latest_date.date()}",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_all_dates(df):
    fig = px.line(
        df,
        x="Hour",
        y="Ontario Demand",
        color="Date Label",
        title="All Dates",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_average(df):
    df_avg = df.groupby("Hour", as_index=False)["Ontario Demand"].mean()
    fig = px.line(df_avg, x="Hour", y="Ontario Demand", title="Average Demand", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def render_today_vs_average(df):
    latest_date = df["Date"].max()
    today_df = df[df["Date"] == latest_date].groupby("Hour", as_index=False)["Ontario Demand"].mean()
    avg_df = df.groupby("Hour", as_index=False)["Ontario Demand"].mean()
    today_df = today_df.rename(columns={"Ontario Demand": "Today"})
    avg_df = avg_df.rename(columns={"Ontario Demand": "Average"})
    merged = pd.merge(today_df, avg_df, on="Hour", how="outer").sort_values("Hour")
    melted = merged.melt(id_vars="Hour", value_vars=["Today", "Average"], var_name="Series", value_name="Demand")
    fig = px.line(melted, x="Hour", y="Demand", color="Series", title=f"Today vs Average - {latest_date.date()}", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def render_latest_7_days(df):
    dates = sorted(df["Date"].dt.normalize().dropna().unique())[-7:]
    recent_df = df[df["Date"].isin(dates)]
    if recent_df.empty:
        st.info("Not enough recent data yet")
        return
    fig = px.line(recent_df, x="Hour", y="Ontario Demand", color="Date Label", title="Latest 7 Dates", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def render_latest_records(df):
    recent = df.tail(50).copy()
    if recent.empty:
        st.info("No recent records available")
        return
    recent["Label"] = recent["Timestamp"].dt.strftime("%Y-%m-%d %H:00")
    fig = px.bar(
        recent,
        x="Label",
        y="Ontario Demand",
        color="Status",
        title="Latest Records",
        hover_data=["Hour", "Deviation", "Anomaly Score"],
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)


def render_anomaly_details(df):
    anomaly_df = df[df["Anomaly"]].copy()
    st.subheader("Anomaly Details")

    if anomaly_df.empty:
        st.success("System normal - no anomaly markers were detected")
        return

    anomaly_df["Label"] = anomaly_df["Timestamp"].dt.strftime("%Y-%m-%d %H:00")
    st.dataframe(
        anomaly_df[
            [
                "Label",
                "Hour",
                "Ontario Demand",
                "Expected Demand",
                "Deviation",
                "Anomaly Score",
                "Status",
            ]
        ],
        use_container_width=True,
    )


def render_chart(df, view_mode):
    if view_mode == "Today":
        render_today(df)
    elif view_mode == "All Dates":
        render_all_dates(df)
    elif view_mode == "Average":
        render_average(df)
    elif view_mode == "Today vs Average":
        render_today_vs_average(df)
    elif view_mode == "Latest 7 Days":
        render_latest_7_days(df)
    elif view_mode == "Latest Records":
        render_latest_records(df)


ensure_state()

if not st.session_state.history_loaded:
    load_history()

if st.session_state.stream_thread is None or not st.session_state.stream_thread.is_alive():
    st.session_state.stream_thread = threading.Thread(
        target=stream_worker,
        args=(st.session_state.data_queue,),
        daemon=True,
    )
    st.session_state.stream_thread.start()

queue_changed = drain_queue()
df = dataframe_from_state()
if not df.empty:
    df = calculate_anomalies(df)

view, refresh_seconds = sidebar_controls(df)

if queue_changed:
    st.session_state.last_error = None

if df.empty:
    st.info("Waiting for data from the server...")
else:
    render_metrics(df)
    render_chart(df, view)
    render_anomaly_details(df)
    st.subheader("Latest Records")
    st.dataframe(
        df[
            [
                "Date",
                "Hour",
                "Ontario Demand",
                "Expected Demand",
                "Deviation",
                "Anomaly Score",
                "Status",
            ]
        ].tail(25),
        use_container_width=True,
    )

time.sleep(refresh_seconds)
st.rerun()
