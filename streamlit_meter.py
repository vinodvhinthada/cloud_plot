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
        """
        Stateful signal generator for a full series (meter, price, timestamps).
        - meter: array-like of composite meter values (0..1)
        - price: array-like of corresponding price action / price values (numeric)
        - timestamps: array-like of timestamps (strings or pd.Timestamp)
        - symbol: string (for label only)
        Returns: list of signals dicts with Time, Value, Type, Color, Text
        """
        import numpy as np

        # --- PARAMETERS (tune if required) ---
        ENTRY_THRESH = 0.60           # require meter >= this to consider long entry
        ENTRY_SLOPE = 0.02            # slope threshold for entry
        ENTRY_PERSIST = 2             # require entry condition to hold for this many bars
        EXIT_BUFFER = 0.65            # "watch" zone; falling below this triggers exit checks
        TRAIL_DROP = 0.08             # drop-from-peak fraction to trigger immediate exit (8%)
        SLOPE_EXIT = -0.02            # strong negative slope to exit
        MIN_BARS_BETWEEN_SIGNALS = 2  # minimum bars between successive signals (~10 min if 5-min bars)
        REV_THRESH = 0.50             # threshold to consider reversal into short
        SHORT_ENTRY_SLOPE = -0.02
        SHORT_ENTRY_PERSIST = 2
        SHORT_EXIT_BUFFER = 0.45
        REVERSE_MIN_BARS = 2          # require a couple bars before reversing to avoid noise

        n = len(meter)
        if n == 0:
            return []

        # Ensure numpy arrays
        meter = np.array(meter, dtype=float)
        price = np.array(price, dtype=float)

        # compute slope series using your calc_slope (window=3)
        try:
            slopes = np.array(calc_slope(list(meter), window=3))
        except Exception:
            slopes = np.full(n, np.nan)
            for i in range(1, n):
                slopes[i] = meter[i] - meter[i-1]

        signals = []
        position = None               # None, 'LONG', 'SHORT'
        highest_since_entry = np.nan
        lowest_since_entry = np.nan
        last_signal_bar = -999
        entry_confirm_count = 0
        short_confirm_count = 0

        # helper to add signal
        def push_signal(i, typ):
            nonlocal position, highest_since_entry, lowest_since_entry, last_signal_bar
            txt_map = {
                "ENTER-LONG": "🟢 ENTRY-LONG",
                "EXIT-LONG": "🚪 EXIT-LONG",
                "ENTER-SHORT": "🔴 ENTRY-SHORT",
                "EXIT-SHORT": "🟢 EXIT-SHORT",
                "REVERSE-ENTER-LONG": "🔄 🟢 REVERSE-LONG",
                "REVERSE-ENTER-SHORT": "🔄 🔴 REVERSE-SHORT"
            }
            color = '#388E3C' if 'LONG' in typ and 'EXIT' not in typ else '#D32F2F' if 'SHORT' in typ and 'EXIT' not in typ else '#FF9800'
            signals.append({
                "Time": timestamps[i],
                "Value": float(meter[i]),
                "Type": typ,
                "Color": color,
                "Text": txt_map.get(typ, typ)
            })
            last_signal_bar = i

        for i in range(n):
            # skip early bars where slope is NaN
            if np.isnan(meter[i]) or np.isnan(slopes[i]):
                continue

            # avoid signals too close to previous signal (reduce spam)
            if i - last_signal_bar < MIN_BARS_BETWEEN_SIGNALS:
                # still update running peak/val for trailing stops if in position
                if position == 'LONG':
                    highest_since_entry = max(highest_since_entry, meter[i])
                elif position == 'SHORT':
                    lowest_since_entry = min(lowest_since_entry, meter[i])
                continue

            slope = slopes[i]
            curr = meter[i]
            price_dir = price[i] - price[i-1] if i > 0 and not np.isnan(price[i-1]) else 0.0

            # update confirm counters
            # entry confirm for LONG: require consecutive meters above ENTRY_THRESH and positive slope
            if curr >= ENTRY_THRESH and slope >= ENTRY_SLOPE and price_dir > 0:
                entry_confirm_count += 1
            else:
                entry_confirm_count = 0

            # entry confirm for SHORT
            if curr <= REV_THRESH and slope <= SHORT_ENTRY_SLOPE and price_dir < 0:
                short_confirm_count += 1
            else:
                short_confirm_count = 0

            # maintain highest/lowest for trailing logic
            if position == 'LONG':
                if np.isnan(highest_since_entry):
                    highest_since_entry = curr
                else:
                    highest_since_entry = max(highest_since_entry, curr)
            elif position == 'SHORT':
                if np.isnan(lowest_since_entry):
                    lowest_since_entry = curr
                else:
                    lowest_since_entry = min(lowest_since_entry, curr)
            else:
                # not in position: keep base values
                highest_since_entry = curr
                lowest_since_entry = curr

            # ========== ENTRY logic ===========
            if position is None:
                # Long entry confirmed
                if entry_confirm_count >= ENTRY_PERSIST:
                    # Enter LONG
                    push_signal(i, "ENTER-LONG")
                    position = "LONG"
                    highest_since_entry = curr
                    lowest_since_entry = curr
                    entry_confirm_count = 0
                    short_confirm_count = 0
                    continue

                # Short entry confirmed
                if short_confirm_count >= SHORT_ENTRY_PERSIST:
                    push_signal(i, "ENTER-SHORT")
                    position = "SHORT"
                    highest_since_entry = curr
                    lowest_since_entry = curr
                    entry_confirm_count = 0
                    short_confirm_count = 0
                    continue

            # ========== IN-POSITION EXIT / REVERSE logic ===========
            if position == "LONG":
                # trailing drop
                drop_from_high = 0.0
                if not np.isnan(highest_since_entry) and highest_since_entry > 0:
                    drop_from_high = (highest_since_entry - curr) / highest_since_entry

                # Immediate exit if steep drop from peak
                if drop_from_high >= TRAIL_DROP:
                    push_signal(i, "EXIT-LONG")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # Exit on strong negative slope
                if slope <= SLOPE_EXIT:
                    push_signal(i, "EXIT-LONG")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # Exit if meter falls into watch/weak zone and slope weakens (early exit)
                if curr < EXIT_BUFFER and slope < 0.01:
                    push_signal(i, "EXIT-LONG")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # Reverse to SHORT if strong reversal signals appear (avoid immediate flip—require consecutive)
                if curr < REV_THRESH and slope <= SHORT_ENTRY_SLOPE and short_confirm_count >= REVERSE_MIN_BARS:
                    push_signal(i, "REVERSE-ENTER-SHORT")
                    position = "SHORT"
                    highest_since_entry = curr
                    lowest_since_entry = curr
                    entry_confirm_count = 0
                    short_confirm_count = 0
                    continue

            elif position == "SHORT":
                # rise from low
                rise_from_low = 0.0
                if not np.isnan(lowest_since_entry) and lowest_since_entry > 0:
                    rise_from_low = (curr - lowest_since_entry) / lowest_since_entry

                # immediate exit if strong bounce
                if rise_from_low >= TRAIL_DROP:
                    push_signal(i, "EXIT-SHORT")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # exit on strong positive slope
                if slope >= abs(SLOPE_EXIT):
                    push_signal(i, "EXIT-SHORT")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # exit if meter moves back to weak short zone
                if curr > SHORT_EXIT_BUFFER and slope > -0.01:
                    push_signal(i, "EXIT-SHORT")
                    position = None
                    highest_since_entry = np.nan
                    lowest_since_entry = np.nan
                    continue

                # reverse to LONG if strong flip
                if curr > ENTRY_THRESH and slope >= ENTRY_SLOPE and entry_confirm_count >= REVERSE_MIN_BARS:
                    push_signal(i, "REVERSE-ENTER-LONG")
                    position = "LONG"
                    highest_since_entry = curr
                    lowest_since_entry = curr
                    entry_confirm_count = 0
                    short_confirm_count = 0
                    continue

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