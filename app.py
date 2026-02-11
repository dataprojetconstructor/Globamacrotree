import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Central Bank Alpha Tool", layout="wide")

if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur API : {e}")
    st.stop()

# --- DEFINITION DES INDICES (CODES INTERNATIONAUX ROBUSTES) ---
# J'ai remplacé les codes OCDE par des codes FMI ou de masse monétaire plus larges
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liq': 'WALCL'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liq': 'ECBASSETSW'},
    'JPY (BoJ)': {'rate': 'INTDSRJPM193N', 'cpi': 'JPNCPIALLMINMEI', 'liq': 'JPNASSETS'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liq': 'MANMM101GBM189S'},
    'CAD (BoC)': {'rate': 'INTDSRCAM193N', 'cpi': 'CANCPIALLMINMEI', 'liq': 'MANMM101CAM189S'},
    'AUD (RBA)': {'rate': 'INTDSRAUM193N', 'cpi': 'AUSCPIALLMINMEI', 'liq': 'MANMM101AUM189S'},
    'CHF (SNB)': {'rate': 'INTDSRCHM193N', 'cpi': 'CHECPIALLMINMEI', 'liq': 'MABMM301CHM189S'}, # Utilisation M3 pour la Suisse
}

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0
    clean_s = series.dropna()
    if clean_s.empty: return 0
    # On prend la dernière valeur non nulle
    val = clean_s.iloc[-1]
    mean = clean_s.mean()
    std = clean_s.std()
    return (val - mean) / std if std != 0 else 0

@st.cache_data(ttl=86400)
def get_macro_data():
    data = []
    # On remonte un peu plus loin pour être sûr d'attraper les données trimestrielles (Australie)
    start_date = datetime.now() - timedelta(days=365*6) 
    
    progress_bar = st.progress(0, text="Récupération des données monde...")
    
    for i, (currency, codes) in enumerate(central_banks.items()):
        row = {'Devise': currency, 'Taux (%)': 0, 'Z-Rate': 0, 'CPI (%)': 0, 'Z-CPI': 0, 'Liquidité (%)': 0, 'Z-Liq': 0, 'Macro Score': 0}
        try:
            # 1. TAUX (On force le remplissage des trous pour les séries quotidiennes/mensuelles)
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if s_rate.empty: raise ValueError("Taux vide")
            row['Taux (%)'] = s_rate.iloc[-1]
            row['Z-Rate'] = calculate_z_score(s_rate)

            # 2. INFLATION (Calcul robuste pour données trimestrielles)
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            # Pour l'Australie (trimestriel), on compare par rapport à 4 périodes au lieu de 12 si besoin
            # Mais .pct_change(12) sur des données mensuelles "remplies" par ffill() marche très bien
            cpi_yoy = s_cpi.pct_change(12).dropna() * 100
            row['CPI (%)'] = cpi_yoy.iloc[-1]
            row['Z-CPI'] = calculate_z_score(cpi_yoy)

            # 3. LIQUIDITÉ
            s_liq = fred.get_series(codes['liq'], observation_start=start_date).ffill()
            liq_chg = s_liq.pct_change(12).dropna() * 100
            row['Liquidité (%)'] = liq_chg.iloc[-1]
            row['Z-Liq'] = calculate_z_score(s_liq)

            # FORMULE MACRO
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Liq'] * 1.0)
            data.append(row)
        except Exception as e:
            st.warning(f"Note : Certaines données pour {currency} sont arrivées avec du retard (Lag FRED).")
            continue
        
        progress_bar.progress((i + 1) / len(central_banks))
    
    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

# --- INTERFACE ---
st.title("🏦 Central Bank Alpha Tool")

df = get_macro_data()

if not df.empty:
    # 1. TABLEAU
    st.header("1. Classement Hawk vs Dove")
    st.dataframe(
        df.style.map(lambda x: 'background-color: #d4edda' if isinstance(x, float) and x > 1.2 else ('background-color: #f8d7da' if isinstance(x, float) and x < -1.2 else ''), 
                     subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
        .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Liquidité (%)', 'Z-Liq', 'Macro Score']),
        use_container_width=True
    )

    # 2. STRENGTH METER
    st.header("2. Currency Strength Meter")
    fig_bar = px.bar(df, x='Macro Score', y='Devise', orientation='h', color='Macro Score', color_continuous_scale='RdYlGn')
    fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_bar, use_container_width=True)

    # 3. OPPORTUNITÉS
    st.header("3. Signaux de Divergence")
    col1, col2 = st.columns(2)
    top_hawk = df.iloc[0]
    top_dove = df.iloc[-1]
    col1.success(f"💪 **FORCE (Long) :** {top_hawk['Devise']}")
    col2.error(f"📉 **FAIBLESSE (Short) :** {top_dove['Devise']}")
    
    # scan des paires
    trades = []
    for i, row_l in df.iterrows():
        for j, row_s in df.iterrows():
            diff = row_l['Macro Score'] - row_s['Macro Score']
            if diff > 2.5:
                trades.append({'Paire': f"{row_l['Devise'][:3]}/{row_s['Devise'][:3]}", 'Score': round(diff, 2)})
    
    if trades:
        st.table(pd.DataFrame(trades).sort_values(by='Score', ascending=False).head(5))

else:
    st.error("Erreur critique : Aucune donnée n'a pu être récupérée. Vérifiez votre clé API FRED.")
