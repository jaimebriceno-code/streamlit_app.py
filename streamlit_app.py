import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Baby Morgan Market", page_icon="👶", layout="centered")

# --- GOOGLE SHEETS CONNECTION ---
# st.cache_resource keeps the connection open so it doesn't re-authenticate on every click
@st.cache_resource
def get_gsheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

client = get_gsheets_client()
SHEET_URL = st.secrets["SHEET_URL"]

# --- DATA HANDLING ---
def load_data():
    """Reads the live data directly from the three Google Sheet tabs."""
    sheet = client.open_by_url(SHEET_URL)
    
    # 1. Load the Market Pool
    try:
        pool_records = sheet.worksheet("Pool").get_all_records()
        pool = {row['Side']: float(row['Shares']) for row in pool_records} if pool_records else {'Girl': 100.0, 'Boy': 100.0}
    except Exception:
        pool = {'Girl': 100.0, 'Boy': 100.0}
        
    # 2. Load the Positions
    try:
        pos_records = sheet.worksheet("Positions").get_all_records()
        positions = {row['Trader']: {'Girl_Shares': row['Girl_Shares'], 'Boy_Shares': row['Boy_Shares'], 'Total_Spent': row['Total_Spent']} for row in pos_records}
    except Exception:
        positions = {}
        
    # 3. Load the Bet History
    try:
        history = sheet.worksheet("History").get_all_records()
    except Exception:
        history = []
        
    return sheet, pool, positions, history

def save_data(sheet, pool, positions, history):
    """Writes the updated dictionaries back to the Google Sheet."""
    
    # Update Pool Tab
    pool_data = [["Side", "Shares"], ["Girl", pool['Girl']], ["Boy", pool['Boy']]]
    sheet.worksheet("Pool").clear()
    sheet.worksheet("Pool").update(values=pool_data, range_name="A1")
    
    # Update Positions Tab
    pos_data = [["Trader", "Girl_Shares", "Boy_Shares", "Total_Spent"]]
    for trader, data in positions.items():
        pos_data.append([trader, data['Girl_Shares'], data['Boy_Shares'], data['Total_Spent']])
    sheet.worksheet("Positions").clear()
    sheet.worksheet("Positions").update(values=pos_data, range_name="A1")
    
    # Update History Tab
    if history:
        hist_data = [list(history[0].keys())] + [list(h.values()) for h in history]
        sheet.worksheet("History").clear()
        sheet.worksheet("History").update(values=hist_data, range_name="A1")

# Fetch fresh data on every page load
try:
    sheet, pool, positions, history = load_data()
except Exception as e:
    st.error(f"Error connecting to Google Sheets. Check your Secrets formatting. Details: {e}")
    st.stop()

def get_price(side):
    total = pool['Girl'] + pool['Boy']
    return pool[side] / total

# --- UI: HEADER & LIVE ODDS ---
st.title("👶 Baby Morgan Prediction Market")
st.markdown("Live Kalshi-style market. Prices adjust automatically based on group demand.")

girl_price = get_price('Girl') * 100
boy_price = get_price('Boy') * 100

col1, col2 = st.columns(2)
col1.metric("Girl (Yes)", f"{girl_price:.1f}¢")
col2.metric("Boy (Yes)", f"{boy_price:.1f}¢")

# --- UI: BET ENTRY FORM ---
st.divider()
st.subheader("💵 Place a Bet")
with st.form("bet_form", clear_on_submit=True):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        trader = st.text_input("Trader Name")
    with col_b:
        side = st.selectbox("Side", ["Girl", "Boy"])
    with col_c:
        dollars = st.number_input("Amount ($)", min_value=1.0, step=1.0)
    
    submitted = st.form_submit_button("Submit Bet")
    
    if submitted and trader and dollars > 0:
        current_price = get_price(side)
        shares = dollars / current_price
        
        # 1. Update the Market Line
        pool[side] += shares
        
        # 2. Update their Portfolio
        if trader not in positions:
            positions[trader] = {'Girl_Shares': 0.0, 'Boy_Shares': 0.0, 'Total_Spent': 0.0}
        positions[trader][f'{side}_Shares'] += shares
        positions[trader]['Total_Spent'] += dollars
        
        # 3. Log the Receipt
        history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "trader": trader,
            "side": side,
            "dollars": dollars,
            "price_cents": current_price * 100,
            "shares": shares
        })
        
        # 4. Push to Google Sheets immediately
        save_data(sheet, pool, positions, history)
        st.success(f"✅ {trader} bet ${dollars:.2f} on {side} at {current_price * 100:.1f}¢!")
        st.rerun()

# --- UI: LEDGER & BALANCES ---
st.divider()
st.subheader("📊 Current Balances")
if positions:
    df_positions = pd.DataFrame.from_dict(positions, orient='index')
    df_positions.index.name = 'Trader'
    df_positions = df_positions.rename(columns={
        'Girl_Shares': 'Girl Shares', 
        'Boy_Shares': 'Boy Shares', 
        'Total_Spent': 'Owed to Pot ($)'
    })
    st.dataframe(df_positions.style.format("{:.1f}"), use_container_width=True)
else:
    st.info("No active positions yet.")

# --- UI: RECEIPT TAPE ---
st.divider()
st.subheader("🧾 Bet History")
if history:
    df_history = pd.DataFrame(history)
    df_history = df_history.rename(columns={
        'time': 'Time', 'trader': 'Trader', 'side': 'Side', 
        'dollars': 'Bet ($)', 'price_cents': 'Price (¢)', 'shares': 'Shares'
    })
    st.dataframe(df_history.style.format({
        'Bet ($)': '{:.2f}', 'Price (¢)': '{:.1f}', 'Shares': '{:.1f}'
    }), use_container_width=True)
else:
    st.info("No bets placed yet.")
