# Real-Time Electricity Demand Dashboard - User Guide

Welcome to the Real-Time Electricity Demand Dashboard! This guide will help you understand and use the dashboard, even if you have no technical background.

---

## What Is This Dashboard?

This dashboard shows you real-time electricity demand data. Think of it like a live monitor that shows:

- **How much electricity is being using right now** (measured in MW - Megawatts)
- **When usage is normal vs. unusual** (anomalies)
- **Historical patterns** so you can see trends over time

The dashboard automatically receives data from a server and displays it in easy-to-understand charts and tables.

---

> **Note:** Make sure the server is running first! The dashboard needs to connect to the server to get data.

---

## Understanding the Main Screen

When you open the dashboard, you'll see several key areas:

### 1. Top Metrics (The Three Boxes)

At the top of the page, you'll see three boxes showing:

| Metric | What It Means |
|--------|---------------|
| **Peak Demand** | The highest electricity usage recorded in the selected time period |
| **Avg Demand** | The average electricity usage over the selected time period |
| **Total Records** | How many data points are being shown |

### 2. Status Message

Below the metrics, you'll see either:

- **🟢 "System normal"** - Everything is running as expected
- **🟡 "X anomalies detected"** - Some unusual patterns were found (see "Understanding Anomalies" below)

### 3. The Chart

The main area shows a line chart with:

- **X-axis (horizontal)**: Hours of the day (0 = midnight, 12 = noon, 23 = 11 PM)
- **Y-axis (vertical)**: Electricity demand in MW
- **Colored lines**: Different dates or data series
- **Gray shaded area**: The "expected" range (normal operating range)
- **Red X markers**: Points where demand was unusual (anomalies)

### 4. Data Table

At the bottom, there's a table showing the raw data with columns for:
- Date
- Hour
- Actual Demand (MW)
- Expected Demand (MW)
- Deviation (how far from expected)
- Anomaly Score
- Status

---

## Using the Sidebar Controls

The left sidebar contains all the controls you need to customize what you see.

### Controls Section

#### Refresh Interval (Slider)

- **What it does:** Controls how often the dashboard updates
- **Range:** 1 to 10 seconds
- **Default:** 2 seconds
- **Tip:** Lower = more responsive but uses more resources

#### Auto Refresh (Checkbox)

- **What it does:** Turns automatic updating on or off
- **Default:** ON
- **Tip:** Turn OFF if you want to study a specific moment without it changing

#### Refresh Now Button

- **What it does:** Forces an immediate update
- **Use when:** Data seems stuck or you want to manually refresh

---

### Scope Section

This controls **which dates** of data to display.

| Option | What It Shows |
|--------|---------------|
| **All data** | Every piece of data available |
| **Today** | Only the most recent date's data |
| **Last 7 days** | The past week's data |
| **Custom date range** | Pick your own start and end dates |

**How to use Custom Date Range:**

1. Select "Custom date range" from the dropdown
2. A date picker will appear below
3. Click the start date, then click the end date
4. The dashboard will update to show only those dates

---

### Filters Section

#### Hour Range (Slider)

- **What it does:** Filters data to show only certain hours of the day
- **Default:** 0-23 (all day)
- **Example:** If you set it to 9-17, you'll only see data from 9 AM to 5 PM

#### Show Normal Rows (Checkbox)

- **What it does:** Controls whether the data table shows normal records
- **Default:** OFF (only shows anomalies)
- **Tip:** Turn ON to see all data, not just unusual ones

---

### View Section

This is one of the most important controls! It changes **how the data is displayed**.

| View Mode | What It Shows |
|-----------|---------------|
| **Today** | A line chart of today's demand with expected range |
| **All Dates** | Lines for every date available (color-coded) |
| **Average** | A single line showing the average demand for each hour |
| **Today vs Average** | Today's data compared to the typical pattern |
| **Latest 7 Days** | The most recent 7 days of data |
| **Latest Records** | A bar chart of the most recent 50 records |

**Recommended for beginners:**
- Start with **"Today"** to see current data
- Use **"Today vs Average"** to understand how today compares to normal
- Switch to **"All Dates"** when you want to see patterns over time

---

## Understanding Anomalies

### What Is an Anomaly?

An anomaly is when the electricity demand is significantly different from what we'd normally expect at that particular hour.

The dashboard uses a mathematical formula to detect anomalies:
- It calculates the "expected" demand for each hour based on historical patterns
- If today's demand deviates more than 3 times the normal variation, it's marked as an anomaly

### How to Identify Anomalies

In the chart:
- **Red X markers** indicate anomalies
- Hover over a red X to see details:
  - Hour
  - Actual Demand
  - Expected Demand
  - Deviation (how far off)
  - Anomaly Score (higher = more unusual)

In the data table:
- Rows with "Anomaly detected" in the Status column
- The Anomaly Score column shows how unusual (score ≥ 3 = anomaly)

### What to Do When You See Anomalies

1. **Check the deviation** - How far is the actual demand from expected?
2. **Note the time** - Is this during peak hours (morning/evening)?
3. **Look for patterns** - Do anomalies happen at the same time each day?
4. **Compare views** - Use "Today vs Average" to see how unusual today is

---

## Connection Status

In the sidebar, you'll see connection information:

### History Buffer
Shows how many records are currently stored in memory (up to 20,000).

### Connection
- **"Streaming"** - Connected and receiving live data
- **"Starting"** - Still connecting (wait a few seconds)

### Last Update
Shows how many seconds ago the last data was received. If it says "N/A", no data has been received yet.

### Available Dates
Shows the date range of the data currently loaded.

---

## Downloading Data

Need to save the data you're viewing? Here's how:

1. Configure your desired **Scope** and **Filters**
2. Click the **"Download current view"** button at the bottom
3. A CSV file will download with all the currently displayed data

The filename will be `pub_dashboard_view.csv`.

---

## Troubleshooting

### "Waiting for data from the server..."

**Cause:** The server isn't running or the dashboard can't connect.

**Solution:**
1. Make sure the server is running (see server README)
2. Check the terminal for error messages
3. Click "Refresh now" button

### Data seems outdated

**Solution:**
1. Check "Last update" in the sidebar - if it's been a while, click "Refresh now"
2. Make sure "Auto refresh" is checked
3. Lower the refresh interval (try 1 second)

### Charts not loading

**Possible causes:**
- No data available for selected scope
- Browser needs to be refreshed

**Solution:**
1. Try a different view mode (e.g., "Today" instead of "All Dates")
2. Check scope settings
3. Refresh the browser page

### Connection errors in sidebar

**Cause:** Lost connection to server

**Solution:**
1. Check that server is still running
2. Click "Refresh now" to reconnect
3. If problem persists, restart both server and dashboard

---

## Quick Reference Card

| Task | How to Do It |
|------|---------------|
| See today's data | Set View = "Today" |
| Compare today to normal | Set View = "Today vs Average" |
| See last week's trends | Set Scope = "Last 7 days" |
| Find unusual patterns | Look for red X markers |
| See only anomalies | Keep "Show normal rows" OFF |
| Download data | Click "Download current view" |
| Manual refresh | Click "Refresh now" |
| Focus on specific hours | Adjust Hour Range slider |

---

## Glossary

| Term | Simple Explanation |
|------|---------------------|
| **MW (Megawatt)** | A unit of power - how much electricity is being used |
| **Demand** | The amount of electricity being used at a given time |
| **Anomaly** | Something unusual - demand much higher or lower than expected |
| **Baseline** | The normal/expected pattern based on historical data |
| **Deviation** | How far the actual demand is from what's expected |
| **Scope** | The date range of data being shown |
| **View** | The way data is displayed (chart type) |

---

## Need More Help?

If you encounter issues not covered in this guide:

1. Check the server is running properly
2. Try restarting both server and dashboard
3. Look at error messages in the terminal
4. Consult the main project README for system requirements

---

*This guide was created to help non-technical users understand and operate the Real-Time Electricity Demand Dashboard.*