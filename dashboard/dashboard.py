import json
import os
import threading
import time
from queue import Empty, Full, Queue
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
BASE_URL = f"http://{SERVER_IP}:8000"
STREAM_URL = f"{BASE_URL}/stream"
RECORDS_URL = f"{BASE_URL}/records"
MAX_BUFFER_SIZE = 20000
FORECAST_REFRESH_SECONDS = int(os.getenv("FORECAST_REFRESH_SECONDS", "300"))


st.set_page_config(
    page_title="Real-Time Electricity Demand Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Real-Time Electricity Demand Dashboard")
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
    if "last_received_epoch" not in st.session_state:
        st.session_state.last_received_epoch = None
    if "last_received_record" not in st.session_state:
        st.session_state.last_received_record = None
    if "refresh_seconds" not in st.session_state:
        st.session_state.refresh_seconds = 2
    if "auto_refresh_enabled" not in st.session_state:
        st.session_state.auto_refresh_enabled = True
    if "scope" not in st.session_state:
        st.session_state.scope = "Today"
    if "date_range" not in st.session_state:
        st.session_state.date_range = None
    if "hour_range" not in st.session_state:
        st.session_state.hour_range = (0, 23)
    if "show_normal_rows" not in st.session_state:
        st.session_state.show_normal_rows = False
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "Today"
    elif st.session_state.view_mode == "Today vs Average":
        st.session_state.view_mode = "Today vs Forecast Benchmarks"
    elif st.session_state.view_mode in {
        "Today vs Forecast Benchmarks",
        "Today vs Live-Trained Forecast",
    }:
        st.session_state.view_mode = "Forecast Training Comparison"
    # Forecast model caching
    if "prophet_model" not in st.session_state:
        st.session_state.prophet_model = None
    if "xgboost_model" not in st.session_state:
        st.session_state.xgboost_model = None
    if "forecast_cache_time" not in st.session_state:
        st.session_state.forecast_cache_time = 0
    if "forecast_cache_data_hash" not in st.session_state:
        st.session_state.forecast_cache_data_hash = None
    if "forecast_cache_result" not in st.session_state:
        st.session_state.forecast_cache_result = None
    if "forecast_cache_target_date" not in st.session_state:
        st.session_state.forecast_cache_target_date = None
    if "forecast_cache_include_today" not in st.session_state:
        st.session_state.forecast_cache_include_today = None
    if "forecast_cache_results" not in st.session_state:
        st.session_state.forecast_cache_results = {}


def coerce_date_range_value(value):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            start = pd.to_datetime(value[0]).date()
            end = pd.to_datetime(value[1]).date()
        elif len(value) == 1:
            start = end = pd.to_datetime(value[0]).date()
        else:
            return None
    elif value is not None:
        start = end = pd.to_datetime(value).date()
    else:
        return None

    if start > end:
        start, end = end, start
    return (start, end)


def clamp_date_range(date_range, min_date, max_date):
    normalized = coerce_date_range_value(date_range)
    if normalized is None:
        return (min_date, max_date)

    start, end = normalized
    if start < min_date:
        start = min_date
    if end > max_date:
        end = max_date
    if start > end:
        start, end = min_date, max_date
    return (start, end)


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
            st.session_state.last_received_epoch = time.time()
            st.session_state.last_received_record = raw
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


def compute_hourly_baseline(df, threshold=3.0):
    if df.empty:
        return pd.DataFrame(columns=["Hour", "Expected", "Scale", "Lower", "Upper"])

    expected = df.groupby("Hour")["Ontario Demand"].median()

    def mad(series: pd.Series) -> float:
        med = series.median()
        return float((series - med).abs().median())

    hour_mad = df.groupby("Hour")["Ontario Demand"].apply(mad)

    global_mad = float((df["Ontario Demand"] - df["Ontario Demand"].median()).abs().median())
    global_std = float(df["Ontario Demand"].std()) if pd.notna(df["Ontario Demand"].std()) else 0.0
    fallback_scale = max([v for v in [global_mad * 1.4826, global_std] if v and v > 0] or [1.0])

    scale = (hour_mad * 1.4826).replace(0, fallback_scale).fillna(fallback_scale)

    baseline = pd.DataFrame(
        {
            "Hour": expected.index.astype(int),
            "Expected": expected.values.astype(float),
            "Scale": scale.reindex(expected.index).values.astype(float),
        }
    )
    baseline["Lower"] = baseline["Expected"] - threshold * baseline["Scale"]
    baseline["Upper"] = baseline["Expected"] + threshold * baseline["Scale"]
    return baseline


def forecast_training_frame(df, target_date=None, include_target_date=False):
    if df.empty:
        return df

    if target_date is None:
        target_date = df["Date"].max()

    if include_target_date:
        return df.copy()

    historical_df = df[df["Date"] < pd.Timestamp(target_date)].copy()
    if len(historical_df) >= 48:
        return historical_df

    return df.copy()


def forecast_cache_signature(df, target_date=None, include_target_date=False):
    if df.empty:
        return (0, None, None, None, include_target_date)

    if target_date is None:
        target_date = df["Date"].max()

    latest_ts = df["Timestamp"].max() if "Timestamp" in df.columns else None
    earliest_ts = df["Timestamp"].min() if "Timestamp" in df.columns else None
    return (
        len(df),
        pd.Timestamp(earliest_ts).isoformat() if pd.notna(earliest_ts) else None,
        pd.Timestamp(latest_ts).isoformat() if pd.notna(latest_ts) else None,
        pd.Timestamp(target_date).date().isoformat(),
        include_target_date,
    )


def forecast_with_prophet(df, target_date=None):
    """
    Use Prophet to forecast expected demand for each hour of a target date.
    Returns a DataFrame with Hour and Predicted columns.
    """
    if df.empty or len(df) < 24:
        return pd.DataFrame(columns=["Hour", "Prophet Predicted"])

    try:
        from prophet import Prophet

        # Prepare data for Prophet (requires 'ds' and 'y' columns)
        prophet_df = df[["Timestamp", "Ontario Demand"]].copy()
        prophet_df = prophet_df.dropna()
        prophet_df = prophet_df.rename(columns={"Timestamp": "ds", "Ontario Demand": "y"})

        if len(prophet_df) < 24:
            return pd.DataFrame(columns=["Hour", "Prophet Predicted"])

        # Fit Prophet model
        model = Prophet(
            daily_seasonality='auto',
            weekly_seasonality='auto',
            yearly_seasonality='auto',
            changepoint_prior_scale=0.05,
        )
        model.fit(prophet_df)

        # Generate forecast for target date
        if target_date is None:
            target_date = df["Date"].max()

        # Create future dataframe for 24 hours
        future_dates = []
        for hour in range(24):
            future_dates.append(pd.Timestamp(target_date).replace(hour=hour))
        future_df = pd.DataFrame({"ds": future_dates})

        # Make predictions
        forecast = model.predict(future_df)
        result = pd.DataFrame({
            "Hour": range(24),
            "Prophet Predicted": forecast["yhat"].values
        })
        return result
    except ImportError:
        return pd.DataFrame(columns=["Hour", "Prophet Predicted"])
    except Exception as e:
        st.session_state.last_error = f"Prophet forecast error: {e}"
        return pd.DataFrame(columns=["Hour", "Prophet Predicted"])


def forecast_with_xgboost(df, target_date=None):
    """
    Use XGBoost with engineered features to predict expected demand.
    Returns a DataFrame with Hour and XGBoost Predicted columns.
    """
    if df.empty or len(df) < 48:
        return pd.DataFrame(columns=["Hour", "XGBoost Predicted"])

    try:
        from xgboost import XGBRegressor

        # Feature engineering
        df_features = df.copy()
        df_features = df_features.dropna(subset=["Timestamp", "Ontario Demand"])

        if len(df_features) < 48:
            return pd.DataFrame(columns=["Hour", "XGBoost Predicted"])

        # Create time-based features
        df_features["hour"] = df_features["Timestamp"].dt.hour
        df_features["day_of_week"] = df_features["Timestamp"].dt.dayofweek
        df_features["day_of_month"] = df_features["Timestamp"].dt.day
        df_features["month"] = df_features["Timestamp"].dt.month
        df_features["is_weekend"] = (df_features["day_of_week"] >= 5).astype(int)

        # Lag features (previous hour, same hour yesterday)
        df_features = df_features.sort_values("Timestamp")
        df_features["demand_lag_1"] = df_features["Ontario Demand"].shift(1)
        df_features["demand_lag_24"] = df_features["Ontario Demand"].shift(24)

        # Rolling statistics
        df_features["rolling_mean_24"] = df_features["Ontario Demand"].rolling(24).mean()
        df_features["rolling_std_24"] = df_features["Ontario Demand"].rolling(24).std()

        # Drop rows with NaN values from lag/rolling features
        df_features = df_features.dropna()

        if len(df_features) < 24:
            return pd.DataFrame(columns=["Hour", "XGBoost Predicted"])

        # Define features
        feature_cols = ["hour", "day_of_week", "day_of_month", "month", "is_weekend",
                        "demand_lag_1", "demand_lag_24", "rolling_mean_24", "rolling_std_24"]

        X = df_features[feature_cols]
        y = df_features["Ontario Demand"]

        # Train model
        model = XGBRegressor(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X, y)

        # Predict for target date
        if target_date is None:
            target_date = df["Date"].max()

        target_ts = pd.Timestamp(target_date)
        predictions = []

        for hour in range(24):
            # Create feature vector for this hour
            features = {
                "hour": hour,
                "day_of_week": target_ts.dayofweek,
                "day_of_month": target_ts.day,
                "month": target_ts.month,
                "is_weekend": 1 if target_ts.dayofweek >= 5 else 0,
                "demand_lag_1": df_features["Ontario Demand"].iloc[-1] if len(df_features) > 0 else 0,
                "demand_lag_24": df_features[df_features["Timestamp"] < target_ts - pd.Timedelta(hours=24)]["Ontario Demand"].mean() if len(df_features) > 24 else 0,
                "rolling_mean_24": df_features["Ontario Demand"].tail(24).mean() if len(df_features) >= 24 else 0,
                "rolling_std_24": df_features["Ontario Demand"].tail(24).std() if len(df_features) >= 24 else 0,
            }
            predictions.append(features)

        pred_df = pd.DataFrame(predictions)
        pred_df = pred_df[feature_cols]
        forecasted = model.predict(pred_df)

        result = pd.DataFrame({
            "Hour": range(24),
            "XGBoost Predicted": forecasted
        })
        return result
    except ImportError:
        return pd.DataFrame(columns=["Hour", "XGBoost Predicted"])
    except Exception as e:
        st.session_state.last_error = f"XGBoost forecast error: {e}"
        return pd.DataFrame(columns=["Hour", "XGBoost Predicted"])


def compute_ensemble_forecast(df, target_date=None, include_target_date=False):
    """
    Combine Prophet and XGBoost predictions with weighted average.
    Returns DataFrame with Hour, Prophet, XGBoost, and Ensemble columns.
    """
    training_df = forecast_training_frame(df, target_date, include_target_date)
    target_date_value = pd.Timestamp(target_date or df["Date"].max()).date()
    signature = forecast_cache_signature(training_df, target_date_value, include_target_date)
    cache_key = (target_date_value.isoformat(), include_target_date)
    cached = st.session_state.forecast_cache_results.get(cache_key)

    if (
        cached is not None
        and cached["signature"] == signature
        and time.time() - cached["created_at"] < FORECAST_REFRESH_SECONDS
    ):
        return cached["result"].copy()

    prophet_forecast = forecast_with_prophet(training_df, target_date)
    xgboost_forecast = forecast_with_xgboost(training_df, target_date)

    if prophet_forecast.empty and xgboost_forecast.empty:
        return pd.DataFrame(columns=["Hour", "Prophet", "XGBoost", "Ensemble"])

    # Merge forecasts
    if prophet_forecast.empty:
        result = xgboost_forecast.rename(columns={"XGBoost Predicted": "Ensemble"})
        result["Prophet"] = result["Ensemble"]
        result["XGBoost"] = result["Ensemble"]
    elif xgboost_forecast.empty:
        result = prophet_forecast.rename(columns={"Prophet Predicted": "Ensemble"})
        result["Prophet"] = result["Ensemble"]
        result["XGBoost"] = result["Ensemble"]
    else:
        merged = pd.merge(prophet_forecast, xgboost_forecast, on="Hour", how="outer")
        # Weighted ensemble (Prophet: 0.4, XGBoost: 0.6)
        merged["Ensemble"] = 0.4 * merged["Prophet Predicted"] + 0.6 * merged["XGBoost Predicted"]
        result = merged.rename(columns={
            "Prophet Predicted": "Prophet",
            "XGBoost Predicted": "XGBoost"
        })

    result = result[["Hour", "Prophet", "XGBoost", "Ensemble"]]
    st.session_state.forecast_cache_result = result.copy()
    st.session_state.forecast_cache_data_hash = signature
    st.session_state.forecast_cache_target_date = target_date_value
    st.session_state.forecast_cache_include_today = include_target_date
    st.session_state.forecast_cache_time = time.time()
    st.session_state.forecast_cache_results[cache_key] = {
        "created_at": st.session_state.forecast_cache_time,
        "signature": signature,
        "result": result.copy(),
    }
    return result


def add_baseline_to_figure(fig, baseline, hours, title_suffix=""):
    if baseline.empty:
        return fig

    band = baseline[baseline["Hour"].isin(hours)].sort_values("Hour")
    if band.empty:
        return fig

    fig.add_trace(
        go.Scatter(
            x=band["Hour"],
            y=band["Upper"],
            mode="lines",
            line=dict(color="rgba(160,160,160,0.35)"),
            name="Expected + band",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=band["Hour"],
            y=band["Lower"],
            mode="lines",
            line=dict(color="rgba(160,160,160,0.35)"),
            fill="tonexty",
            fillcolor="rgba(160,160,160,0.15)",
            name="Expected band",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=band["Hour"],
            y=band["Expected"],
            mode="lines",
            line=dict(color="rgba(90,90,90,0.85)", dash="dot"),
            name="Expected (median)",
        )
    )

    if title_suffix:
        fig.update_layout(title=f"{fig.layout.title.text}{title_suffix}")
    return fig


def add_anomaly_markers(fig, df_with_anomaly, label_col=None):
    anomalies = df_with_anomaly[df_with_anomaly["Anomaly"]].copy()
    if anomalies.empty:
        return fig

    hover_text = None
    if label_col and label_col in anomalies.columns:
        hover_text = anomalies[label_col]

    fig.add_trace(
        go.Scatter(
            x=anomalies["Hour"],
            y=anomalies["Ontario Demand"],
            mode="markers",
            marker=dict(size=11, color="#d62728", symbol="x"),
            name="Anomaly",
            text=hover_text,
            customdata=anomalies[["Expected Demand", "Deviation", "Anomaly Score"]].to_numpy(),
            hovertemplate=(
                "Hour: %{x}<br>"
                "Demand: %{y:.1f} MW<br>"
                "Expected: %{customdata[0]:.1f} MW<br>"
                "Deviation: %{customdata[1]:.1f} MW<br>"
                "Score: %{customdata[2]:.2f}<extra></extra>"
            ),
        )
    )
    return fig


def sidebar_controls(df):
    st.sidebar.header("Controls")
    refresh_seconds = st.sidebar.slider(
        "Dashboard refresh interval (seconds)",
        1,
        10,
        key="refresh_seconds",
    )
    auto_refresh_enabled = st.sidebar.checkbox(
        "Auto refresh",
        key="auto_refresh_enabled",
    )
    if st.sidebar.button("Refresh now", key="refresh_now"):
        st.rerun()

    st.sidebar.subheader("Scope")
    scope = st.sidebar.selectbox(
        "Data scope",
        ["All data", "Today", "Last 7 days", "Custom date range"],
        key="scope",
    )

    if not df.empty:
        min_date = df["Date"].min().date()
        max_date = df["Date"].max().date()
    else:
        today = pd.Timestamp.today().date()
        min_date, max_date = today, today

    st.session_state.date_range = clamp_date_range(
        st.session_state.date_range,
        min_date,
        max_date,
    )

    date_range = st.session_state.date_range
    if scope == "Custom date range":
        date_range = st.sidebar.date_input(
            "Date range",
            value=st.session_state.date_range,
            min_value=min_date,
            max_value=max_date,
            key="date_range",
        )
        st.session_state.date_range = clamp_date_range(date_range, min_date, max_date)
        date_range = st.session_state.date_range

    st.sidebar.subheader("Filters")
    hour_range = st.sidebar.slider("Hour range", 0, 23, key="hour_range")
    show_normal_rows = st.sidebar.checkbox("Show normal rows", key="show_normal_rows")

    st.sidebar.caption(f"History buffer: {len(st.session_state.records)} records")
    st.sidebar.caption(
        f"Connection: {'Streaming' if st.session_state.stream_thread and st.session_state.stream_thread.is_alive() else 'Starting'}"
    )

    if st.session_state.last_error:
        st.sidebar.warning(st.session_state.last_error)

    if not df.empty:
        latest_date = df["Date"].max().date()
        earliest_date = df["Date"].min().date()
        st.sidebar.caption(f"Available dates: {earliest_date} to {latest_date}")

    if st.session_state.last_received_epoch is None:
        st.sidebar.caption("Last update: N/A")
    else:
        age_s = max(0.0, time.time() - st.session_state.last_received_epoch)
        st.sidebar.caption(f"Last update: {age_s:.0f}s ago")

    st.sidebar.subheader("View")
    view = st.sidebar.selectbox(
        "View Mode",
        [
            "Today",
            "All Dates",
            "Average",
            "Forecast Training Comparison",
            "Latest 7 Days",
            "Latest Records",
        ],
        key="view_mode",
    )

    return (
        view,
        refresh_seconds,
        auto_refresh_enabled,
        scope,
        date_range,
        hour_range,
        show_normal_rows,
    )


def apply_scope_and_filters(df, scope, date_range, hour_range):
    if df.empty:
        return df

    df_view = df.copy()

    if scope == "Today":
        latest_date = df_view["Date"].max()
        df_view = df_view[df_view["Date"] == latest_date]
    elif scope == "Last 7 days":
        latest_date = df_view["Date"].max()
        cutoff = latest_date - pd.Timedelta(days=6)
        df_view = df_view[df_view["Date"] >= cutoff]
    elif scope == "Custom date range":
        start = None
        end = None
        if isinstance(date_range, (list, tuple)):
            if len(date_range) >= 2:
                start, end = date_range[0], date_range[1]
            elif len(date_range) == 1:
                start = end = date_range[0]
        elif date_range is not None:
            start = end = date_range

        if start is not None and end is not None:
            start_ts = pd.to_datetime(start)
            end_ts = pd.to_datetime(end)
            if start_ts > end_ts:
                start_ts, end_ts = end_ts, start_ts
            df_view = df_view[(df_view["Date"] >= start_ts) & (df_view["Date"] <= end_ts)]

    hr0, hr1 = hour_range
    df_view = df_view[(df_view["Hour"] >= hr0) & (df_view["Hour"] <= hr1)]
    return df_view


def build_scope_label(df_view, scope, hour_range):
    hour_label = f"Hours {hour_range[0]}-{hour_range[1]}"
    if df_view.empty:
        return f"{scope} | {hour_label}"

    min_date = df_view["Date"].min().date()
    max_date = df_view["Date"].max().date()

    if scope == "Today":
        scope_label = f"Today ({max_date})"
    elif scope == "Last 7 days":
        scope_label = f"Last 7 days ({min_date} to {max_date})"
    elif scope == "Custom date range":
        scope_label = f"Custom range ({min_date} to {max_date})"
    else:
        scope_label = f"All data ({min_date} to {max_date})"

    return f"{scope_label} | {hour_label}"


def render_metrics(df):
    peak = df["Ontario Demand"].max()
    avg = df["Ontario Demand"].mean()

    cols = st.columns(3)
    cols[0].metric("Peak Demand", f"{peak:.0f} MW" if pd.notna(peak) else "N/A")
    cols[1].metric("Avg Demand", f"{avg:.0f} MW" if pd.notna(avg) else "N/A")
    cols[2].metric("Total Records", f"{len(df)}")

    if df["Anomaly"].any():
        st.warning(f"{int(df['Anomaly'].sum())} anomalies detected")
    else:
        st.success("System normal")


def render_today(df, scope_label, baseline=None):
    latest_date = df["Date"].max()
    df_today = df[df["Date"] == latest_date]

    if df_today.empty:
        st.info("No data for the latest date yet")
        return

    fig = px.line(
        df_today,
        x="Hour",
        y="Ontario Demand",
        title=f"Ontario Demand - {latest_date.date()} | {scope_label}",
        markers=True,
    )
    baseline_df = baseline if baseline is not None else pd.DataFrame()
    fig = add_baseline_to_figure(fig, baseline_df, sorted(df_today["Hour"].unique()))
    fig = add_anomaly_markers(fig, df_today)
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def render_all_dates(df, scope_label):
    fig = px.line(
        df,
        x="Hour",
        y="Ontario Demand",
        color="Date Label",
        title=f"All Dates | {scope_label}",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_average(df, scope_label):
    df_avg = df.groupby("Hour", as_index=False)["Ontario Demand"].mean()
    fig = px.line(df_avg, x="Hour", y="Ontario Demand", title=f"Average Demand | {scope_label}", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def calculate_accuracy_percentage(actual, predicted):
    comparison = pd.DataFrame({"Actual": actual, "Predicted": predicted}).dropna()
    comparison = comparison[comparison["Actual"] != 0]
    if comparison.empty:
        return None

    absolute_percentage_error = (
        (comparison["Actual"] - comparison["Predicted"]).abs() / comparison["Actual"].abs()
    )
    accuracy = 100 - (absolute_percentage_error.mean() * 100)
    return max(0.0, min(100.0, float(accuracy)))


def style_today_trace(fig):
    for trace in fig.data:
        line_width = 5 if getattr(trace, "name", None) == "Today" else 2
        marker_size = 9 if getattr(trace, "name", None) == "Today" else None
        if marker_size is None:
            trace.update(line={"width": line_width})
        else:
            trace.update(line={"width": line_width}, marker={"size": marker_size})


def render_today_vs_forecast(df, scope_label, baseline=None, include_today_in_training=False):
    latest_date = df["Date"].max()
    today_df = df[df["Date"] == latest_date].groupby("Hour", as_index=False)["Ontario Demand"].mean()
    if include_today_in_training:
        comparison_source = df
        title_prefix = "Today vs Live-Trained Forecast"
    else:
        historical_df = df[df["Date"] < latest_date].copy()
        comparison_source = historical_df if not historical_df.empty else df
        title_prefix = "Today vs Forecast Benchmarks"

    avg_df = comparison_source.groupby("Hour", as_index=False)["Ontario Demand"].mean()
    today_df = today_df.rename(columns={"Ontario Demand": "Today"})
    avg_df = avg_df.rename(columns={"Ontario Demand": "Average"})

    # Get Prophet, XGBoost, and Ensemble forecasts
    forecast_df = compute_ensemble_forecast(
        df,
        latest_date,
        include_target_date=include_today_in_training,
    )

    # Merge all forecasts
    merged = pd.merge(today_df, avg_df, on="Hour", how="outer").sort_values("Hour")

    if not forecast_df.empty:
        merged = pd.merge(merged, forecast_df, on="Hour", how="outer")

    baseline_df = compute_hourly_baseline(comparison_source)
    if baseline_df.empty and baseline is not None:
        baseline_df = baseline
    if not baseline_df.empty:
        expected_median = baseline_df[["Hour", "Expected"]].rename(
            columns={"Expected": "Expected Median"}
        )
        merged = pd.merge(merged, expected_median, on="Hour", how="outer")

    # Melt for plotting
    if not forecast_df.empty:
        value_vars = [
            "Today",
            "Average",
            "Prophet",
            "XGBoost",
            "Ensemble",
        ]
        value_vars = [v for v in value_vars if v in merged.columns]
    else:
        value_vars = ["Today", "Average"]
        value_vars = [v for v in value_vars if v in merged.columns]

    melted = merged.melt(id_vars="Hour", value_vars=value_vars, var_name="Series", value_name="Demand")

    # Define colors for each series
    color_map = {
        "Today": "#1f77b4",
        "Average": "#7f7f7f",
        "Prophet": "#ff7f0e",
        "XGBoost": "#2ca02c",
        "Ensemble": "#d62728",
        "Expected Median": "#4d4d4d",
    }

    fig = px.line(
        melted,
        x="Hour",
        y="Demand",
        color="Series",
        color_discrete_map=color_map,
        title=f"{title_prefix} - {latest_date.date()} | {scope_label}",
        markers=True,
    )

    style_today_trace(fig)

    # Add baseline band if available
    fig = add_baseline_to_figure(fig, baseline_df, sorted(merged["Hour"].dropna().unique()))

    # Highlight anomalies for the latest date
    anomalies = df[(df["Date"] == latest_date) & (df["Anomaly"])].copy()
    if not anomalies.empty:
        fig.add_trace(
            go.Scatter(
                x=anomalies["Hour"],
                y=anomalies["Ontario Demand"],
                mode="markers",
                marker=dict(size=11, color="#d62728", symbol="x"),
                name="Anomaly",
                customdata=anomalies[["Expected Demand", "Deviation", "Anomaly Score"]].to_numpy(),
                hovertemplate=(
                    "Hour: %{x}<br>"
                    "Demand: %{y:.1f} MW<br>"
                    "Expected: %{customdata[0]:.1f} MW<br>"
                    "Deviation: %{customdata[1]:.1f} MW<br>"
                    "Score: %{customdata[2]:.2f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Today vs Expected Accuracy")
    methods = ["Average", "Prophet", "XGBoost", "Ensemble", "Expected Median"]
    accuracy_rows: list[dict[str, Any]] = []
    for method in methods:
        if method not in merged.columns:
            continue

        comparison = merged[["Today", method]].dropna()
        if comparison.empty:
            continue

        mae = (comparison["Today"] - comparison[method]).abs().mean()
        accuracy = calculate_accuracy_percentage(comparison["Today"], comparison[method])
        accuracy_rows.append(
            {
                "Method": method,
                "Accuracy %": accuracy,
                "MAE (MW)": mae,
                "Compared Hours": len(comparison),
            }
        )

    if accuracy_rows:
        accuracy_df = pd.DataFrame(accuracy_rows)
        accuracy_df["Accuracy %"] = accuracy_df["Accuracy %"].map(
            lambda value: "N/A" if value is None else f"{value:.1f}%"
        )
        accuracy_df["MAE (MW)"] = accuracy_df["MAE (MW)"].round(1)
        st.dataframe(accuracy_df, use_container_width=True, hide_index=True)

    comparison_columns = ["Hour"] + [column for column in methods if column in merged.columns]
    if len(comparison_columns) > 1:
        st.subheader("Expected Demand Comparison")
        st.dataframe(merged[comparison_columns].round(1), use_container_width=True)


def render_forecast_training_comparison(df, scope_label, baseline=None):
    left_col, right_col = st.columns(2)

    with left_col:
        render_today_vs_forecast(
            df,
            scope_label,
            baseline=baseline,
            include_today_in_training=False,
        )

    with right_col:
        render_today_vs_forecast(
            df,
            scope_label,
            baseline=baseline,
            include_today_in_training=True,
        )


def render_latest_7_days(df, scope_label):
    dates = sorted(df["Date"].dt.normalize().dropna().unique())[-7:]
    recent_df = df[df["Date"].isin(dates)]
    if recent_df.empty:
        st.info("Not enough recent data yet")
        return
    fig = px.line(
        recent_df,
        x="Hour",
        y="Ontario Demand",
        color="Date Label",
        title=f"Latest 7 Dates | {scope_label}",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_latest_records(df, scope_label):
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
        title=f"Latest Records | {scope_label}",
        hover_data=["Hour", "Deviation", "Anomaly Score"],
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)


def render_anomaly_details(df, scope_label):
    anomaly_df = df[df["Anomaly"]].copy()
    st.subheader(f"Anomaly Details - {scope_label}")

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


def render_chart(df, view_mode, baseline, scope_label):
    if view_mode == "Today":
        render_today(df, scope_label, baseline=baseline)
    elif view_mode == "All Dates":
        render_all_dates(df, scope_label)
    elif view_mode == "Average":
        render_average(df, scope_label)
    elif view_mode == "Forecast Training Comparison":
        render_forecast_training_comparison(df, scope_label, baseline=baseline)
    elif view_mode == "Latest 7 Days":
        render_latest_7_days(df, scope_label)
    elif view_mode == "Latest Records":
        render_latest_records(df, scope_label)


def render_dashboard_content(view, scope, date_range, hour_range, show_normal_rows):
    queue_changed = drain_queue()
    df = dataframe_from_state()
    if not df.empty:
        df = calculate_anomalies(df)

    if queue_changed:
        st.session_state.last_error = None

    if df.empty:
        st.info("Waiting for data from the server...")
        return

    baseline = compute_hourly_baseline(df)
    df_view = apply_scope_and_filters(df, scope, date_range, hour_range)
    scope_label = build_scope_label(df_view, scope, hour_range)

    if df_view.empty:
        st.warning(f"No data matches the selected scope/filters. Active view: {scope_label}")
    else:
        render_metrics(df_view)
        st.caption(f"Active scope: {scope_label}")
        render_chart(df_view, view, baseline, scope_label)

        st.divider()
        render_anomaly_details(df_view, scope_label)

    df_table = df_view
    if not show_normal_rows:
        df_table = df_table[df_table["Anomaly"]]

    table_scope_label = build_scope_label(df_view, scope, hour_range)
    st.subheader(f"Latest Records - {table_scope_label}")

    if df_table.empty:
        if show_normal_rows:
            st.info(f"No records available for {table_scope_label}.")
        else:
            st.info(f"No anomaly rows available for {table_scope_label}. Turn on 'Show normal rows' to see all records.")

    st.dataframe(
        df_table[
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

    st.download_button(
        f"Download current view ({scope_label})",
        data=df_view.to_csv(index=False).encode("utf-8"),
        file_name="pub_dashboard_view.csv",
        mime="text/csv",
        key="download_current_view",
        on_click="ignore",
    )


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

df_sidebar = dataframe_from_state()
(
    view,
    refresh_seconds,
    auto_refresh_enabled,
    scope,
    date_range,
    hour_range,
    show_normal_rows,
) = sidebar_controls(df_sidebar)

if hasattr(st, "fragment"):
    @st.fragment(run_every=refresh_seconds if auto_refresh_enabled else None)
    def live_dashboard():
        render_dashboard_content(view, scope, date_range, hour_range, show_normal_rows)


    live_dashboard()
else:
    render_dashboard_content(view, scope, date_range, hour_range, show_normal_rows)
    if auto_refresh_enabled:
        time.sleep(refresh_seconds)
        st.rerun()
