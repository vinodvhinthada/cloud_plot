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
    else:
        df["Nifty_Composite"] = np.nan

    if all(col in df.columns for col in ["Bank_ISS", "Bank_Price_Action"]):
        df["Bank_Composite"] = (df["Bank_ISS"] + df["Bank_Price_Action"]) / 2
    else:
        df["Bank_Composite"] = np.nan

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
            if selected_cols:
                # Melt dataframe for Altair multi-line chart
                df_melt = df_today.melt(id_vars=["Timestamp"], value_vars=selected_cols, var_name="Metric", value_name="Value")
                chart = alt.Chart(df_melt).mark_line().encode(
                    x=alt.X('Timestamp:T', title='Time', axis=alt.Axis(grid=True)),
                    y=alt.Y('Value:Q', title='Value', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True)),
                    color='Metric:N'
                ).properties(
                    width=900,
                    height=400
                )
                st.altair_chart(chart, use_container_width=True)

                # Calculate and display latest slope for each selected metric
                st.markdown("### Latest Slope Values (window=3)")
                for metric in selected_cols:
                    if metric in df_today.columns:
                        slopes = calc_slope(df_today[metric].values, window=3)
                        latest_slope = slopes[-1] if len(slopes) > 0 else np.nan
                        st.write(f"{metric}: {latest_slope:.4f}")
            else:
                st.info("Please select at least one plot to display.")
            st.write(f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("No 'Timestamp' column found in data.")

    time.sleep(REFRESH_INTERVAL)
