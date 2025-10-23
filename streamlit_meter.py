import streamlit as st
import pandas as pd
import requests
import time
import numpy as np

def calc_slope(series, window=3):
    slopes = [np.nan] * len(series)
    for i in range(window, len(series)):
        y = series[i-window:i]
        x = np.arange(window)
        if np.any(np.isnan(y)):
            slopes[i] = np.nan
        else:
            slope = np.polyfit(x, y, 1)[0]  # slope of linear fit
            slopes[i] = slope
    return slopes

st.set_page_config(page_title="📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard", layout="wide")
st.title("📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard")

# Columns available for plotting
plot_cols = [
    "Nifty_ISS", "Bank_ISS", "Nifty_Price_Action", "Bank_Price_Action",
    "Nifty_Composite", "Bank_Composite"
]

# Multiselect for user to choose plots
selected_cols = st.multiselect(
    "Select plots to display:",
    options=plot_cols,
    default=["Nifty_Composite", "Bank_Composite"]
)

# New Google Sheets CSV URL
url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQrpJFwXLrYYl35032xsjaKQdaIfEF5Zaqsw8Q9VfhxdBwqf_v9LOlISNT1UPOQDHA-3VFldvcz-ZSu/pub?output=csv"

REFRESH_INTERVAL = 300  # seconds (5 minutes)

placeholder = st.empty()

while True:
    df = pd.read_csv(url)

    # Convert numeric columns
    for col in ["Nifty_ISS", "Bank_ISS", "Nifty_Price_Action", "Bank_Price_Action"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- Simple Composite Calculation for Chart (match webapp) ---
    if all(col in df.columns for col in ["Nifty_ISS", "Nifty_Price_Action"]):
        df["Nifty_Composite"] = (df["Nifty_ISS"] + df["Nifty_Price_Action"]) / 2
        df["Nifty_Smooth"] = df["Nifty_Composite"].rolling(5).mean()
        df["Nifty_Slope"] = df["Nifty_Composite"].diff().rolling(3).mean()
    else:
        df["Nifty_Composite"] = np.nan
        df["Nifty_Smooth"] = np.nan
        df["Nifty_Slope"] = np.nan

    if all(col in df.columns for col in ["Bank_ISS", "Bank_Price_Action"]):
        df["Bank_Composite"] = (df["Bank_ISS"] + df["Bank_Price_Action"]) / 2
        df["Bank_Smooth"] = df["Bank_Composite"].rolling(5).mean()
        df["Bank_Slope"] = df["Bank_Composite"].diff().rolling(3).mean()
    else:
        df["Bank_Composite"] = np.nan
        df["Bank_Smooth"] = np.nan
        df["Bank_Slope"] = np.nan

    # --- Trading Signal Detection Logic ---
    # Enhanced Meter Signal Logic for Nifty/BankNifty
    def detect_signals(meter, price, timestamps, symbol):
        import datetime
        SIGNAL_SYMBOLS = {
            "ENTER-LONG": "🟢",
            "EXIT-LONG": "🚪",
            "REVERSE-ENTER-SHORT": "🔄🔴",
            "ENTER-SHORT": "🔴",
            "EXIT-SHORT": "🚪",
            "REVERSE-ENTER-LONG": "🔄🟢"
        }
        state = {
            "position": None,
            "highest_since_entry": None,
            "lowest_since_entry": None,
            "last_signal_time": None,
            "meter_history": [],
            "prev_meter": None,
            "wait_after_exit": 0
        }
        signals = []
        for i in range(len(meter)):
            curr_meter = meter[i]
            curr_price = price[i]
            timestamp = timestamps[i]
            # Slope
            slope = curr_meter - state["prev_meter"] if state["prev_meter"] is not None else 0
            state["prev_meter"] = curr_meter
            abs_slope = abs(slope)

            # Safety: skip if not enough readings
            if i < 1:
                continue

            # Safety: skip if in neutral zone
            if 0.55 <= curr_meter <= 0.6:
                continue

            # Safety: skip if not enough momentum
            if abs_slope < 0.02:
                continue

            # Safety: confirm with price direction
            price_dir = curr_price - price[i-1] if i > 0 else 0

            # Maintain meter history (last 3)
            state["meter_history"].append(curr_meter)
            if len(state["meter_history"]) > 3:
                state["meter_history"].pop(0)

            # Minimum time gap filter (10 min)
            if state["last_signal_time"]:
                try:
                    time_diff = (datetime.datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M") -
                                 datetime.datetime.strptime(str(state["last_signal_time"]), "%Y-%m-%d %H:%M")).total_seconds()/60
                    if time_diff < 10:
                        continue
                except Exception:
                    pass

            # Wait for 2 new readings after exit before re-enter
            if state["wait_after_exit"] > 0:
                state["wait_after_exit"] -= 1
                continue

            # Update highest/lowest since entry
            if state["position"] == "LONG":
                state["highest_since_entry"] = max(state["highest_since_entry"], curr_meter)
            elif state["position"] == "SHORT":
                state["lowest_since_entry"] = min(state["lowest_since_entry"], curr_meter)
            else:
                state["highest_since_entry"] = curr_meter
                state["lowest_since_entry"] = curr_meter

            drop_from_high = (state["highest_since_entry"] - curr_meter)/state["highest_since_entry"] if state["highest_since_entry"] else 0
            rise_from_low = (curr_meter - state["lowest_since_entry"])/state["lowest_since_entry"] if state["lowest_since_entry"] else 0

            signal = None

            # --- LONG LOGIC ---
            if state["position"] != "LONG" and curr_meter > 0.6 and slope > 0 and price_dir > 0:
                signal = "ENTER-LONG"
                state["position"] = "LONG"
                state["highest_since_entry"] = curr_meter
                state["lowest_since_entry"] = curr_meter

            elif state["position"] == "LONG" and (drop_from_high >= 0.1 or curr_meter < 0.65 or (len(state["meter_history"]) == 3 and all(x < state["meter_history"][-2] for x in state["meter_history"]))):
                signal = "EXIT-LONG"
                state["position"] = None
                state["wait_after_exit"] = 2

            elif curr_meter < 0.5 and slope < 0:
                signal = "REVERSE-ENTER-SHORT"
                state["position"] = "SHORT"
                state["highest_since_entry"] = curr_meter
                state["lowest_since_entry"] = curr_meter

            # --- SHORT LOGIC ---
            elif state["position"] != "SHORT" and curr_meter < 0.5 and slope < 0 and price_dir < 0:
                signal = "ENTER-SHORT"
                state["position"] = "SHORT"
                state["highest_since_entry"] = curr_meter
                state["lowest_since_entry"] = curr_meter

            elif state["position"] == "SHORT" and (rise_from_low >= 0.1 or curr_meter > 0.45 or (len(state["meter_history"]) == 3 and all(x > state["meter_history"][-2] for x in state["meter_history"]))):
                signal = "EXIT-SHORT"
                state["position"] = None
                state["wait_after_exit"] = 2

            elif curr_meter > 0.6 and slope > 0:
                signal = "REVERSE-ENTER-LONG"
                state["position"] = "LONG"
                state["highest_since_entry"] = curr_meter
                state["lowest_since_entry"] = curr_meter

            if signal:
                state["last_signal_time"] = timestamp
                signals.append({
                    "Time": timestamp,
                    "Value": curr_meter,
                    "Type": signal,
                    "Color": '#388E3C' if 'LONG' in signal else '#D32F2F' if 'SHORT' in signal else '#FF9800',
                    "Text": SIGNAL_SYMBOLS.get(signal, '')
                })
        return signals

    # Filter for today's data and market hours only
    if "Timestamp" in df.columns:
        # Parse Timestamp to datetime
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')
        today = pd.Timestamp.now().normalize()
        # Market hours: 09:15 to 15:30
        market_open = pd.Timestamp.combine(today, pd.to_datetime("09:15").time())
        market_close = pd.Timestamp.combine(today, pd.to_datetime("15:30").time())
        df_today = df[(df["Timestamp"].dt.normalize() == today) &
                     (df["Timestamp"] >= market_open) &
                     (df["Timestamp"] <= market_close)]
        import altair as alt
        with placeholder.container():
            # ...existing code...
            df_plot = df_today.copy()
            df_plot["Time"] = df_plot["Timestamp"]

            # Reference zones
            ref_bands = [
                alt.Chart(pd.DataFrame({"y": [0.4, 0.6]})).mark_rule(strokeDash=[2,2], color="#888", strokeWidth=1).encode(y="y"),
                alt.Chart(pd.DataFrame({"y": [0.45, 0.55]})).mark_rect(opacity=0.08, color="#999").encode(y="y", y2="y")
            ]

            # Plot only selected columns
            chart_layers = [*ref_bands]
            if "Nifty_Composite" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeWidth=2).encode(
                        x=alt.X('Time:T', title='Time', axis=alt.Axis(grid=True, labelAngle=0, tickCount=10)),
                        y=alt.Y('Nifty_Composite:Q', title='Nifty Composite', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True)),
                        color=alt.value('#2196F3'),
                        tooltip=['Time:T', 'Nifty_Composite:Q']
                    ).properties(width=900, height=400)
                )
            if "Bank_Composite" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeWidth=2).encode(
                        x='Time:T',
                        y=alt.Y('Bank_Composite:Q', title='Bank Composite', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True)),
                        color=alt.value('#FF5722'),
                        tooltip=['Time:T', 'Bank_Composite:Q']
                    )
                )
            if "Nifty_Smooth" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeWidth=3).encode(
                        x='Time:T',
                        y='Nifty_Smooth:Q',
                        color=alt.value('#1976D2'),
                        tooltip=['Time:T', 'Nifty_Smooth:Q']
                    )
                )
            if "Bank_Smooth" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeWidth=3).encode(
                        x='Time:T',
                        y='Bank_Smooth:Q',
                        color=alt.value('#E64A19'),
                        tooltip=['Time:T', 'Bank_Smooth:Q']
                    )
                )
            if "Nifty_Slope" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeDash=[4,2], color='#4CAF50', opacity=0.5).encode(
                        x='Time:T',
                        y='Nifty_Slope:Q',
                        tooltip=['Time:T', 'Nifty_Slope:Q']
                    )
                )
            if "Bank_Slope" in selected_cols:
                chart_layers.append(
                    alt.Chart(df_plot).mark_line(strokeDash=[4,2], color='#F44336', opacity=0.5).encode(
                        x='Time:T',
                        y='Bank_Slope:Q',
                        tooltip=['Time:T', 'Bank_Slope:Q']
                    )
                )

            # --- Trading Signal Markers ---
            all_signals = pd.DataFrame()
            if "Nifty_Composite" in selected_cols:
                nifty_signals = detect_signals(
                    df_plot["Nifty_Composite"].values,
                    df_plot["Nifty_Price"].values,
                    df_plot["Time"].values,
                    "NIFTY"
                )
                all_signals = pd.DataFrame(nifty_signals)
            if "Bank_Composite" in selected_cols:
                bank_signals = detect_signals(
                    df_plot["Bank_Composite"].values,
                    df_plot["Bank_Price"].values,
                    df_plot["Time"].values,
                    "BANKNIFTY"
                )
                if all_signals.empty:
                    all_signals = pd.DataFrame(bank_signals)
                else:
                    all_signals = pd.concat([all_signals, pd.DataFrame(bank_signals)], ignore_index=True)


            # Draw vertical lines at each signal time
            if not all_signals.empty:
                vline_layer = alt.Chart(all_signals).mark_rule(strokeDash=[2,2], color='#222', strokeWidth=1).encode(
                    x='Time:T'
                )
            else:
                vline_layer = None

            signal_layer = alt.Chart(all_signals).mark_text(fontSize=16, fontWeight='bold', dy=-10).encode(
                x='Time:T',
                y='Value:Q',
                text='Text:N',
                color='Color:N'
            ) if not all_signals.empty else alt.Chart(pd.DataFrame({'Time':[], 'Value':[], 'Text':[], 'Color':[]})).mark_text()
            if vline_layer is not None:
                chart_layers.append(vline_layer)
            chart_layers.append(signal_layer)

            # Compose chart
            chart = alt.layer(*chart_layers).resolve_scale(y='shared').properties(width=900, height=400)
            st.altair_chart(chart, use_container_width=True)

            # Calculate and display latest slope for each selected metric
            st.markdown("### Latest Slope Values (window=3)")
            for metric in ["Nifty_Composite", "Bank_Composite"]:
                if metric in df_today.columns:
                    slopes = calc_slope(df_today[metric].values, window=3)
                    latest_slope = slopes[-1] if len(slopes) > 0 else np.nan
                    st.write(f"{metric}: {latest_slope:.4f}")
            st.write(f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("No 'Timestamp' column found in data.")
    time.sleep(REFRESH_INTERVAL)