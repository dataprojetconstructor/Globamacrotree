import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURATION ET STYLE ---
st.set_page_config(page_title="Global Macro Edge | Central Bank Terminal", layout="wide")

# CSS pour améliorer l'esthétique
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; }
    .hawk-card { border-left: 5px solid #28a745; background-color: #f0fff4; padding: 20px; border-radius: 10px; margin-bottom: 10px; }
    .dove-card { border-left: 5px solid #dc3545; background-color: #fff5f5; padding: 20px; border-radius: 10px; margin-bottom: 10px; }
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
    st.error("Erreur de connexion API FRED. Vérifiez votre clé.")
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
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()

            cur_rate = s_rate.iloc[-1]
            z_rate = calculate_z_score(s_rate)
            
            cpi_yoy = s_cpi.pct_change(12).dropna() * 100
            cur_cpi = cpi_yoy.iloc[-1] if not cpi_yoy.empty else 0
            z_cpi = calculate_z_score(cpi_yoy)
            
            liq_yoy = s_liq.pct_change(12).dropna() * 100
            cur_liq = liq_yoy.iloc[-1] if not liq_yoy.empty else 0
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

df = fetch_all_data()

# --- INTERFACE ---
st.title("🏛️ Global Macro Edge")
st.markdown(f"**Terminal de Surveillance des Banques Centrales** | {datetime.now().strftime('%d %b %Y')}")
st.divider()

if not df.empty:
    # KPI Top bar
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top Hawkish", df.iloc[0]['Devise'], f"{df.iloc[0]['Macro Score']:.2f}")
    c2.metric("Top Dovish", df.iloc[-1]['Devise'], f"{df.iloc[-1]['Macro Score']:.2f}", delta_color="inverse")
    c3.metric("Max Spread", f"{(df.iloc[0]['Macro Score'] - df.iloc[-1]['Macro Score']):.2f}")
    c4.metric("Assets Analyzed", len(df))

    # Onglets
    tab1, tab2, tab3 = st.tabs(["📊 Performance Relative", "🔍 Fondamentaux", "⚡ Signaux"])

    with tab1:
        col_a, col_b = st.columns([2, 1])
        with col_a:
            fig_bar = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score',
                             color_continuous_scale='RdYlGn', title="Force de la Politique Monétaire")
            st.plotly_chart(fig_bar, use_container_width=True)
        with col_b:
            fig_scat = px.scatter(df, x="Z-CPI", y="Z-Rate", text="Devise", size=[20]*len(df),
                                  color="Macro Score", color_continuous_scale='RdYlGn', title="Cycle Taux/Inflation")
            st.plotly_chart(fig_scat, use_container_width=True)

    with tab2:
        st.subheader("Tableau de Bord des Banques Centrales")
        
        # Style alternatif sans besoin strict de matplotlib si possible
        # Mais avec matplotlib dans requirements.txt, ceci fonctionnera parfaitement :
        try:
            st.dataframe(
                df.style.background_gradient(cmap='RdYlGn', subset=['Macro Score', 'Z-Rate', 'Z-CPI'])
                .format("{:.2f}", subset=['Taux (%)', 'CPI (%)', 'Liquidité (%)', 'Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score']),
                use_container_width=True, height=450
            )
        except:
            # Fallback simple si matplotlib échoue
            st.dataframe(df, use_container_width=True)

    with tab3:
        st.subheader("Stratégies de Divergence")
        c_long, c_short = st.columns(2)
        
        with c_long:
            st.markdown(f'<div class="hawk-card"><b>🚀 ACHAT (Strongest)</b><br><h3>{df.iloc[0]["Devise"]}</h3>Macro Score: {df.iloc[0]["Macro Score"]:.2f}</div>', unsafe_allow_html=True)
            st.write("La politique est restrictive. Les taux sont élevés par rapport à l'inflation, ce qui attire les flux de capitaux.")

        with c_short:
            st.markdown(f'<div class="dove-card"><b>📉 VENTE (Weakest)</b><br><h3>{df.iloc[-1]["Devise"]}</h3>Macro Score: {df.iloc[-1]["Macro Score"]:.2f}</div>', unsafe_allow_html=True)
            st.write("La politique est accommodante. L'injection de liquidité ou les taux bas dévaluent la monnaie.")

        st.divider()
        st.markdown("### 💱 Paires Forex à surveiller")
        pairs = []
        for i in range(len(df)):
            for j in range(len(df)-1, i, -1):
                diff = df.iloc[i]['Macro Score'] - df.iloc[j]['Macro Score']
                if diff > 2.5:
                    pairs.append({'Paire': f"{df.iloc[i]['Devise'][:3]} / {df.iloc[j]['Devise'][:3]}", 'Divergence': diff, 'Signal': 'ACHAT 🔥' if diff > 4 else 'OBSERVATION ⚖️'})
        
        if pairs:
            st.table(pd.DataFrame(pairs).sort_values(by='Divergence', ascending=False))

else:
    st.warning("Aucune donnée disponible. Vérifiez la connexion FRED.")

st.caption("Données normalisées (Z-Score) basées sur un historique de 5 ans. Source : St. Louis FED.")
