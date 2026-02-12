import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Macro Alpha Terminal", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; }
    .opp-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .hawk-tag { color: #238636; font-weight: bold; background: #23863622; padding: 4px 8px; border-radius: 4px; }
    .dove-tag { color: #da3633; font-weight: bold; background: #da363322; padding: 4px 8px; border-radius: 4px; }
    h1, h2, h3 { color: #f0f6fc; font-family: 'Inter', sans-serif; }
    .text-muted { color: #8b949e; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True)

# --- API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except:
    st.error("Erreur API FRED")
    st.stop()

# --- CODES SÉRIES G10 (SÉRIES OCDE & M1 POUR STABILITÉ) ---
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL', 'symbol': 'USD'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW', 'symbol': 'EUR'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS', 'symbol': 'JPY'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S', 'symbol': 'GBP'},
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S', 'symbol': 'CAD'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S', 'symbol': 'AUD'},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S', 'symbol': 'CHF'},
}

# --- BACKEND ---

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0.0
    clean = series.ffill().dropna()
    return (clean.iloc[-1] - clean.mean()) / clean.std() if not clean.empty else 0.0

@st.cache_data(ttl=86400)
def fetch_macro():
    data = []
    start_date = datetime.now() - timedelta(days=365*8)
    for currency, codes in central_banks.items():
        row = {
            'Devise': currency, 'Symbol': codes['symbol'],
            'Taux (%)': 0.0, 'Z-Rate': 0.0, 'CPI (%)': 0.0, 
            'Z-CPI': 0.0, 'Liq/Masse (%)': 0.0, 'Z-Liq': 0.0, 'Macro Score': 0.0
        }
        try:
            # Récupération individuelle pour ne pas bloquer le pays si une série échoue
            try:
                r = fred.get_series(codes['rate'], observation_start=start_date).ffill()
                row['Taux (%)'] = r.iloc[-1]
                row['Z-Rate'] = calculate_z_score(r)
            except: pass

            try:
                c = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
                c_yoy = c.pct_change(12).dropna() * 100
                row['CPI (%)'] = c_yoy.iloc[-1]
                row['Z-CPI'] = calculate_z_score(c_yoy)
            except: pass

            try:
                l = fred.get_series(codes['liq'], observation_start=start_date).ffill()
                l_yoy = l.pct_change(12).dropna() * 100
                row['Liq/Masse (%)'] = l_yoy.iloc[-1]
                row['Z-Liq'] = calculate_z_score(l)
            except: pass
            
            # Calcul du score global
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Liq'] * 1.0)
            data.append(row)
        except:
            data.append(row)
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

def fetch_price(pair):
    try:
        ticker = f"{pair}=X"
        df_p = yf.download(ticker, period="2y", interval="1d", progress=False)
        curr = df_p['Close'].iloc[-1].item()
        z = (curr - df_p['Close'].mean().item()) / df_p['Close'].std().item()
        return round(curr, 4), round(z, 2)
    except: return 0.0, 0.0

# --- UI START ---
st.title("🏛️ Institutional Macro Terminal")
df = fetch_macro()

if not df.empty:
    # Top Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Strongest", df.iloc[0]['Symbol'], f"{df.iloc[0]['Macro Score']:.2f}")
    m2.metric("Weakest", df.iloc[-1]['Symbol'], f"{df.iloc[-1]['Macro Score']:.2f}", delta_color="inverse")
    m3.metric("Max Divergence", round(df.iloc[0]['Macro Score'] - df.iloc[-1]['Macro Score'], 2))
    m4.metric("Active Assets", len(df), "G10 Coverage")

    tab1, tab2, tab3 = st.tabs(["📊 Force Relative", "🎯 Opportunités Tactiques", "📑 Données Fondamentales"])

    with tab1:
        col_left, col_right = st.columns([1, 1])
        with col_left:
            st.subheader("Currency Strength Meter")
            fig_bar = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score',
                             color_continuous_scale='RdYlGn', template='plotly_dark')
            st.plotly_chart(fig_bar, use_container_width=True)
        
        with col_right:
            st.subheader("Visualisation du Cycle (G10)")
            fig_cycle = px.scatter(df, x="Z-CPI", y="Z-Rate", text="Symbol", size=[20]*len(df),
                                   color="Macro Score", color_continuous_scale='RdYlGn',
                                   labels={'Z-CPI': 'Inflation Momentum (Z)', 'Z-Rate': 'Rate Tightness (Z)'},
                                   template='plotly_dark')
            fig_cycle.add_hline(y=0, line_dash="dash", line_color="#444")
            fig_cycle.add_vline(x=0, line_dash="dash", line_color="#444")
            st.plotly_chart(fig_cycle, use_container_width=True)

    with tab2:
        st.header("⚡ Opportunités Classées par Divergence")
        
        # Génération et classement des paires
        opps = []
        for i in range(len(df)):
            for j in range(len(df)-1, i, -1):
                h = df.iloc[i]
                d = df.iloc[j]
                div_score = h['Macro Score'] - d['Macro Score']
                if div_score > 1.5: # On garde les divergences significatives
                    opps.append((h, d, div_score))
        
        # Tri par divergence décroissante
        opps.sort(key=lambda x: x[2], reverse=True)

        for h, d, div_score in opps[:6]: # Affiche le Top 6
            pair_name = f"{h['Symbol']}{d['Symbol']}"
            price, z_price = fetch_price(pair_name)
            
            sig_text = "TENDANCE"
            if z_price < -1: sig_text = "VALEUR EXTRÊME 🔥"
            elif z_price > 1.5: sig_text = "SUR-ACHAT ⚠️"

            st.markdown(f"""
            <div class="opp-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 1.5em; font-weight: bold;">{h['Symbol']} / {d['Symbol']}</span>
                    <span class="hawk-tag">{sig_text}</span>
                </div>
                <div style="display: flex; gap: 40px; margin-top: 15px;">
                    <div><span class="text-muted">Divergence Macro</span><br><b style="font-size: 1.2em;">{div_score:.2f}</b></div>
                    <div><span class="text-muted">Prix Actuel</span><br><b>{price}</b></div>
                    <div><span class="text-muted">Z-Score Prix (2y)</span><br><b style="color: {'#238636' if z_price < 0 else '#da3633'}">{z_price}</b></div>
                    <div><span class="text-muted">Confiance</span><br><b>{'Haute' if div_score > 3.5 else 'Moyenne'}</b></div>
                </div>
                <div style="margin-top: 15px; border-top: 1px solid #30363d; padding-top: 10px;">
                    <span class="text-muted">ANALYSE :</span> 
                    Achat de <b>{h['Symbol']}</b> contre <b>{d['Symbol']}</b>. 
                    Le différentiel de taux est de <b>{(h['Taux (%)']-d['Taux (%)']):.2f}%</b>.
                </div>
            </div>
            """, unsafe_allow_html=True)

    with tab3:
        st.subheader("Fundamental Analysis Ledger")
        st.dataframe(
            df.style.map(lambda x: 'color: #238636; font-weight: bold' if isinstance(x, float) and x > 1.2 else ('color: #da3633; font-weight: bold' if isinstance(x, float) and x < -1.2 else ''), 
                                subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
            .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Liq/Masse (%)', 'Z-Liq', 'Macro Score']),
            use_container_width=True, height=450
        )

else:
    st.error("Échec de la synchronisation des données.")

st.caption(f"Terminal G10 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
