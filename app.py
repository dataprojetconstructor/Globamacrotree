import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Central Bank Alpha Tool", layout="wide")

# --- GESTION SÉCURISÉE DE LA CLÉ API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur de connexion à la FRED : {e}")
    st.stop()

# --- DEFINITION DES INDICES ---
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'balance': 'WALCL'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'balance': 'ECBASSETSW'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'balance': 'JPNASSETS'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'balance': None}, 
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'balance': 'CV11269'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'balance': None},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'balance': 'CHFCENTRALBANK'},
}

# --- MOTEUR DE CALCUL ---

def calculate_z_score(series):
    """Normalise la donnée : (Valeur actuelle - Moyenne) / Écart-type"""
    if series is None or len(series) < 10: return 0
    clean_s = series.dropna()
    if clean_s.empty: return 0
    mean = clean_s.mean()
    std = clean_s.std()
    return (clean_s.iloc[-1] - mean) / std if std != 0 else 0

@st.cache_data(ttl=86400)
def get_macro_data():
    data = []
    start_date = datetime.now() - timedelta(days=365*5)
    progress_bar = st.progress(0, text="Extraction des données monétaires...")
    
    for i, (currency, codes) in enumerate(central_banks.items()):
        row = {'Devise': currency, 'Taux (%)': 0, 'Z-Rate': 0, 'CPI (%)': 0, 'Z-CPI': 0, 'Bilan 6M (%)': 0, 'Z-Bilan': 0, 'Macro Score': 0}
        try:
            # Taux
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if not s_rate.empty:
                row['Taux (%)'] = s_rate.iloc[-1]
                row['Z-Rate'] = calculate_z_score(s_rate)
            # Inflation
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            if not s_cpi.empty:
                cpi_yoy = s_cpi.pct_change(12).dropna() * 100
                row['CPI (%)'] = cpi_yoy.iloc[-1]
                row['Z-CPI'] = calculate_z_score(cpi_yoy)
            # Bilan
            if codes['balance']:
                try:
                    s_bs = fred.get_series(codes['balance'], observation_start=start_date).ffill()
                    bs_chg = s_bs.pct_change(26).dropna() * 100
                    row['Bilan 6M (%)'] = bs_chg.iloc[-1]
                    row['Z-Bilan'] = calculate_z_score(bs_chg)
                except: pass

            # Formule du Score : (Rate * 2) + (CPI * 1) - (Bilan * 0.5)
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Bilan'] * 0.5)
            data.append(row)
        except: continue
        progress_bar.progress((i + 1) / len(central_banks))
    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

# --- INTERFACE ---

st.title("🏦 Central Bank Policy Tracker")

# --- SECTION EXPLICATION (Nouveau) ---
with st.expander("ℹ️ Comment fonctionne ce tableau de bord ? (Méthodologie)"):
    st.markdown("""
    Cet outil mesure la **posture relative** des banques centrales pour identifier des opportunités sur le Forex.
    
    ### 1. Les 3 Piliers de l'Analyse
    *   **Taux Directeur (Z-Rate) :** Plus les taux sont élevés par rapport à leur moyenne historique, plus la devise est attractive (Carry Trade).
    *   **Inflation (Z-CPI) :** Une inflation élevée force la banque centrale à rester "Hawkish" (agressive), ce qui soutient la devise.
    *   **Bilan (Z-Bilan) :** Si la banque réduit son bilan (QT), la devise se raréfie et prend de la valeur. Si elle l'augmente (QE/Impression monétaire), la devise s'affaiblit.

    ### 2. Le calcul du Z-Score (Normalisation)
    Pour comparer des banques différentes, nous utilisons le **Z-Score**. 
    *   Il répond à la question : *"La valeur actuelle est-elle exceptionnelle par rapport aux 5 dernières années ?"*
    *   Un score de **+2.0** signifie que la valeur est très élevée historiquement. Un score de **-2.0** signifie qu'elle est historiquement basse.

    ### 3. La Formule du "Macro Score"
    Le score final qui classe les devises est calculé ainsi :
    `Score = (Z_Taux * 2.0) + (Z_Inflation * 1.0) - (Z_Bilan * 0.5)`
    *   On donne **deux fois plus d'importance aux taux** car c'est le moteur principal du Forex.
    *   On **soustrait** le bilan car une expansion du bilan est négative pour la valeur d'une monnaie.
    """)

# --- CHARGEMENT ---
df = get_macro_data()

# --- AFFICHAGE ---
if not df.empty:
    st.header("1. Classement Hawk vs Dove")
    
    def style_val(val):
        if not isinstance(val, (int, float)): return ''
        if val > 1.2: return 'background-color: #d4edda; color: #155724; font-weight: bold'
        if val < -1.2: return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
        return ''

    st.dataframe(
        df.style.map(style_val, subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score'])
        .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Bilan 6M (%)', 'Z-Bilan', 'Macro Score']),
        use_container_width=True
    )

    st.divider()
    
    col_chart, col_sig = st.columns([2, 1])

    with col_chart:
        st.header("2. Carte des Cycles")
        fig = px.scatter(
            df, x="Z-CPI", y="Z-Rate", text="Devise", 
            size=[30]*len(df), color="Macro Score",
            color_continuous_scale="RdYlGn",
            labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux (Z-Score)"},
        )
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        fig.add_vline(x=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, use_container_width=True)

    with col_sig:
        st.header("3. Signaux de Trading")
        top_hawk = df.iloc[0]
        top_dove = df.iloc[-1]
        
        st.success(f"**Devise la plus Forte (Hawk) :** {top_hawk['Devise']}")
        st.error(f"**Devise la plus Faible (Dove) :** {top_dove['Devise']}")
        
        spread = top_hawk['Macro Score'] - top_dove['Macro Score']
        
        st.metric("Potentiel de Divergence", f"{spread:.2f}")
        
        st.write("---")
        st.write("**Logique de Trading :**")
        st.markdown(f"""
        Le signal suggère d'acheter la devise en haut du classement (**{top_hawk['Devise'][:3]}**) 
        et de vendre celle en bas (**{top_dove['Devise'][:3]}**).
        
        *Si le spread est > 2.0, la divergence de politique monétaire est considérée comme majeure.*
        """)

    # SECTION DIVERGENCE
    st.divider()
    st.subheader("💡 Opportunités de Paires Forex")
    trades = []
    for i, row_l in df.iterrows():
        for j, row_s in df.iterrows():
            diff = row_l['Macro Score'] - row_s['Macro Score']
            if diff > 2.5:
                trades.append({
                    'Paire': f"{row_l['Devise'][:3]}/{row_s['Devise'][:3]}",
                    'Action': 'ACHAT (Long)',
                    'Intensité': f"{diff:.2f}",
                    'Raison': "Divergence Politique Monétaire"
                })
    
    if trades:
        st.table(pd.DataFrame(trades).sort_values(by='Intensité', ascending=False))
    else:
        st.write("Aucune divergence forte détectée actuellement.")

else:
    st.error("Données indisponibles. Vérifiez la clé API.")

# Footer
st.caption(f"Données mises à jour le {datetime.now().strftime('%d/%m/%Y')}. Source : St. Louis FRED.")
