import streamlit as st
import pandas as pd
import json
import glob
import plotly.express as px
import plotly.graph_objects as go
import time
from google import genai # <--- NOVA BIBLIOTECA OFICIAL DO GOOGLE

# --- CONFIGURAÇÃO DE RESPONSIVIDADE TOTAL ---
st.set_page_config(page_title="Centro de Comando - Chocadeira", layout="wide", page_icon="📈")

def notificar_atualizacao():
    st.toast('A ler ficheiros locais...', icon='⏳')
    time.sleep(0.3)
    st.toast('Painel 100% Atualizado com Sucesso!', icon='✅')

# --- DICIONÁRIO DE COORDENADAS PARA O MAPA DO BRASIL ---
COORDENADAS_ESTADOS = {
    'Acre': [-9.02, -70.81], 'Alagoas': [-9.53, -36.75], 'Amapá': [1.41, -51.77],
    'Amazonas': [-3.47, -65.10], 'Bahia': [-12.96, -38.51], 'Ceará': [-3.71, -38.54],
    'Distrito Federal': [-15.83, -47.86], 'Espírito Santo': [-19.19, -40.34],
    'Goiás': [-16.64, -49.31], 'Maranhão': [-2.55, -44.30], 'Mato Grosso': [-12.64, -55.42],
    'Mato Grosso do Sul': [-20.51, -54.54], 'Minas Gerais': [-18.10, -44.38],
    'Pará': [-5.53, -52.29], 'Paraíba': [-7.06, -35.55], 'Paraná': [-24.89, -51.55],
    'Pernambuco': [-8.28, -35.07], 'Piauí': [-8.28, -43.68], 'Rio de Janeiro': [-22.84, -43.15],
    'Rio Grande do Norte': [-5.22, -36.52], 'Rio Grande do Sul': [-30.01, -51.22],
    'Rondônia': [-10.83, -63.34], 'Roraima': [1.99, -61.33], 'Santa Catarina': [-27.33, -49.44],
    'São Paulo': [-23.55, -46.64], 'Sergipe': [-10.90, -37.07], 'Tocantins': [-10.25, -48.25]
}

# --- MOTOR DE DADOS ---
def carregar_dados():
    arquivos = glob.glob("*.csv")
    listas = {"app_events": [], "play_installs": [], "play_uninstalls": [], "play_traffic": [], "admob": [], "shopee": []}
    dados = {k: pd.DataFrame() for k in listas.keys()}
    
    for arq in arquivos:
        nome_min = arq.lower()
        if "affiliate" in nome_min or "shopee" in nome_min:
            try:
                df_temp = pd.read_csv(arq)
                if "Comissão líquida do afiliado(R$)" in df_temp.columns: listas["shopee"].append(df_temp)
            except: pass
        elif "admob" in nome_min or "ganhos" in nome_min:
            sucesso = False
            for codificacao in ['utf-8', 'utf-16', 'latin-1', 'cp1252']:
                for separador in ['\t', ',', ';']:
                    try:
                        df_temp = pd.read_csv(arq, sep=separador, encoding=codificacao)
                        cols = [str(c).lower() for c in df_temp.columns]
                        if any("ganhos" in c or "ecpm" in c for c in cols):
                            listas["admob"].append(df_temp)
                            sucesso = True
                            break
                    except: pass
                if sucesso: break
        elif "todos os países" in nome_min or "origens de tráfego" in nome_min:
            try:
                df_temp = pd.read_csv(arq)
                cols = " ".join(df_temp.columns).lower()
                if "aquisição" in cols and "todos os eventos" in cols: listas["play_installs"].append(df_temp)
                elif "perda" in cols: listas["play_uninstalls"].append(df_temp)
                elif "origens de tráfego" in cols: listas["play_traffic"].append(df_temp)
            except: pass
        elif "análise" not in nome_min:
            try:
                df_temp = pd.read_csv(arq)
                if 'event_name' in df_temp.columns: listas["app_events"].append(df_temp)
            except: pass

    if listas["app_events"]:
        df_app = pd.concat(listas["app_events"], ignore_index=True)
        df_app = df_app.drop_duplicates(subset=['timestamp', 'user_id', 'session_id', 'event_name'], keep='last')
        
        def extrair(json_str, chave):
            try: return json.loads(json_str).get(chave, None)
            except: return None

        df_app['timestamp'] = pd.to_datetime(df_app['timestamp'])
        df_app['data_curta'] = df_app['timestamp'].dt.date
        df_app['hora'] = df_app['timestamp'].dt.hour
        dias_pt = {0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'}
        df_app['dia_semana'] = df_app['timestamp'].dt.dayofweek.map(dias_pt)
        df_app['dia_semana'] = pd.Categorical(df_app['dia_semana'], categories=list(dias_pt.values()), ordered=True)

        df_app['chocadeira_nome_raw'] = df_app['string_props'].apply(lambda x: extrair(x, 'chocadeira_nome'))
        df_app['especie_ave'] = df_app['string_props'].apply(lambda x: extrair(x, 'especie_ave'))
        df_app['is_premium_bool'] = df_app['string_props'].apply(lambda x: str(extrair(x, 'usuario_premium')).lower() == 'sim')
        df_app['taxa_eclosao'] = pd.to_numeric(df_app['numeric_props'].apply(lambda x: extrair(x, 'taxa_eclosao_percentual')), errors='coerce')
        df_app.loc[(df_app['taxa_eclosao'] < 0) | (df_app['taxa_eclosao'] > 100), 'taxa_eclosao'] = None
        
        def padronizar(nome):
            if pd.isna(nome) or str(nome).strip() == "": return "Não Informada"
            n = str(nome).strip().upper()
            if "ISOPOR" in n or "CASEIRA" in n: return "Isopor / Caseira"
            if "INCHOC" in n or "ENCHOC" in n: return "Inchoc"
            if "RURAL" in n or "RUAL" in n: return "Rural"
            if "CHOCAAVES" in n or "CHOCA" in n: return "Chocaaves"
            if "ECLODIR" in n or "ECLO" in n: return "Eclodir"
            return "Outras"
            
        def limpar_nome_ranking(nome):
            if pd.isna(nome) or str(nome).strip() == "": return "Não Informada"
            n = str(nome).upper().replace("CHOCADEIRA", "").strip()
            return "Genérica" if n == "" else n

        df_app['chocadeira_padronizada'] = df_app['chocadeira_nome_raw'].apply(padronizar)
        df_app['chocadeira_limpa_ranking'] = df_app['chocadeira_nome_raw'].apply(limpar_nome_ranking)
        dados["app_events"] = df_app

    for key in ["play_installs", "play_uninstalls", "play_traffic"]:
        if listas[key]:
            dados[key] = pd.concat(listas[key], ignore_index=True).drop_duplicates(subset=['Data'], keep='last')

    if listas["admob"]:
        df_ad = pd.concat(listas["admob"], ignore_index=True).dropna(how='all').drop_duplicates()
        cols_dinheiro = [c for c in df_ad.columns if "usd" in str(c).lower() or "ganhos" in str(c).lower() or "ecpm" in str(c).lower()]
        for col in cols_dinheiro: df_ad[col] = pd.to_numeric(df_ad[col].astype(str).str.replace(',', '.'), errors='coerce')
        dados["admob"] = df_ad

    if listas["shopee"]:
        df_sh = pd.concat(listas["shopee"], ignore_index=True).drop_duplicates(subset=['ID do pedido', 'ID do item'], keep='last')
        df_sh['Horário do pedido'] = pd.to_datetime(df_sh['Horário do pedido'], errors='coerce')
        df_sh['Data'] = df_sh['Horário do pedido'].dt.date
        for col in ['Comissão líquida do afiliado(R$)', 'Preço(R$)', 'Valor de Compra(R$)']:
            if col in df_sh.columns: df_sh[col] = pd.to_numeric(df_sh[col].astype(str).str.replace(',', '.'), errors='coerce')
        dados["shopee"] = df_sh

    return dados

dados = carregar_dados()
df_app = dados["app_events"]
df_original = df_app.copy()

if df_app.empty:
    st.error("⚠️ Nenhum dado detetado. Adicione os ficheiros .csv na pasta.")
    st.stop()
else:
    notificar_atualizacao()

# --- BARRA LATERAL ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1004/1004186.png", width=60)
if st.sidebar.button("🔄 Atualizar Fontes", width="stretch"): st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("🧠 Inteligência Artificial")
api_key_gemini = st.sidebar.text_input("Chave API do Google Gemini:", type="password", help="Cole sua chave aqui")

st.sidebar.markdown("---")
st.sidebar.title("⚙️ Filtros Globais")
min_date, max_date = df_app['timestamp'].min().date(), df_app['timestamp'].max().date()
date_range = st.sidebar.date_input("Período Analisado", [min_date, max_date])
eventos = st.sidebar.multiselect("🎯 Filtrar Evento(s)", df_app['event_name'].dropna().unique(), default=[])
estados = st.sidebar.multiselect("📍 Filtrar por Estado", df_app['region_name'].dropna().sort_values().unique())

if len(date_range) == 2: df_app = df_app[(df_app['timestamp'].dt.date >= date_range[0]) & (df_app['timestamp'].dt.date <= date_range[1])]
if eventos: df_app = df_app[df_app['event_name'].isin(eventos)]
if estados: df_app = df_app[df_app['region_name'].isin(estados)]

tab1, tab2, tab3, tab4 = st.tabs(["🐣 Produto & Engajamento", "🚀 Aquisição & Play Store", "💰 Monetização (AdMob)", "🛍️ E-commerce (Shopee)"])

# ==========================================
# TAB 1: PRODUTO E ENGAJAMENTO
# ==========================================
with tab1:
    st.header("Análise Avançada de Produto e Comportamento")
    
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    total_users = df_app['user_id'].nunique()
    assinantes = df_app[df_app['is_premium_bool'] == 1]['user_id'].nunique()
    taxa_prem = (assinantes / total_users * 100) if total_users > 0 else 0
    df_eclosao = df_app[df_app['event_name'] == 'finalizou_incubacao'].dropna(subset=['taxa_eclosao'])
    media_eclosao = df_eclosao['taxa_eclosao'].mean() if not df_eclosao.empty else 0
    sessoes = df_app.groupby('session_id')['timestamp'].agg(['min', 'max'])
    sessoes['dur'] = (sessoes['max'] - sessoes['min']).dt.total_seconds() / 60.0
    media_sessao = sessoes[sessoes['dur'] > 0]['dur'].mean()
    hora_pico = df_app['hora'].value_counts().idxmax() if not df_app.empty else 0
    
    kpi1.metric("Usuários Únicos", total_users)
    kpi2.metric("Conversão Premium", f"{taxa_prem:.1f}%")
    kpi3.metric("Média Eclosão", f"{media_eclosao:.1f}%" if media_eclosao > 0 else "N/A")
    kpi4.metric("Duração Sessão", f"{media_sessao:.1f} min" if pd.notna(media_sessao) else "N/A")
    kpi5.metric("Pico de Acesso", f"{hora_pico}h")

    # --- NOVA API DO GOOGLE GEMINI ---
    st.markdown("---")
    if st.button("🧠 Gerar Relatório de Decisões com IA", type="primary", width="stretch"):
        if not api_key_gemini:
            st.error("⚠️ Insira a Chave API na barra lateral primeiro.")
        else:
            with st.spinner('A IA está a analisar...'):
                try:
                    client = genai.Client(api_key=api_key_gemini)
                    rec_admob = dados["admob"]['Ganhos estimados (USD)'].sum() if not dados["admob"].empty else 0
                    rec_shopee = dados["shopee"]['Comissão líquida do afiliado(R$)'].sum() if not dados["shopee"].empty else 0
                    prompt = f"Analise dados do app Chocadeira Eficiente: {total_users} users, Eclosão {media_eclosao:.1f}%, Sessão {media_sessao:.1f}m, Premium {taxa_prem:.1f}%, AdMob ${rec_admob}, Shopee R${rec_shopee}. Dê um diagnóstico e uma ação prática em Markdown."
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash', # Usa o modelo mais leve e robusto da nova biblioteca
                        contents=prompt
                    )
                    st.markdown(response.text)
                except Exception as e: st.error(f"Erro IA: {e}")

    st.markdown("---")
    
    # --- MAPA INTERATIVO CORRIGIDO (scatter_map) ---
    st.subheader("🗺️ Densidade Geográfica de Utilização")
    try:
        df_mapa = df_app['region_name'].dropna().value_counts().reset_index()
        df_mapa.columns = ['Estado', 'Acessos']
        df_mapa['Estado_Limpo'] = df_mapa['Estado'].str.strip().str.title()
        df_mapa['Lat'] = df_mapa['Estado_Limpo'].map(lambda x: COORDENADAS_ESTADOS.get(x, [None, None])[0])
        df_mapa['Lon'] = df_mapa['Estado_Limpo'].map(lambda x: COORDENADAS_ESTADOS.get(x, [None, None])[1])
        df_mapa_limpo = df_mapa.dropna(subset=['Lat', 'Lon'])
        
        if not df_mapa_limpo.empty:
            fig_mapa = px.scatter_map( # Comando Plotly atualizado!
                df_mapa_limpo, 
                lat="Lat", lon="Lon", 
                size="Acessos", color="Acessos",
                hover_name="Estado", 
                hover_data={"Lat":False, "Lon":False, "Acessos":True},
                color_continuous_scale=px.colors.sequential.Plasma, 
                size_max=50, 
                zoom=3, center={"lat": -15.78, "lon": -47.92}, 
                map_style="carto-positron" # Parâmetro atualizado!
            )
            fig_mapa.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_mapa, width="stretch") # Streamlit container width atualizado!
        else:
            st.info("Nenhum estado válido encontrado para desenhar o mapa.")
    except Exception as e:
        st.warning(f"Não foi possível renderizar o mapa: {e}")

    st.markdown("---")

    col_rank1, col_rank2 = st.columns([2, 1])
    with col_rank1:
        st.subheader("🏆 Classificação e Marcas")
        contagem = df_app['chocadeira_limpa_ranking'].value_counts().reset_index()
        contagem.columns = ['Modelo Específico', 'Total']
        df_fin = df_app[df_app['event_name'] == 'finalizou_incubacao'].dropna(subset=['taxa_eclosao'])
        medias = df_fin.groupby('chocadeira_limpa_ranking')['taxa_eclosao'].mean().reset_index()
        medias.columns = ['Modelo Específico', 'Eclosão (%)']
        st.dataframe(pd.merge(contagem, medias, on='Modelo Específico', how='left').head(15), column_config={"Eclosão (%)": st.column_config.NumberColumn(format="%.1f%%")}, width="stretch", hide_index=True)
        
    with col_rank2:
        st.subheader("📊 Participação")
        try:
            df_choc_pie = df_app[df_app['chocadeira_padronizada'] != 'Não Informada']['chocadeira_padronizada'].value_counts().reset_index()
            df_choc_pie.columns = ['Modelo', 'Quantidade']
            st.plotly_chart(px.pie(df_choc_pie, names='Modelo', values='Quantidade', hole=0.4), width="stretch")
        except: pass

    st.markdown("---")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("**📅 Evolução de Acessos**")
        try:
            df_t = df_app.groupby(['data_curta']).size().reset_index(name='Eventos')
            st.plotly_chart(px.line(df_t, x='data_curta', y='Eventos', markers=True), width="stretch")
        except: pass
    with col_g2:
        st.markdown("**🔥 Mapa de Calor Semanal**")
        try:
            df_h = df_app.groupby(['dia_semana', 'hora']).size().reset_index(name='Acessos')
            st.plotly_chart(px.density_heatmap(df_h, x="hora", y="dia_semana", z="Acessos", text_auto=True), width="stretch")
        except: pass

# ==========================================
# TAB 2: AQUISIÇÃO E PLAY STORE
# ==========================================
with tab2:
    st.header("Funil de Marketing e Retenção")
    if dados["play_installs"].empty or dados["play_uninstalls"].empty: st.warning("⚠️ Sem arquivos da Play Store.")
    else:
        df_in, df_out = dados["play_installs"], dados["play_uninstalls"]
        c_br = [c for c in df_in.columns if "Brasil" in c][0]
        c_out_br = [c for c in df_out.columns if "Brasil" in c][0]
        k1, k2, k3 = st.columns(3)
        k1.metric("⬇ Instalações", int(df_in[c_br].sum()))
        k2.metric("🗑 Desinstalações", int(df_out[c_out_br].sum()))
        k3.metric("🚀 Líquido", int(df_in[c_br].sum() - df_out[c_out_br].sum()))
        try:
            df_in['Dia'] = df_in['Data'].str.split(',').str[0]
            fig_balanco = go.Figure()
            fig_balanco.add_trace(go.Bar(x=df_in['Dia'], y=df_in[c_br], name="Instalações", marker_color='green'))
            fig_balanco.add_trace(go.Bar(x=df_in['Dia'], y=-df_out[c_out_br], name="Desinstalações", marker_color='red'))
            fig_balanco.update_layout(barmode='relative', title="Balanço Diário")
            st.plotly_chart(fig_balanco, width="stretch")
        except: pass

# ==========================================
# TAB 3: MONETIZAÇÃO (ADMOB)
# ==========================================
with tab3:
    st.header("Receita e Assinaturas (AdMob + Premium)")
    if not dados["admob"].empty:
        df_ad = dados["admob"]
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Receita (USD)", f"${df_ad['Ganhos estimados (USD)'].sum():.2f}")
        c2.metric("👁️ Impressões", f"{df_ad['Impressões'].sum():,.0f}")
        c3.metric("💰 eCPM Médio", f"${df_ad['eCPM observado (USD)'].mean():.2f}")
    else: st.warning("⚠️ Relatório AdMob não encontrado.")

# ==========================================
# TAB 4: SHOPEE AFILIADOS
# ==========================================
with tab4:
    st.header("🛒 E-commerce e Afiliados (Shopee)")
    if not dados["shopee"].empty:
        df_sh = dados["shopee"]
        df_c = df_sh[df_sh['Status do Pedido'] == 'Concluído']
        c1, c2, c3 = st.columns(3)
        c1.metric("Comissão Líquida", f"R$ {df_c['Comissão líquida do afiliado(R$)'].sum():.2f}")
        c2.metric("Vendas Geradas", f"R$ {df_c['Valor de Compra(R$)'].sum():.2f}")
        c3.metric("Pedidos Concluídos", len(df_c))
        
        c_g1, c_g2 = st.columns([2, 1])
        with c_g1:
            st.subheader("🔥 Top Produtos")
            st.dataframe(df_c.groupby('Nome do Item').agg(Vendas=('Qtd', 'sum'), Comissao=('Comissão líquida do afiliado(R$)', 'sum')).reset_index().sort_values(by='Vendas', ascending=False).head(10), width="stretch", hide_index=True)
        with c_g2:
            st.subheader("🛍️ Status")
            st.plotly_chart(px.pie(df_sh['Status do Pedido'].value_counts().reset_index(), names='Status do Pedido', values='count', hole=0.4), width="stretch")
    else: st.warning("⚠️ Relatório Shopee não encontrado.")
