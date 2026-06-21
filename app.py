import streamlit as st
import pandas as pd
import json
import glob
import plotly.express as px
import plotly.graph_objects as go
import time
import google.generativeai as genai

# --- CONFIGURAÇÃO DE RESPONSIVIDADE TOTAL ---
st.set_page_config(page_title="Centro de Comando - Chocadeira", layout="wide", page_icon="📈")

def notificar_atualizacao():
    st.toast('A ler ficheiros locais...', icon='⏳')
    time.sleep(0.3)
    st.toast('Painel 100% Atualizado com Sucesso!', icon='✅')

# --- MOTOR DE DADOS: INTELIGÊNCIA DE FICHEIROS MULTIFONTE ---
def carregar_dados():
    arquivos = glob.glob("*.csv")
    
    listas = {
        "app_events": [], "play_installs": [], "play_uninstalls": [], 
        "play_traffic": [], "admob": [], "shopee": []
    }
    
    dados = {
        "app_events": pd.DataFrame(), "play_installs": pd.DataFrame(), 
        "play_uninstalls": pd.DataFrame(), "play_traffic": pd.DataFrame(), 
        "admob": pd.DataFrame(), "shopee": pd.DataFrame()
    }
    
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

    # --- PROCESSAMENTO E SANITIZAÇÃO ---
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
            df_ps = pd.concat(listas[key], ignore_index=True)
            df_ps = df_ps.drop_duplicates(subset=['Data'], keep='last')
            dados[key] = df_ps

    if listas["admob"]:
        df_ad = pd.concat(listas["admob"], ignore_index=True)
        df_ad = df_ad.dropna(how='all').drop_duplicates()
        colunas_dinheiro = [c for c in df_ad.columns if "usd" in str(c).lower() or "ganhos" in str(c).lower() or "ecpm" in str(c).lower()]
        for col in colunas_dinheiro:
            df_ad[col] = pd.to_numeric(df_ad[col].astype(str).str.replace(',', '.'), errors='coerce')
        dados["admob"] = df_ad

    if listas["shopee"]:
        df_sh = pd.concat(listas["shopee"], ignore_index=True)
        df_sh = df_sh.drop_duplicates(subset=['ID do pedido', 'ID do item'], keep='last')
        df_sh['Horário do pedido'] = pd.to_datetime(df_sh['Horário do pedido'], errors='coerce')
        df_sh['Data'] = df_sh['Horário do pedido'].dt.date
        cols_dinheiro = ['Comissão líquida do afiliado(R$)', 'Preço(R$)', 'Valor de Compra(R$)']
        for col in cols_dinheiro:
            if col in df_sh.columns:
                df_sh[col] = pd.to_numeric(df_sh[col].astype(str).str.replace(',', '.'), errors='coerce')
        dados["shopee"] = df_sh

    return dados

# --- EXECUÇÃO DO MOTOR ---
dados = carregar_dados()
df_app = dados["app_events"]
df_original = df_app.copy()

if df_app.empty:
    st.error("⚠️ Nenhum dado detetado. Adicione os ficheiros .csv na pasta.")
    st.stop()
else:
    notificar_atualizacao()

# --- BARRA LATERAL (COM IA E FILTROS) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1004/1004186.png", width=60)
st.sidebar.title("Comandos")

if st.sidebar.button("🔄 Atualizar Fontes", use_container_width=True):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("🧠 Inteligência Artificial")
api_key_gemini = st.sidebar.text_input("Chave API do Google Gemini:", type="password", help="Obtenha a sua chave gratuita no Google AI Studio")

st.sidebar.markdown("---")
st.sidebar.title("⚙️ Filtros Globais")
min_date, max_date = df_app['timestamp'].min().date(), df_app['timestamp'].max().date()
date_range = st.sidebar.date_input("Período Analisado (Eventos)", [min_date, max_date])
eventos = st.sidebar.multiselect("🎯 Filtrar Evento(s)", df_app['event_name'].dropna().unique(), default=[])
estados = st.sidebar.multiselect("📍 Filtrar por Estado", df_app['region_name'].dropna().sort_values().unique())

if len(date_range) == 2:
    df_app = df_app[(df_app['timestamp'].dt.date >= date_range[0]) & (df_app['timestamp'].dt.date <= date_range[1])]
if eventos:
    df_app = df_app[df_app['event_name'].isin(eventos)]
if estados:
    df_app = df_app[df_app['region_name'].isin(estados)]

# --- CONFIGURAÇÃO DAS 4 ABAS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🐣 Produto & Engajamento", 
    "🚀 Aquisição & Play Store", 
    "💰 Monetização (AdMob)", 
    "🛍️ E-commerce Afiliado (Shopee)"
])

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
    media_geral_eclosao = df_eclosao['taxa_eclosao'].mean() if not df_eclosao.empty else 0
    sessoes = df_app.groupby('session_id')['timestamp'].agg(['min', 'max'])
    sessoes['duracao'] = (sessoes['max'] - sessoes['min']).dt.total_seconds() / 60.0
    media_sessao = sessoes[sessoes['duracao'] > 0]['duracao'].mean()
    hora_pico = df_app['hora'].value_counts().idxmax() if not df_app.empty else 0
    
    kpi1.metric("Usuários Únicos", total_users)
    kpi2.metric("Conversão Premium", f"{taxa_prem:.1f}%")
    kpi3.metric("Média de Eclosão 🐣", f"{media_geral_eclosao:.1f}%" if media_geral_eclosao > 0 else "N/A")
    kpi4.metric("Duração Sessão ⏱️", f"{media_sessao:.1f} min" if pd.notna(media_sessao) else "N/A")
    kpi5.metric("Pico de Acesso", f"{hora_pico}h")

    # --- NOVO: MOTOR DE CIÊNCIA DE DADOS COM IA (GEMINI) ---
    st.markdown("---")
    st.header("🤖 Cientista de Dados Virtual (IA)")
    
    # Prepara os dados para enviar para a IA
    receita_admob = dados["admob"]['Ganhos estimados (USD)'].sum() if not dados["admob"].empty else 0
    vendas_shopee = dados["shopee"]['Comissão líquida do afiliado(R$)'].sum() if not dados["shopee"].empty else 0
    
    pacote_dados_ia = f"""
    - Usuários Ativos: {total_users}
    - Taxa Média de Eclosão: {media_geral_eclosao:.1f}%
    - Tempo Médio de Uso Diário: {media_sessao:.1f} minutos
    - Conversão Premium: {taxa_prem:.1f}%
    - Faturamento AdMob: ${receita_admob:.2f} USD
    - Faturamento Shopee Afiliados: R$ {vendas_shopee:.2f}
    - Hora de Pico: {hora_pico}h
    """

    if st.button("🧠 Gerar Relatório de Decisões com IA", type="primary"):
        if not api_key_gemini:
            st.error("⚠️ Por favor, insira a sua Chave API do Google Gemini na barra lateral primeiro.")
        else:
            with st.spinner('A IA está a analisar os seus dados cruzados de Aplicação, Play Store, AdMob e Shopee...'):
                try:
                    genai.configure(api_key=api_key_gemini)
                    # Busca automaticamente qual modelo está liberado para a sua chave
                    modelo_liberado = None
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            modelo_liberado = m.name
                            break
                    
                    if not modelo_liberado:
                        st.error("A sua chave API é válida, mas não tem permissão ativa para modelos de texto. Verifique no Google AI Studio.")
                        st.stop()
                        
                    model = genai.GenerativeModel(modelo_liberado)
                    prompt = f"""Atue como um Analista de Dados e Especialista em Crescimento de Aplicativos.
                    Analise os dados reais da aplicação 'Chocadeira Eficiente' (nicho de agricultura/pecuária):
                    {pacote_dados_ia}
                    
                    Escreva um relatório curto, direto ao ponto, estruturado em Markdown com 3 seções:
                    1. 🚨 **Diagnóstico Principal:** O que estes números dizem sobre a saúde do app.
                    2. 💡 **Oportunidade de Receita:** Uma recomendação prática cruzando AdMob/Shopee com o uso.
                    3. 📈 **Ação Imediata (Produto):** Uma melhoria sugerida para retenção baseada no tempo de sessão ou conversão premium.
                    Fale diretamente com o criador do app num tom encorajador e profissional.
                    """
                    resposta_ia = model.generate_content(prompt)
                    st.success("Análise concluída!")
                    st.markdown(resposta_ia.text)
                except Exception as e:
                    st.error(f"Erro ao comunicar com a IA: {e}")

    st.markdown("---")
    
    # --- GRÁFICOS BLINDADOS (TRY/EXCEPT) ---
    st.subheader("🏆 Classificação e Marcas")
    col_rank1, col_rank2 = st.columns([2, 1])
    with col_rank1:
        contagem_uso = df_app['chocadeira_limpa_ranking'].value_counts().reset_index()
        contagem_uso.columns = ['Modelo Específico', 'Total de Usos']
        df_fin_raw = df_app[df_app['event_name'] == 'finalizou_incubacao'].dropna(subset=['taxa_eclosao'])
        medias_eclosao_raw = df_fin_raw.groupby('chocadeira_limpa_ranking')['taxa_eclosao'].mean().reset_index()
        medias_eclosao_raw.columns = ['Modelo Específico', 'Taxa Média de Eclosão (%)']
        ranking_completo = pd.merge(contagem_uso, medias_eclosao_raw, on='Modelo Específico', how='left').head(15)
        st.dataframe(ranking_completo, column_config={"Taxa Média de Eclosão (%)": st.column_config.NumberColumn(format="%.1f%%")}, use_container_width=True, hide_index=True)
        
    with col_rank2:
        try:
            df_choc_pie = df_app[df_app['chocadeira_padronizada'] != 'Não Informada']['chocadeira_padronizada'].value_counts().reset_index()
            df_choc_pie.columns = ['Modelo', 'Quantidade']
            if not df_choc_pie.empty:
                fig_pizza = px.pie(df_choc_pie, names='Modelo', values='Quantidade', hole=0.4, template="plotly_white")
                st.plotly_chart(fig_pizza, use_container_width=True)
            else:
                st.info("Sem dados suficientes para o gráfico de pizza.")
        except: st.info("Filtro atual bloqueou a renderização deste gráfico.")

    st.markdown("---")
    st.subheader("Visualizações Gráficas Complementares")
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.markdown("**📅 Evolução de Acessos no Tempo**")
        try:
            df_tempo = df_app.groupby(['data_curta']).size().reset_index(name='Eventos')
            if not df_tempo.empty:
                fig_linha = px.line(df_tempo, x='data_curta', y='Eventos', markers=True, template="plotly_white")
                st.plotly_chart(fig_linha, use_container_width=True)
            else: st.info("Sem dados temporais.")
        except: pass
        
    with col_g2:
        st.markdown("**🏆 Desempenho por Marca Unificada**")
        try:
            if not df_eclosao.empty:
                df_agrupado = df_eclosao.groupby('chocadeira_padronizada', as_index=False)['taxa_eclosao'].mean()
                df_agrupado = df_agrupado[df_agrupado['chocadeira_padronizada'] != 'Não Informada'].sort_values('taxa_eclosao', ascending=False)
                if not df_agrupado.empty:
                    df_agrupado['taxa_txt'] = df_agrupado['taxa_eclosao'].apply(lambda x: f"{x:.1f}%")
                    fig_bar = px.bar(df_agrupado, x='chocadeira_padronizada', y='taxa_eclosao', text='taxa_txt', color='chocadeira_padronizada', template='plotly_white')
                    st.plotly_chart(fig_bar, use_container_width=True)
                else: st.info("Sem marcas unificadas para eclosão.")
            else: st.info("Filtre o evento finalizou_incubacao.")
        except: pass

# ==========================================
# TAB 2: AQUISIÇÃO E PLAY STORE
# ==========================================
with tab2:
    st.header("Funil de Marketing e Retenção")
    if dados["play_installs"].empty or dados["play_uninstalls"].empty:
        st.warning("⚠️ Arquivos da Play Store não detetados.")
    else:
        df_in, df_out = dados["play_installs"], dados["play_uninstalls"]
        col_in_br = [c for c in df_in.columns if "Brasil" in c][0]
        col_out_br = [c for c in df_out.columns if "Brasil" in c][0]
        k1, k2, k3 = st.columns(3)
        k1.metric("⬇ Novas Instalações", int(df_in[col_in_br].sum()))
        k2.metric("🗑 Desinstalações", int(df_out[col_out_br].sum()))
        k3.metric("🚀 Crescimento Líquido", int(df_in[col_in_br].sum() - df_out[col_out_br].sum()))
        
        try:
            df_in['Data_Limpa'] = df_in['Data'].str.split(',').str[0]
            fig_balanco = go.Figure()
            fig_balanco.add_trace(go.Bar(x=df_in['Data_Limpa'], y=df_in[col_in_br], name="Instalações", marker_color='#2ca02c'))
            fig_balanco.add_trace(go.Bar(x=df_in['Data_Limpa'], y=-df_out[col_out_br], name="Desinstalações", marker_color='#d62728'))
            fig_balanco.update_layout(barmode='relative', title="Balanço Diário", template="plotly_white")
            st.plotly_chart(fig_balanco, use_container_width=True)
        except: pass

# ==========================================
# TAB 3: MONETIZAÇÃO (ADMOB)
# ==========================================
with tab3:
    st.header("Receita e Assinaturas (AdMob + Premium)")
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("👑 Assinantes Premium", assinantes)
    col_m2.metric("📈 Taxa de Conversão Premium", f"{taxa_prem:.1f}%")
    
    if not dados["admob"].empty:
        df_ad = dados["admob"]
        col_m3.metric("💵 Receita AdMob (USD)", f"${df_ad['Ganhos estimados (USD)'].sum():.2f}")
        ca, cb = st.columns(2)
        ca.info(f"**Total de Impressões:** {df_ad['Impressões'].sum():,.0f}")
        cb.info(f"**eCPM Médio:** ${df_ad['eCPM observado (USD)'].mean():.2f}")
    else: st.warning("⚠️ O relatório do AdMob não pôde ser renderizado financeiramente.")

# ==========================================
# TAB 4: E-COMMERCE AFILIADO (SHOPEE)
# ==========================================
with tab4:
    st.header("🛒 Gestão de E-commerce e Afiliados (Shopee)")
    if dados["shopee"].empty:
        st.warning("⚠️ O arquivo da Shopee (AffiliateCommissionReport) não foi encontrado.")
    else:
        df_sh = dados["shopee"]
        df_concluidos = df_sh[df_sh['Status do Pedido'] == 'Concluído']
        df_cancelados = df_sh[df_sh['Status do Pedido'] == 'Cancelado']
        
        c_sh1, c_sh2, c_sh3, c_sh4 = st.columns(4)
        c_sh1.metric("Comissão Líquida (R$)", f"R$ {df_concluidos['Comissão líquida do afiliado(R$)'].sum():.2f}")
        c_sh2.metric("Vendas Geradas (R$)", f"R$ {df_concluidos['Valor de Compra(R$)'].sum():.2f}")
        c_sh3.metric("Pedidos Concluídos", len(df_concluidos))
        c_sh4.metric("Taxa de Cancelamento", f"{(len(df_cancelados) / len(df_sh) * 100) if len(df_sh) > 0 else 0:.1f}%", delta_color="inverse")
        
        st.markdown("---")
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            st.subheader("🔥 Top Produtos Vendidos")
            top_produtos = df_concluidos.groupby('Nome do Item').agg(Vendas=('Qtd', 'sum'), Comissao_Total=('Comissão líquida do afiliado(R$)', 'sum')).reset_index().sort_values(by='Vendas', ascending=False).head(10)
            st.dataframe(top_produtos, column_config={"Comissao_Total": st.column_config.NumberColumn("Sua Comissão (R$)", format="R$ %.2f")}, use_container_width=True, hide_index=True)
            
        with col_s2:
            st.subheader("📈 Evolução Diária de Comissões")
            try:
                comissao_diaria = df_concluidos.groupby('Data')['Comissão líquida do afiliado(R$)'].sum().reset_index()
                if not comissao_diaria.empty:
                    fig_shopee = px.line(comissao_diaria, x='Data', y='Comissão líquida do afiliado(R$)', markers=True, template="plotly_white")
                    fig_shopee.update_traces(line_color="#ff7f0e")
                    st.plotly_chart(fig_shopee, use_container_width=True)
            except: pass
