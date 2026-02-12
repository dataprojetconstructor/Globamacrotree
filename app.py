import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION ET STYLE ---
st.set_page_config(page_title="Global Macro Edge | Central Bank Terminal", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f4f7f9; }
    .stMetric { background-color: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .hawk-card { border-left: 6px solid #28a745; background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 15px; }
    .dove-card { border-left: 6px solid #dc3545; background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 15px; }
    .opportunity-card { border: 1px solid #e0e0e0; background-color: #ffffff; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    h1, h2, h3 { color: #1e293b; font-family: 'Inter', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# --- GESTION API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception:
    st.error("Erreur de connexion API FRED.")
    st.stop()

# --- CODES SÉRIES ---
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL', 'symbol': 'USD'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW', 'symbol': 'EUR'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS', 'symbol': 'JPY'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S', 'symbol': 'GBP'},
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S', 'symbol': 'CAD'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S', 'symbol': 'AUD'},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S', 'symbol': 'CHF'},
}

# --- FONCTIONS DE CALCUL ---

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0.0
    clean_s = series.ffill().dropna()
    return (clean_s.iloc[-1] - clean_s.mean()) / clean_s.std() if not clean_s.empty else 0.0

@st.cache_data(ttl=86400)
def fetch_macro_data():
    data_list = []
    start_date = datetime.now() - timedelta(days=365*6)
    for currency, codes in central_banks.items():
        try:
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()

            macro_score = (calculate_z_score(s_rate) * 2.0) + (calculate_z_score(s_cpi.pct_change(12)) * 1.0) - (calculate_z_score(s_liq.pct_change(12)) * 1.0)
            data_list.append({
                'Devise': currency, 'Symbol': codes['symbol'],
                'Taux (%)': s_rate.iloc[-1], 'CPI (%)': (s_cpi.pct_change(12).iloc[-1]*100),
                'Macro Score': macro_score, 'Z-Rate': calculate_z_score(s_rate)
            })
        except: continue
    return pd.DataFrame(data_list).sort_values(by='Macro Score', ascending=False)

def get_price_z_score(pair_name):
    """Calcule le Z-score du prix actuel par rapport à la moyenne 2 ans"""
    try:
        ticker = f"{pair_name}=X"
        data = yf.download(ticker, period="2y", interval="1d", progress=False)
        if data.empty: return 0.0, 0.0
        current_price = data['Close'].iloc[-1].item() # Correction pour extraire la valeur scalaire
        mean_price = data['Close'].mean().item()
        std_price = data['Close'].std().item()
        z_price = (current_price - mean_price) / std_price
        return round(current_price, 4), round(z_price, 2)
    except:
        return 0.0, 0.0

# --- ENGINE ---
df_macro = fetch_macro_data()

# --- INTERFACE ---
st.title("🏛️ Institutional Macro Terminal")
st.markdown(f"**Analyse Fundamental & Tactical Execution** | {datetime.now().strftime('%d %B %Y')}")
st.divider()

# KPI Top Bar
if not df_macro.empty:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Strongest Currency", df_macro.iloc[0]['Devise'], f"Score: {df_macro.iloc[0]['Macro Score']:.2f}")
    m2.metric("Weakest Currency", df_macro.iloc[-1]['Devise'], f"Score: {df_macro.iloc[-1]['Macro Score']:.2f}", delta_color="inverse")
    m3.metric("Alpha Spread", f"{(df_macro.iloc[0]['Macro Score'] - df_macro.iloc[-1]['Macro Score']):.2f}")
    m4.metric("Market Sentiment", "Risk-On" if df_macro.iloc[0]['Symbol'] != 'USD' else "Risk-Off")

# TABS
tab1, tab2, tab3 = st.tabs(["📊 Force Relative", "🎯 Opportunités Tactiques", "📑 Rapport Détaillé"])

with tab1:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        fig_strength = px.bar(df_macro, x='Macro Score', y='Devise', orientation='h', color='Macro Score', 
                             color_continuous_scale='RdYlGn', title="Global Currency Strength Meter")
        st.plotly_chart(fig_strength, use_container_width=True)
    with col_b:
        st.markdown("### 💡 Analyse Flash")
        top_h = df_macro.iloc[0]
        st.info(f"**{top_h['Devise']}** domine le marché. Ses fondamentaux suggèrent une poursuite de la force via le différentiel de taux.")

with tab2:
    st.header("⚡ Opportunités Macro + Prix (Z-Score)")
    st.write("Cette section croise la macroéconomie (Fondamental) avec la position du prix (Technique).")
    
    # On génère les paires candidates
    pairs_to_analyze = []
    for i in range(min(3, len(df_macro))):
        for j in range(len(df_macro)-1, len(df_macro)-3, -1):
            if i != j:
                pairs_to_analyze.append((df_macro.iloc[i], df_macro.iloc[j]))

    c_op1, c_op2 = st.columns(2)
    
    for idx, (long_cur, short_cur) in enumerate(pairs_to_analyze[:4]):
        pair_name = f"{long_cur['Symbol']}{short_cur['Symbol']}"
        price, z_price = get_price_z_score(pair_name)
        
        target_col = c_op1 if idx % 2 == 0 else c_op2
        
        with target_col:
            st.markdown(f"""
            <div class="hawk-card">
                <b>PAIRE : {long_cur['Symbol']} / {short_cur['Symbol']}</b><br>
                <span style="font-size: 0.9em; color: #64748b;">Divergence Macro : {(long_cur['Macro Score'] - short_cur['Macro Score']):.2f}</span>
            </div>
            """, unsafe_allow_html=True)
            
            p1, p2, p3 = st.columns(3)
            p1.metric("Prix Actuel", price)
            
            # Couleur du Z-Price
            z_color = "normal"
            if z_price > 1.5: z_color = "inverse" # Cher
            elif z_price < -1.5: z_color = "normal" # Pas cher
            
            p2.metric("Z-Score Prix", z_price, delta="Surchargé" if z_price > 1.5 else "Sous-évalué", delta_color=z_color)
            
            # Logique de signal
            signal = "Attendre"
            if z_price < 0: signal = "ACHAT (Value) 🔥"
            elif z_price > 2: signal = "Prise de Profit ⚠️"
            else: signal = "Tendance Saine ✅"
            
            p3.write(f"**Signal :**\n{signal}")
            st.write("---")

with tab3:
    st.subheader("Données Fondamentales Complètes")
    st.dataframe(df_macro.style.background_gradient(cmap='RdYlGn', subset=['Macro Score', 'Z-Rate']), use_container_width=True)
    
    st.markdown("### 📘 Guide de lecture des opportunités")
    st.write("""
    1. **Convergence (Le Trade de Valeur) :** Si la Macro est très positive mais que le Z-Score du prix est négatif (prix bas), c'est une anomalie de marché. Le prix finira par remonter pour rejoindre ses fondamentaux.
    2. **Momentum (Le Trade de Tendance) :** Si la Macro est positive et le Z-Score du prix est entre 0 et 1.5, la tendance est saine et confirmée.
    3. **Saturation :** Si le Z-Score du prix dépasse 2.0, le mouvement est peut-être épuisé à court terme malgré de bons fondamentaux.
    """)

st.caption("Données : FRED St Louis & Yahoo Finance API. Les Z-Scores Prix sont calculés sur une fenêtre de 500 jours de trading.")
