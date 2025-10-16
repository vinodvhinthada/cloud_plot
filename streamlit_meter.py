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
            # Only show composite plots by default
            composite_metrics = ["Nifty_Composite", "Bank_Composite"]
            smooth_metrics = ["Nifty_Smooth", "Bank_Smooth"]
            slope_metrics = ["Nifty_Slope", "Bank_Slope"]
            # Prepare data for Altair
            df_plot = df_today.copy()
            df_plot["Time"] = df_plot["Timestamp"]

            # Reference zones
            ref_bands = [
                alt.Chart(pd.DataFrame({"y": [0.4, 0.6]})).mark_rule(strokeDash=[2,2], color="#888", strokeWidth=1).encode(y="y"),
                alt.Chart(pd.DataFrame({"y": [0.45, 0.55]})).mark_rect(opacity=0.08, color="#999").encode(y="y", y2="y")
            ]

            # Composite lines
            lines = alt.Chart(df_plot).mark_line(strokeWidth=2).encode(
                x=alt.X('Time:T', title='Time', axis=alt.Axis(grid=True, labelAngle=0, tickCount=10)),
                y=alt.Y('Nifty_Composite:Q', title='Composite Value', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True)),
                color=alt.value('#2196F3'),
                tooltip=['Time:T', 'Nifty_Composite:Q']
            ).properties(width=900, height=400)
            lines2 = alt.Chart(df_plot).mark_line(strokeWidth=2).encode(
                x='Time:T',
                y='Bank_Composite:Q',
                color=alt.value('#FF5722'),
                tooltip=['Time:T', 'Bank_Composite:Q']
            )

            # Smooth lines
            smooth1 = alt.Chart(df_plot).mark_line(strokeWidth=3).encode(
                x='Time:T',
                y='Nifty_Smooth:Q',
                color=alt.value('#1976D2'),
                tooltip=['Time:T', 'Nifty_Smooth:Q']
            )
            smooth2 = alt.Chart(df_plot).mark_line(strokeWidth=3).encode(
                x='Time:T',
                y='Bank_Smooth:Q',
                color=alt.value('#E64A19'),
                tooltip=['Time:T', 'Bank_Smooth:Q']
            )

            # Slope lines (momentum)
            slope1 = alt.Chart(df_plot).mark_line(strokeDash=[4,2], color='#4CAF50', opacity=0.5).encode(
                x='Time:T',
                y='Nifty_Slope:Q',
                tooltip=['Time:T', 'Nifty_Slope:Q']
            )
            slope2 = alt.Chart(df_plot).mark_line(strokeDash=[4,2], color='#F44336', opacity=0.5).encode(
                x='Time:T',
                y='Bank_Slope:Q',
                tooltip=['Time:T', 'Bank_Slope:Q']
            )

            # Signal markers
            signal_df = pd.DataFrame()
            for metric, slope_col, comp_col, color, arrow, cond_up, cond_down in [
                ("Nifty_Composite", "Nifty_Slope", "Nifty_Composite", '#388E3C', '▲', lambda s, c: s > 0 and c > 0.55, lambda s, c: s < 0 and c < 0.45),
                ("Bank_Composite", "Bank_Slope", "Bank_Composite", '#D32F2F', '▼', lambda s, c: s < 0 and c < 0.45, lambda s, c: s > 0 and c > 0.55)
            ]:
                if slope_col in df_plot.columns and comp_col in df_plot.columns:
                    for i in range(1, len(df_plot)):
                        prev_slope = df_plot[slope_col].iloc[i-1]
                        curr_slope = df_plot[slope_col].iloc[i]
                        curr_comp = df_plot[comp_col].iloc[i]
                        if np.isnan(prev_slope) or np.isnan(curr_slope) or np.isnan(curr_comp):
                            continue
                        # Upward signal
                        if prev_slope < 0 and cond_up(curr_slope, curr_comp):
                            signal_df = pd.concat([signal_df, pd.DataFrame({
                                'Time': [df_plot['Time'].iloc[i]],
                                'Value': [curr_comp],
                                'Color': [color],
                                'Arrow': [arrow]
                            })])
                        # Downward signal
                        if prev_slope > 0 and cond_down(curr_slope, curr_comp):
                            signal_df = pd.concat([signal_df, pd.DataFrame({
                                'Time': [df_plot['Time'].iloc[i]],
                                'Value': [curr_comp],
                                'Color': [color],
                                'Arrow': [arrow]
                            })])

            signal_layer = alt.Chart(signal_df).mark_text(fontSize=18, fontWeight='bold', dy=-10).encode(
                x='Time:T',
                y='Value:Q',
                text='Arrow:N',
                color='Color:N'
            ) if not signal_df.empty else alt.Chart(pd.DataFrame({'Time':[], 'Value':[], 'Arrow':[], 'Color':[]})).mark_text()

            # Compose chart
            chart = alt.layer(
                *ref_bands,
                lines, lines2,
                smooth1, smooth2,
                slope1, slope2,
                signal_layer
            ).resolve_scale(
                y='shared'
            ).properties(
                width=900,
                height=400
            )
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
