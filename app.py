import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION ET STYLE PROFESSIONNEL ---
st.set_page_config(page_title="Global Macro Terminal", layout="wide")

# Style CSS pour un rendu "Terminal Bloomberg/Reuters" (Fond sombre, texte clair)
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #1c2128; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
    div[data-testid="stMetricValue"] { color: #58a6ff; font-size: 28px; }
    .status-box { padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #30363d; }
    h1, h2, h3 { color: #f0f6fc; }
    .stDataFrame { border: 1px solid #30363d; }
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

# --- CODES SÉRIES (Version Stable & Détaillée) ---
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
    if series is None or len(series) < 10: return 0.0
    clean_s = series.ffill().dropna()
    if clean_s.empty: return 0.0
    return (clean_s.iloc[-1] - clean_s.mean()) / clean_s.std()

@st.cache_data(ttl=86400)
def fetch_full_macro():
    data_list = []
    start_date = datetime.now() - timedelta(days=365*6)
    for currency, codes in central_banks.items():
        try:
            # Récupération
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()

            # Calculs
            z_rate = calculate_z_score(s_rate)
            
            cpi_yoy = s_cpi.pct_change(12).dropna() * 100
            z_cpi = calculate_z_score(cpi_yoy)
            
            liq_yoy = s_liq.pct_change(12).dropna() * 100
            z_liq = calculate_z_score(s_liq)

            score = (z_rate * 2.0) + (z_cpi * 1.0) - (z_liq * 1.0)

            data_list.append({
                'Devise': currency,
                'Symbol': codes['symbol'],
                'Taux (%)': s_rate.iloc[-1],
                'Z-Rate': z_rate,
                'CPI (%)': cpi_yoy.iloc[-1],
                'Z-CPI': z_cpi,
                'Liq/Masse M. (%)': liq_yoy.iloc[-1],
                'Z-Liq': z_liq,
                'Macro Score': score
            })
        except: continue
    return pd.DataFrame(data_list).sort_values(by='Macro Score', ascending=False)

def fetch_price_data(pair):
    try:
        ticker = f"{pair}=X"
        d = yf.download(ticker, period="2y", interval="1d", progress=False)
        if d.empty: return 0, 0
        current = float(d['Close'].iloc[-1])
        z_price = (current - d['Close'].mean()) / d['Close'].std()
        return round(current, 4), round(float(z_price), 2)
    except: return 0, 0

# --- Lancement du moteur ---
df = fetch_full_macro()

# --- INTERFACE ---
st.title("🏛️ Global Macro Alpha Terminal")
st.markdown(f"**Données Institutionnelles** | Flux : FRED & Yahoo Finance | Mise à jour : {datetime.now().strftime('%d/%m/%Y')}")

# Section KPI
if not df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Strongest (Hawk)", df.iloc[0]['Devise'], f"{df.iloc[0]['Macro Score']:.2f}")
    k2.metric("Weakest (Dove)", df.iloc[-1]['Devise'], f"{df.iloc[-1]['Macro Score']:.2f}", delta_color="inverse")
    k3.metric("Max Spread", f"{(df.iloc[0]['Macro Score'] - df.iloc[-1]['Macro Score']):.2f}")
    k4.metric("Market State", "Divergence" if abs(df['Macro Score'].mean()) < 2 else "Trend")

st.divider()

# --- SECTION 1 : TABLEAU DÉTAILLÉ (Le coeur de l'outil) ---
st.header("1. Analyse Fondamentale Détaillée")
st.markdown("Ce tableau compare les politiques monétaires via le Z-Score (écart à la moyenne sur 5 ans).")

# Stylisage du tableau pour visibilité max
def color_macro(val):
    if not isinstance(val, (int, float)): return ''
    color = '#1c2128'
    if val > 1.2: color = '#14522d' # Vert sombre
    elif val < -1.2: color = '#611623' # Rouge sombre
    return f'background-color: {color}'

st.dataframe(
    df.style.applymap(color_macro, subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
    .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Liq/Masse M. (%)', 'Z-Liq', 'Macro Score']),
    use_container_width=True, height=350
)

st.divider()

# --- SECTION 2 : GRAPHIQUE DE FORCE ---
st.header("2. Force Relative des Devises")
col_bar, col_scat = st.columns([1, 1])

with col_bar:
    fig_bar = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score',
                     color_continuous_scale='RdYlGn', template='plotly_dark')
    st.plotly_chart(fig_bar, use_container_width=True)

with col_scat:
    fig_scat = px.scatter(df, x="Z-CPI", y="Z-Rate", text="Devise", size=[25]*len(df),
                          color="Macro Score", color_continuous_scale='RdYlGn', template='plotly_dark',
                          title="Cycle : Inflation vs Taux")
    fig_scat.add_hline(y=0, line_dash="dash")
    fig_scat.add_vline(x=0, line_dash="dash")
    st.plotly_chart(fig_scat, use_container_width=True)

st.divider()

# --- SECTION 3 : OPPORTUNITÉS TACTIQUES (MACRO + PRIX) ---
st.header("3. Signaux d'Exécution (Divergence vs Prix)")
st.markdown("On cherche les paires où la **Macro est forte** mais le **Prix est encore bas** (Z-Score Prix < 0).")

# Génération des meilleures paires (Top Hawk vs Top Dove)
best_hawk = df.iloc[:2]
best_dove = df.iloc[-2:]

opportunities = []
for _, h in best_hawk.iterrows():
    for _, d in best_dove.iterrows():
        pair = f"{h['Symbol']}{d['Symbol']}"
        price, z_price = fetch_price_data(pair)
        macro_div = h['Macro Score'] - d['Macro Score']
        
        # Logique de signal
        if z_price < -1: signal = "ACHAT D'OR (Sous-évalué) 🔥"
        elif z_price < 0: signal = "ACHAT (Value) ✅"
        elif z_price > 1.5: signal = "SURACHAT (Attendre repli) ⚠️"
        else: signal = "Tendance Confirmée 📈"
        
        opportunities.append({
            'Paire': f"{h['Symbol']}/{d['Symbol']}",
            'Div. Macro': round(macro_div, 2),
            'Prix Actuel': price,
            'Z-Score Prix (2y)': z_price,
            'Signal Tactique': signal
        })

if opportunities:
    opp_df = pd.DataFrame(opportunities).sort_values(by='Div. Macro', ascending=False)
    
    # Affichage sous forme de colonnes pour lisibilité
    for i, row in opp_df.iterrows():
        with st.container():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            c1.markdown(f"### {row['Paire']}")
            c2.metric("Div. Macro", row['Div. Macro'])
            c3.metric("Z-Score Prix", row['Z-Score Prix (2y)'], 
                      delta="Sous-évalué" if row['Z-Score Prix (2y)'] < 0 else "Cher",
                      delta_color="normal" if row['Z-Score Prix (2y)'] < 0 else "inverse")
            c4.info(f"**Diagnostic :** {row['Signal Tactique']}")
            st.write("---")

st.caption("Source : FRED St-Louis (Macro) & Yahoo Finance (Prix). Le Z-Score Prix compare le prix actuel à sa moyenne sur les 500 derniers jours.")
