import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard", layout="wide")
st.title("📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard")

# Columns available for plotting
plot_cols = [
    "Nifty_ISS", "Bank_ISS", "Nifty_Price_Action", "Bank_Price_Action",
    "Nifty_Composite_Meter", "Bank_Composite_Meter"
]

# Multiselect for user to choose plots
selected_cols = st.multiselect(
    "Select plots to display:",
    options=plot_cols,
    default=plot_cols
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

    import numpy as np
    # --- Composite Meter Calculation for Nifty ---
    if all(col in df.columns for col in ["Nifty_ISS", "Nifty_Price_Action"]):
        price_centered = df["Nifty_Price_Action"] - df["Nifty_Price_Action"].rolling(12).mean()
        oi_centered = df["Nifty_ISS"] - df["Nifty_ISS"].rolling(12).mean()
        adaptive_weight = np.clip((df["Nifty_ISS"] - 0.5) * 2, 0.2, 0.8)
        composite = adaptive_weight * oi_centered + (1 - adaptive_weight) * price_centered
        ema1 = composite.ewm(span=3, adjust=False).mean()
        ema2 = ema1.ewm(span=3, adjust=False).mean()
        smoothed_signal = 2 * ema1 - ema2
        rolling_min = smoothed_signal.rolling(24).min()
        rolling_max = smoothed_signal.rolling(24).max()
        normalized_final = (smoothed_signal - rolling_min) / (rolling_max - rolling_min + 1e-8)
        df["Nifty_Composite_Meter"] = normalized_final.clip(0, 1)
    else:
        df["Nifty_Composite_Meter"] = np.nan

    # --- Composite Meter Calculation for BankNifty ---
    if all(col in df.columns for col in ["Bank_ISS", "Bank_Price_Action"]):
        price_centered = df["Bank_Price_Action"] - df["Bank_Price_Action"].rolling(12).mean()
        oi_centered = df["Bank_ISS"] - df["Bank_ISS"].rolling(12).mean()
        adaptive_weight = np.clip((df["Bank_ISS"] - 0.5) * 2, 0.2, 0.8)
        composite = adaptive_weight * oi_centered + (1 - adaptive_weight) * price_centered
        ema1 = composite.ewm(span=3, adjust=False).mean()
        ema2 = ema1.ewm(span=3, adjust=False).mean()
        smoothed_signal = 2 * ema1 - ema2
        rolling_min = smoothed_signal.rolling(24).min()
        rolling_max = smoothed_signal.rolling(24).max()
        normalized_final = (smoothed_signal - rolling_min) / (rolling_max - rolling_min + 1e-8)
        df["Bank_Composite_Meter"] = normalized_final.clip(0, 1)
    else:
        df["Bank_Composite_Meter"] = np.nan

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
        with placeholder.container():
            if selected_cols:
                st.line_chart(df_today.set_index("Timestamp")[selected_cols])
            else:
                st.info("Please select at least one plot to display.")
            st.write(f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("No 'Timestamp' column found in data.")

    time.sleep(REFRESH_INTERVAL)
