import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard", layout="wide")
st.title("📊 NIFTY & BANKNIFTY Enhanced Meter Dashboard")

url = "https://sheet.best/api/sheets/1Rw8fu7R0NZJpI2au_SKTs2-6N6qHcoA5snyBcMmtkxc"

REFRESH_INTERVAL = 300  # seconds (5 minutes)

placeholder = st.empty()

while True:
    data = requests.get(url).json()
    df = pd.DataFrame(data)

    # Convert numeric columns
    cols = ["Nifty_ISS", "Bank_ISS", "Nifty_PA_Zone", "Bank_PA_Zone", "Nifty_Price_Action", "Bank_Price_Action"]
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Filter for today's data only
    if "Timestamp" in df.columns:
        # Try to parse Timestamp to datetime
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')
        today = pd.Timestamp.now().normalize()
        df_today = df[df["Timestamp"].dt.normalize() == today]
        with placeholder.container():
            st.line_chart(df_today.set_index("Timestamp")[cols])
            st.write(f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("No 'Timestamp' column found in data.")

    time.sleep(REFRESH_INTERVAL)
