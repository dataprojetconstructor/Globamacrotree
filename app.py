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
    # Clé de secours pour tests locaux
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur de connexion à la FRED : {e}")
    st.stop()

# --- DEFINITION DES INDICES (Utilisation de Proxies de Liquidité M1/M3) ---
# Si le bilan n'est pas dispo, on utilise la masse monétaire (Money Stock)
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'liquidity': 'WALCL'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'liquidity': 'ECBASSETSW'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'liquidity': 'JPNASSETS'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'liquidity': 'MANMM101GBM189S'}, # M1 UK
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'liquidity': 'MANMM101CAM189S'}, # M1 Canada
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'liquidity': 'MANMM101AUM189S'}, # M1 Australie
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'liquidity': 'CHFCENTRALBANK'},
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
    progress_bar = st.progress(0, text="Analyse des banques centrales en cours...")
    
    for i, (currency, codes) in enumerate(central_banks.items()):
        row = {'Devise': currency, 'Taux (%)': 0, 'Z-Rate': 0, 'CPI (%)': 0, 'Z-CPI': 0, 'Liquidité (%)': 0, 'Z-Liq': 0, 'Macro Score': 0}
        try:
            # 1. TAUX
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if not s_rate.empty:
                row['Taux (%)'] = s_rate.iloc[-1]
                row['Z-Rate'] = calculate_z_score(s_rate)

            # 2. INFLATION (YoY)
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            if not s_cpi.empty:
                cpi_yoy = s_cpi.pct_change(12).dropna() * 100
                row['CPI (%)'] = cpi_yoy.iloc[-1]
                row['Z-CPI'] = calculate_z_score(cpi_yoy)

            # 3. LIQUIDITÉ (Bilan ou Masse Monétaire)
            s_liq = fred.get_series(codes['liquidity'], observation_start=start_date).ffill()
            if not s_liq.empty:
                liq_chg = s_liq.pct_change(12).dropna() * 100
                row['Liquidité (%)'] = liq_chg.iloc[-1]
                row['Z-Liq'] = calculate_z_score(s_liq)

            # FORMULE DU MACRO SCORE
            # Poids : Taux (2.0) + Inflation (1.0) - Liquidité (1.0)
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Liq'] * 1.0)
            data.append(row)
        except:
            continue
        progress_bar.progress((i + 1) / len(central_banks))
    
    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

# --- INTERFACE ---

st.title("🏦 Central Bank Alpha Tool")

with st.expander("ℹ️ Méthodologie : Comment sont calculés les scores ?"):
    st.markdown("""
    Ce tableau de bord analyse la force relative des devises via trois indicateurs clés normalisés par **Z-Score** (écart à la moyenne sur 5 ans) :
    
    1.  **Z-Rate (Taux) :** Poids x2.0. Des taux élevés attirent les capitaux (Carry Trade).
    2.  **Z-CPI (Inflation) :** Poids x1.0. Une inflation forte pousse la banque centrale à être restrictive (Hawkish).
    3.  **Z-Liq (Liquidité) :** Poids -1.0. Mesure le bilan ou la masse monétaire (M1). Si la liquidité augmente, la devise se dévalue.
    
    **Formule :** `(Z_Taux * 2) + (Z_CPI * 1) - (Z_Liq * 1)`
    """)

# Chargement des données
df = get_macro_data()

if not df.empty:
    # --- SECTION 1 : DASHBOARD ---
    st.header("1. Classement Macro Global")
    
    def style_val(val):
        if not isinstance(val, (int, float)): return ''
        if val > 1.2: return 'background-color: #d4edda; color: #155724; font-weight: bold'
        if val < -1.2: return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
        return ''

    st.dataframe(
        df.style.map(style_val, subset=['Z-Rate', 'Z-CPI', 'Z-Liq', 'Macro Score'])
        .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Liquidité (%)', 'Z-Liq', 'Macro Score']),
        use_container_width=True
    )

    st.divider()

    # --- SECTION 2 : CURRENCY STRENGTH METER ---
    st.header("2. Currency Strength Meter")
    
    col_bar, col_info = st.columns([2, 1])
    
    with col_bar:
        # Création du graphique de force relative
        fig_bar = px.bar(
            df, x='Macro Score', y='Devise', orientation='h',
            color='Macro Score',
            color_continuous_scale='RdYlGn',
            title="Puissance Relative des Devises"
        )
        fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)
    
    with col_info:
        st.markdown("""
        **Lecture du Strength Meter :**
        - **Vert (Positif) :** Devises **Hawkish**. Politique restrictive, taux élevés, liquidité contrôlée. Idéal pour l'achat.
        - **Rouge (Négatif) :** Devises **Dovish**. Politique accommodante, taux bas, forte injection de liquidité. Idéal pour la vente.
        """)

    st.divider()

    # --- SECTION 3 : VISUALISATION CYCLIQUE ---
    col_chart, col_sig = st.columns([2, 1])

    with col_chart:
        st.header("3. Carte des Cycles (Taux vs Inflation)")
        fig_scatter = px.scatter(
            df, x="Z-CPI", y="Z-Rate", text="Devise", 
            size=[30]*len(df), color="Macro Score",
            color_continuous_scale="RdYlGn",
            labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux (Z-Score)"},
        )
        fig_scatter.add_hline(y=0, line_dash="dash", line_color="grey")
        fig_scatter.add_vline(x=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_sig:
        st.header("4. Signaux Forex")
        top_hawk = df.iloc[0]
        top_dove = df.iloc[-1]
        
        st.success(f"🔥 **Top ACHAT :** {top_hawk['Devise']}")
        st.error(f"🌊 **Top VENTE :** {top_dove['Devise']}")
        
        spread = top_hawk['Macro Score'] - top_dove['Macro Score']
        st.metric("Potentiel de Divergence", f"{spread:.2f}")
        
        st.info(f"""
        **Paire suggérée :** {top_hawk['Devise'][:3]}/{top_dove['Devise'][:3]}
        
        **Logique :** On achète la devise ayant le meilleur mix (Taux hauts / Liquidité faible) contre celle ayant le moins bon mix.
        """)

    # --- SECTION 4 : GÉNÉRATEUR D'OPPORTUNITÉS ---
    st.divider()
    st.subheader("💡 Opportunités Détectées")
    
    trades = []
    for i, row_l in df.iterrows():
        for j, row_s in df.iterrows():
            diff = row_l['Macro Score'] - row_s['Macro Score']
            if diff > 2.5: # Seuil de divergence forte
                trades.append({
                    'Paire': f"{row_l['Devise'][:3]}/{row_s['Devise'][:3]}",
                    'Position': 'LONG',
                    'Score Spread': round(diff, 2),
                    'Confiance': 'Élevée' if diff > 4 else 'Moyenne'
                })
    
    if trades:
        st.table(pd.DataFrame(trades).sort_values(by='Score Spread', ascending=False))
    else:
        st.write("Aucune divergence majeure détectée pour le moment.")

else:
    st.error("Impossible de récupérer les données depuis la FRED. Vérifiez votre clé API.")

st.caption(f"Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')} | Sources : FRED, OCDE, Banques Centrales")
