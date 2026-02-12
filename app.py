import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION ---
st.set_page_config(page_title="Macro Terminal Pro", layout="wide")

# Style "Bloomberg Terminal"
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #1c2128; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
    .status-card { border-left: 5px solid #58a6ff; background-color: #1c2128; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    h1, h2, h3 { color: #f0f6fc; font-family: 'Segoe UI', sans-serif; }
    .stDataFrame { border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception:
    st.error("Clé API invalide ou problème de connexion.")
    st.stop()

# --- CODES SÉRIES RÉVISÉS (POUR UNE FIABILITÉ MAXIMALE) ---
# J'utilise ici les taux "Immediate Rates" ou "Policy Rates" les plus robustes
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL', 'symbol': 'USD'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW', 'symbol': 'EUR'},
    'JPY (BoJ)': {'rate': 'INTDSRJPM193N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS', 'symbol': 'JPY'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S', 'symbol': 'GBP'},
    'CAD (BoC)': {'rate': 'INTDSRCAM193N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S', 'symbol': 'CAD'},
    'AUD (RBA)': {'rate': 'INTDSRAUM193N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S', 'symbol': 'AUD'},
    'CHF (SNB)': {'rate': 'INTDSRCHM193N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S', 'symbol': 'CHF'},
}

# --- MOTEUR DE CALCUL ---

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0.0
    clean_s = series.ffill().dropna()
    if clean_s.empty: return 0.0
    return (clean_s.iloc[-1] - clean_s.mean()) / clean_s.std()

@st.cache_data(ttl=86400)
def fetch_data():
    data = []
    # On remonte à 7 ans pour avoir une base statistique solide malgré les retards de publication
    start_date = datetime.now() - timedelta(days=365*7)
    
    for currency, codes in central_banks.items():
        try:
            # Récupération Taux
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            # Récupération Inflation
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            # Récupération Liquidité
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()

            if s_rate.empty or s_cpi.empty: continue

            z_rate = calculate_z_score(s_rate)
            
            cpi_yoy = s_cpi.pct_change(12).dropna() * 100
            z_cpi = calculate_z_score(cpi_yoy)
            
            liq_yoy = s_liq.pct_change(12).dropna() * 100
            z_liq = calculate_z_score(s_liq)

            # Formule : On pondère le taux (x2) car c'est le driver principal
            macro_score = (z_rate * 2.0) + (z_cpi * 1.0) - (z_liq * 1.0)

            data.append({
                'Devise': currency,
                'Symbol': codes['symbol'],
                'Taux (%)': round(s_rate.iloc[-1], 2),
                'Z-Rate': round(z_rate, 2),
                'Inflation (%)': round(cpi_yoy.iloc[-1], 2),
                'Z-CPI': round(z_cpi, 2),
                'Liquidité (%)': round(liq_yoy.iloc[-1], 2),
                'Z-Liq': round(z_liq, 2),
                'Macro Score': round(macro_score, 2)
            })
        except: continue
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

def get_market_data(pair):
    try:
        ticker = f"{pair}=X"
        df_tick = yf.download(ticker, period="2y", interval="1d", progress=False)
        current = df_tick['Close'].iloc[-1].item()
        # Z-score prix sur 2 ans
        z_price = (current - df_tick['Close'].mean().item()) / df_tick['Close'].std().item()
        return round(current, 4), round(z_price, 2)
    except: return 0.0, 0.0

# --- AFFICHAGE ---

st.title("🏛️ Institutional Macro Terminal")
st.markdown(f"**Analyse Fundamental & Tactical Execution** | {datetime.now().strftime('%d %B %Y')}")

df = fetch_data()

if not df.empty:
    # 1. METRICS TOP BAR
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strongest (Hawk)", df.iloc[0]['Devise'], df.iloc[0]['Macro Score'])
    c2.metric("Weakest (Dove)", df.iloc[-1]['Devise'], df.iloc[-1]['Macro Score'], delta_color="inverse")
    c3.metric("Global Spread", round(df.iloc[0]['Macro Score'] - df.iloc[-1]['Macro Score'], 2))
    c4.metric("Data Status", "Live (FRED/IMF)")

    st.divider()

    # 2. TABLEAU DÉTAILLÉ (Le fond propre et pro)
    st.header("1. Fundamental Scoreboard")
    
    # Stylisage
    def color_values(val):
        if not isinstance(val, (int, float)): return ''
        if val > 1.2: return 'color: #28a745; font-weight: bold;' # Vert
        if val < -1.2: return 'color: #dc3545; font-weight: bold;' # Rouge
        return 'color: #adb5bd;'

    st.dataframe(
        df.style.applymap(color_values, subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
        .format("{:.2f}", subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score']),
        use_container_width=True, height=350
    )

    # 3. ANALYSE PRIX & OPPORTUNITÉS
    st.divider()
    st.header("2. Tactical Execution (Price vs Macro)")
    
    # On compare les 2 plus forts contre les 2 plus faibles
    hawks = df.iloc[:2]
    doves = df.iloc[-2:]
    
    col_opps = st.columns(2)
    idx = 0
    for _, h in hawks.iterrows():
        for _, d in doves.iterrows():
            pair = f"{h['Symbol']}{d['Symbol']}"
            price, z_price = get_market_data(pair)
            macro_div = round(h['Macro Score'] - d['Macro Score'], 2)
            
            # Logique de signal
            if z_price < 0: signal = "ACHAT (Sous-évalué) 🔥"
            elif z_price > 1.8: signal = "VENDU (Trop cher) ⚠️"
            else: signal = "Tendance Saine ✅"

            with col_opps[idx % 2]:
                st.markdown(f"""
                <div class="status-card">
                    <b>{h['Symbol']} / {d['Symbol']}</b> | Divergence Macro : {macro_div}
                </div>
                """, unsafe_allow_html=True)
                p1, p2, p3 = st.columns(3)
                p1.write(f"Prix: **{price}**")
                p2.write(f"Z-Price: **{z_price}**")
                p3.write(f"**{signal}**")
            idx += 1

    # 4. VISUALISATION
    st.divider()
    st.header("3. Market Strength Map")
    fig = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score',
                 color_continuous_scale='RdYlGn', template='plotly_dark')
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Données momentanément indisponibles sur FRED.")

st.caption("Méthodologie : Z-Score calculé sur 7 ans. Sources : FRED, IMF, Yahoo Finance.")
