import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION ---
st.set_page_config(page_title="Macro Terminal Pro", layout="wide")

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

# --- CODES SÉRIES RÉVISÉS (SÉRIES OCDE ULTRA-STABLES) ---
# J'ai utilisé les codes 'IRSTCI01' qui sont les taux du marché monétaire suivis par l'OCDE
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL', 'symbol': 'USD'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW', 'symbol': 'EUR'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS', 'symbol': 'JPY'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S', 'symbol': 'GBP'},
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S', 'symbol': 'CAD'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S', 'symbol': 'AUD'},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S', 'symbol': 'CHF'},
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
    # On remonte à 10 ans pour assurer une base statistique large
    start_date = datetime.now() - timedelta(days=365*10)
    
    progress_bar = st.progress(0, text="Synchronisation G10 en cours...")
    count = 0

    for currency, codes in central_banks.items():
        count += 1
        progress_bar.progress(count / len(central_banks))
        
        # Initialisation par défaut pour éviter de sauter un pays
        res = {
            'Devise': currency, 'Symbol': codes['symbol'],
            'Taux (%)': 0.0, 'Z-Rate': 0.0,
            'Inflation (%)': 0.0, 'Z-CPI': 0.0,
            'Liquidité (%)': 0.0, 'Z-Liq': 0.0,
            'Macro Score': 0.0
        }
        
        try:
            # 1. TAUX
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if not s_rate.empty:
                res['Taux (%)'] = s_rate.iloc[-1]
                res['Z-Rate'] = calculate_z_score(s_rate)

            # 2. INFLATION
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            if not s_cpi.empty:
                cpi_yoy = s_cpi.pct_change(12).dropna() * 100
                if not cpi_yoy.empty:
                    res['Inflation (%)'] = cpi_yoy.iloc[-1]
                    res['Z-CPI'] = calculate_z_score(cpi_yoy)

            # 3. LIQUIDITÉ (Bilan ou Masse Monétaire)
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()
            if not s_liq.empty:
                liq_yoy = s_liq.pct_change(12).dropna() * 100
                if not liq_yoy.empty:
                    res['Liquidité (%)'] = liq_yoy.iloc[-1]
                    res['Z-Liq'] = calculate_z_score(s_liq)

            # Formule Macro Score
            res['Macro Score'] = (res['Z-Rate'] * 2.0) + (res['Z-CPI'] * 1.0) - (res['Z-Liq'] * 1.0)
            data.append(res)
        except Exception as e:
            # Si erreur, on garde les valeurs par défaut mais on n'exclut pas le pays
            data.append(res)
            
    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

def get_market_data(pair):
    try:
        ticker = f"{pair}=X"
        df_tick = yf.download(ticker, period="2y", interval="1d", progress=False)
        current = df_tick['Close'].iloc[-1].item()
        z_price = (current - df_tick['Close'].mean().item()) / df_tick['Close'].std().item()
        return round(current, 4), round(z_price, 2)
    except: return 0.0, 0.0

# --- AFFICHAGE ---

st.title("🏛️ Institutional Macro Terminal")
st.markdown(f"**G10 Currency Surveillance** | Flux : FRED/OECD | {datetime.now().strftime('%d %B %Y')}")

df = fetch_data()

if not df.empty:
    # 1. METRICS TOP BAR
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strongest Currency", df.iloc[0]['Devise'], f"{df.iloc[0]['Macro Score']:.2f}")
    c2.metric("Weakest Currency", df.iloc[-1]['Devise'], f"{df.iloc[-1]['Macro Score']:.2f}", delta_color="inverse")
    c3.metric("Alpha Spread", round(df.iloc[0]['Macro Score'] - df.iloc[-1]['Macro Score'], 2))
    c4.metric("Coverage", f"{len(df)} Countries")

    st.divider()

    # 2. TABLEAU DÉTAILLÉ
    st.header("1. Fundamental Analysis Table")
    
    def color_values(val):
        if not isinstance(val, (int, float)): return ''
        if val > 1.2: return 'color: #28a745; font-weight: bold;'
        if val < -1.2: return 'color: #dc3545; font-weight: bold;'
        return 'color: #adb5bd;'

    st.dataframe(
        df.style.applymap(color_values, subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
        .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'Inflation (%)', 'Z-CPI', 'Liquidité (%)', 'Z-Liq', 'Macro Score']),
        use_container_width=True, height=400
    )

    # 3. OPPORTUNITÉS TACTIQUES
    st.divider()
    st.header("2. Tactical Execution (Price vs Macro)")
    
    hawks = df.iloc[:2]
    doves = df.iloc[-2:]
    
    col_opps = st.columns(2)
    idx = 0
    for _, h in hawks.iterrows():
        for _, d in doves.iterrows():
            pair = f"{h['Symbol']}{d['Symbol']}"
            price, z_price = get_market_data(pair)
            macro_div = round(h['Macro Score'] - d['Macro Score'], 2)
            
            # Diagnostic tactique
            if z_price < 0: signal = "ACHAT (Value) 🔥"
            elif z_price > 1.8: signal = "SURACHAT (Attendre) ⚠️"
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

    # 4. GRAPHIQUE
    st.divider()
    st.header("3. Global Strength Map")
    fig = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score',
                 color_continuous_scale='RdYlGn', template='plotly_dark')
    fig.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Données momentanément indisponibles.")

st.caption("Méthodologie : Z-Scores calculés sur 10 ans. Liquidité basée sur le bilan ou la masse monétaire M1/M3.")
