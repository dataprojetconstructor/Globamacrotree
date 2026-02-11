import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURATION ET STYLE ---
st.set_page_config(page_title="Global Macro Edge | Central Bank Terminal", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; border-radius: 10px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .hawk-card { border-left: 5px solid #28a745; background-color: #e6ffed; padding: 15px; border-radius: 5px; }
    .dove-card { border-left: 5px solid #dc3545; background-color: #fceaea; padding: 15px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- GESTION API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error("Erreur de connexion API FRED")
    st.stop()

# --- CODES SÉRIES ROBUSTES ---
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL', 'name': 'United States'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW', 'name': 'Euro Area'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS', 'name': 'Japan'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S', 'name': 'United Kingdom'},
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S', 'name': 'Canada'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S', 'name': 'Australia'},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S', 'name': 'Switzerland'},
}

# --- LOGIQUE DE CALCUL ---

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0.0
    clean_s = series.ffill().dropna()
    if clean_s.empty: return 0.0
    return (clean_s.iloc[-1] - clean_s.mean()) / clean_s.std()

@st.cache_data(ttl=86400)
def fetch_all_data():
    data_list = []
    start_date = datetime.now() - timedelta(days=365*6)
    
    for currency, codes in central_banks.items():
        try:
            # Récupération sécurisée
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()

            # Métriques
            cur_rate = s_rate.iloc[-1]
            z_rate = calculate_z_score(s_rate)
            
            cpi_yoy = s_cpi.pct_change(12).dropna() * 100
            cur_cpi = cpi_yoy.iloc[-1]
            z_cpi = calculate_z_score(cpi_yoy)
            
            liq_yoy = s_liq.pct_change(12).dropna() * 100
            cur_liq = liq_yoy.iloc[-1]
            z_liq = calculate_z_score(s_liq)

            # Score composite
            macro_score = (z_rate * 2.0) + (z_cpi * 1.0) - (z_liq * 1.0)

            data_list.append({
                'Devise': currency,
                'Région': codes['name'],
                'Taux (%)': cur_rate,
                'CPI (%)': cur_cpi,
                'Liquidité (%)': cur_liq,
                'Z-Rate': z_rate,
                'Z-CPI': z_cpi,
                'Z-Liq': z_liq,
                'Macro Score': macro_score
            })
        except:
            continue
    return pd.DataFrame(data_list).sort_values(by='Macro Score', ascending=False)

# --- ENGINE START ---
df = fetch_all_data()

# --- HEADER ---
st.title("🏛️ Global Macro Edge")
st.markdown(f"**Terminal de Surveillance des Banques Centrales** | Dernière mise à jour : {datetime.now().strftime('%d %b %Y')}")
st.divider()

# --- TOP KPI CARDS ---
col1, col2, col3, col4 = st.columns(4)
if not df.empty:
    top_hawk = df.iloc[0]
    top_dove = df.iloc[-1]
    
    with col1:
        st.metric("Top Hawkish (Strong)", top_hawk['Devise'], f"{top_hawk['Macro Score']:.2f}")
    with col2:
        st.metric("Top Dovish (Weak)", top_dove['Devise'], f"{top_dove['Macro Score']:.2f}", delta_color="inverse")
    with col3:
        spread = top_hawk['Macro Score'] - top_dove['Macro Score']
        st.metric("Max Divergence", f"{spread:.2f}", "Potential Alpha")
    with col4:
        st.metric("Active Regions", len(df), "G10 Coverage")

# --- MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Dashboard de Force", "🔍 Analyse Détaillée", "⚡ Signaux de Trading"])

with tab1:
    col_a, col_b = st.columns([2, 1])
    
    with col_a:
        st.subheader("Currency Strength Meter")
        fig_strength = px.bar(
            df, x='Macro Score', y='Devise', orientation='h',
            color='Macro Score', color_continuous_scale='RdYlGn',
            template='plotly_white', height=500
        )
        fig_strength.update_layout(showlegend=False, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_strength, use_container_width=True)

    with col_b:
        st.subheader("Positionnement Cyclique")
        fig_scatter = px.scatter(
            df, x="Z-CPI", y="Z-Rate", text="Devise", size=[30]*len(df),
            color="Macro Score", color_continuous_scale='RdYlGn',
            labels={'Z-CPI': 'Inflation Momentum', 'Z-Rate': 'Rate Tightness'}
        )
        fig_scatter.add_hline(y=0, line_dash="dash")
        fig_scatter.add_vline(x=0, line_dash="dash")
        st.plotly_chart(fig_scatter, use_container_width=True)

with tab2:
    st.subheader("Données Fondamentales Comparées")
    # Style dynamique pour le tableau
    formatted_df = df.copy()
    st.dataframe(
        df.style.background_gradient(cmap='RdYlGn', subset=['Macro Score', 'Z-Rate', 'Z-CPI'])
        .format("{:.2f}", subset=['Taux (%)', 'CPI (%)', 'Liquidité (%)', 'Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score']),
        use_container_width=True, height=400
    )
    
    # Analyse textuelle
    st.markdown("### 📝 Analyse de marché")
    for _, row in df.iterrows():
        sentiment = "Restrictif (Hawkish)" if row['Macro Score'] > 0 else "Accommodant (Dovish)"
        with st.expander(f"Analyse approfondie : {row['Devise']}"):
            st.write(f"La banque centrale de **{row['Région']}** affiche un score de **{row['Macro Score']:.2f}**.")
            st.write(f"- **Taux :** Le Z-score de {row['Z-Rate']:.2f} indique que les taux sont {'élevés' if row['Z-Rate']>0 else 'bas'} par rapport à l'historique.")
            st.write(f"- **Inflation :** À {row['CPI (%)']:.2f}%, l'inflation est {'une pression majeure' if row['Z-CPI']>1 else 'sous contrôle'}.")
            st.write(f"- **Liquidité :** La variation de la masse monétaire ({row['Liquidité (%)']:.2f}%) suggère une {'contraction' if row['Z-Liq']<0 else 'expansion'} des liquidités.")

with tab3:
    st.subheader("Opportunités de Paires Forex")
    
    col_long, col_short = st.columns(2)
    
    with col_long:
        st.markdown('<div class="hawk-card"><h4>🚀 OPPORTUNITÉS LONG</h4></div>', unsafe_allow_html=True)
        for i in range(min(2, len(df))):
            row = df.iloc[i]
            st.write(f"**{row['Devise']}** : Score de force élevé ({row['Macro Score']:.2f}). Supporté par un différentiel de taux positif.")

    with col_short:
        st.markdown('<div class="dove-card"><h4>📉 OPPORTUNITÉS SHORT</h4></div>', unsafe_allow_html=True)
        for i in range(1, min(3, len(df))):
            row = df.iloc[-i]
            st.write(f"**{row['Devise']}** : Score de faiblesse ({row['Macro Score']:.2f}). Pression baissière due à la politique monétaire.")

    st.divider()
    
    # Générateur de paires
    st.markdown("### 💱 Top Paires de Divergence")
    paires = []
    for i in range(len(df)):
        for j in range(len(df)-1, i, -1):
            s_long = df.iloc[i]
            s_short = df.iloc[j]
            diff = s_long['Macro Score'] - s_short['Macro Score']
            if diff > 2.5:
                paires.append({
                    'Paire': f"{s_long['Devise'][:3]} / {s_short['Devise'][:3]}",
                    'Intensité': diff,
                    'Confiance': "Élevée 🔥" if diff > 4 else "Modérée ⚖️"
                })
    
    if paires:
        pair_df = pd.DataFrame(paires).sort_values(by='Intensité', ascending=False)
        st.table(pair_df)
    else:
        st.info("Aucune divergence majeure détectée pour le moment.")

# --- FOOTER ---
st.divider()
st.caption("Avertissement : Les calculs sont basés sur des données historiques normalisées (Z-Score). Ce terminal est un outil d'aide à la décision et ne constitue pas un conseil en investissement.")
