import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Macro Alpha Terminal", layout="wide")

st.markdown("""
    <style>
    /* Global Theme */
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; }
    
    /* Card Style */
    .opp-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .hawk-tag { color: #238636; font-weight: bold; background: #23863622; padding: 4px 8px; border-radius: 4px; }
    .dove-tag { color: #da3633; font-weight: bold; background: #da363322; padding: 4px 8px; border-radius: 4px; }
    
    /* Typography */
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

# --- CODES SÉRIES G10 (STABLES) ---
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
    if series is None or len(series) < 10: return 0.0
    clean = series.ffill().dropna()
    return (clean.iloc[-1] - clean.mean()) / clean.std() if not clean.empty else 0.0

@st.cache_data(ttl=86400)
def fetch_macro():
    data = []
    start_date = datetime.now() - timedelta(days=365*8)
    for currency, codes in central_banks.items():
        try:
            r = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            c = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            l = fred.get_series(codes['liq'], observation_start=start_date).ffill()
            
            c_yoy = c.pct_change(12).dropna() * 100
            l_yoy = l.pct_change(12).dropna() * 100
            
            z_r, z_c, z_l = calculate_z_score(r), calculate_z_score(c_yoy), calculate_z_score(l)
            score = (z_r * 2.0) + (z_c * 1.0) - (z_l * 1.0)
            
            data.append({
                'Devise': currency, 'Symbol': codes['symbol'],
                'Taux (%)': r.iloc[-1], 'Z-Rate': z_r,
                'CPI (%)': c_yoy.iloc[-1], 'Z-CPI': z_c,
                'Liq/Masse (%)': l_yoy.iloc[-1], 'Z-Liq': z_l,
                'Macro Score': score
            })
        except: continue
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
    m4.metric("Market Mode", "High Vol" if abs(df['Macro Score'].max()) > 3 else "Neutral")

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
            # LE GRAPHIQUE DU CYCLE
            fig_cycle = px.scatter(df, x="Z-CPI", y="Z-Rate", text="Symbol", size=[20]*len(df),
                                   color="Macro Score", color_continuous_scale='RdYlGn',
                                   labels={'Z-CPI': 'Inflation Momentum (Z)', 'Z-Rate': 'Rate Tightness (Z)'},
                                   template='plotly_dark')
            fig_cycle.add_hline(y=0, line_dash="dash", line_color="#444")
            fig_cycle.add_vline(x=0, line_dash="dash", line_color="#444")
            # Annotations des quadrants
            fig_cycle.add_annotation(x=2, y=2, text="HAWKISH", showarrow=False, font=dict(color="green"))
            fig_cycle.add_annotation(x=-2, y=-2, text="DOVISH", showarrow=False, font=dict(color="red"))
            st.plotly_chart(fig_cycle, use_container_width=True)

    with tab2:
        st.header("⚡ Signaux d'Exécution Détaillés")
        # Logique de paires
        hawks = df.iloc[:2]
        doves = df.iloc[-2:]
        
        for _, h in hawks.iterrows():
            for _, d in doves.iterrows():
                pair_name = f"{h['Symbol']}{d['Symbol']}"
                price, z_price = fetch_price(pair_name)
                div_score = h['Macro Score'] - d['Macro Score']
                
                # Couleur du signal
                sig_text = "CONVENTIONNEL"
                if z_price < -1: sig_text = "VALEUR EXTRÊME 🔥"
                elif z_price > 1.5: sig_text = "SUR-ACHAT / ATTENDRE ⚠️"

                with st.container():
                    st.markdown(f"""
                    <div class="opp-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 1.5em; font-weight: bold;">{h['Symbol']} / {d['Symbol']}</span>
                            <span class="hawk-tag">{sig_text}</span>
                        </div>
                        <div style="display: flex; gap: 40px; margin-top: 15px;">
                            <div><span class="text-muted">Divergence Macro</span><br><b>{div_score:.2f}</b></div>
                            <div><span class="text-muted">Prix Actuel</span><br><b>{price}</b></div>
                            <div><span class="text-muted">Z-Score Prix (2y)</span><br><b style="color: {'#238636' if z_price < 0 else '#da3633'}">{z_price}</b></div>
                            <div><span class="text-muted">Confiance</span><br><b>{'Haute' if div_score > 3.5 else 'Moyenne'}</b></div>
                        </div>
                        <div style="margin-top: 15px; border-top: 1px solid #30363d; padding-top: 10px;">
                            <span class="text-muted">LOGIQUE :</span><br>
                            L'achat de <b>{h['Symbol']}</b> est supporté par un différentiel de taux de <b>{(h['Taux (%)']-d['Taux (%)']):.2f}%</b>. 
                            Le prix est actuellement <b>{'sous' if z_price < 0 else 'au-dessus'}</b> de sa moyenne historique de 2 ans.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    with tab3:
        st.subheader("Fundamental Analysis Ledger")
        # Tableau détaillé comme demandé
        styled_df = df.copy()
        st.dataframe(
            styled_df.style.map(lambda x: 'color: #238636; font-weight: bold' if isinstance(x, float) and x > 1.2 else ('color: #da3633; font-weight: bold' if isinstance(x, float) and x < -1.2 else ''), 
                                subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
            .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Liq/Masse (%)', 'Z-Liq', 'Macro Score']),
            use_container_width=True, height=450
        )

else:
    st.error("Échec de la synchronisation des données.")

st.caption(f"Terminal G10 | {datetime.now().strftime('%Y-%m-%d %H:%M')} | Basé sur les cycles de 8 ans.")
