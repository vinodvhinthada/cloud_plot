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
    "Nifty_Composite", "Bank_Composite",
    "Nifty_Smooth", "Bank_Smooth", "Nifty_Slope", "Bank_Slope"
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
    # --- Enhanced Stateful Signal Logic ---
    def detect_signals(meter, price, timestamps, symbol):
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
            "entry_value": None,
            "highest": None,
            "lowest": None,
            "last_signal_time": None,
            "cooldown": 0
        }

        signals = []
        sustain_window = 3  # must hold level for 3 bars
        cooldown_bars = 5   # ignore signals for next 5 bars after exit
        meter = np.array(meter)
        price = np.array(price)

        for i in range(3, len(meter)):
            curr = meter[i]
            prev = meter[i-1]
            slope = curr - prev
            timestamp = timestamps[i]

            if np.isnan(curr) or np.isnan(prev):
                continue

            # --- Cooldown logic ---
            if state["cooldown"] > 0:
                state["cooldown"] -= 1
                continue

            # --- Sustained confirmation (avoid noise) ---
            last_n = meter[i-sustain_window:i]
            if len(last_n) < sustain_window:
                continue

            avg_recent = np.mean(last_n)
            stable_up = np.all(last_n > 0.58)
            stable_down = np.all(last_n < 0.48)

            signal = None

            # LONG ENTRY
            if state["position"] is None and stable_up and slope > 0:
                signal = "ENTER-LONG"
                state["position"] = "LONG"
                state["entry_value"] = curr
                state["highest"] = curr
                state["lowest"] = curr

            # LONG EXIT or Reverse
            elif state["position"] == "LONG":
                state["highest"] = max(state["highest"], curr)
                drop = (state["highest"] - curr) / state["highest"]

                if drop >= 0.08 or curr < 0.58:
                    signal = "EXIT-LONG"
                    state["position"] = None
                    state["cooldown"] = cooldown_bars

                elif stable_down and slope < 0:
                    signal = "REVERSE-ENTER-SHORT"
                    state["position"] = "SHORT"
                    state["entry_value"] = curr
                    state["lowest"] = curr

            # SHORT ENTRY
            elif state["position"] is None and stable_down and slope < 0:
                signal = "ENTER-SHORT"
                state["position"] = "SHORT"
                state["entry_value"] = curr
                state["lowest"] = curr
                state["highest"] = curr

            # SHORT EXIT or Reverse
            elif state["position"] == "SHORT":
                state["lowest"] = min(state["lowest"], curr)
                rise = (curr - state["lowest"]) / abs(state["lowest"])

                if rise >= 0.08 or curr > 0.48:
                    signal = "EXIT-SHORT"
                    state["position"] = None
                    state["cooldown"] = cooldown_bars

                elif stable_up and slope > 0:
                    signal = "REVERSE-ENTER-LONG"
                    state["position"] = "LONG"
                    state["entry_value"] = curr
                    state["highest"] = curr

            # Record signal
            if signal:
                signals.append({
                    "Time": timestamp,
                    "Value": curr,
                    "Type": signal,
                    "Color": '#388E3C' if 'LONG' in signal else '#D32F2F',
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
                    df_plot["Nifty_Price_Action"].values,
                    df_plot["Time"].values,
                    "NIFTY"
                )
                all_signals = pd.DataFrame(nifty_signals)
            if "Bank_Composite" in selected_cols:
                bank_signals = detect_signals(
                    df_plot["Bank_Composite"].values,
                    df_plot["Bank_Price_Action"].values,
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
                color='Color:N',
                tooltip=[
                    alt.Tooltip('Time:T', title='Time', format='%Y-%m-%d %H:%M:%S'),
                    alt.Tooltip('Type:N', title='Signal Type'),
                    alt.Tooltip('Value:Q', title='Meter Value')
                ]
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
