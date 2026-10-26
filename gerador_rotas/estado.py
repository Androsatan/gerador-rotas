import pandas as pd
import streamlit as st

from gerador_rotas.dominio.parser_pedidos import chave_duplicidade


def iniciar_estado():
    if "modulo_ativo" not in st.session_state:
        st.session_state["modulo_ativo"] = "rotas"

    if "df_pedidos" not in st.session_state:
        st.session_state["df_pedidos"] = pd.DataFrame()

    if "df_pedidos_editados" not in st.session_state:
        st.session_state["df_pedidos_editados"] = pd.DataFrame()

    if "versao_editor_pedidos" not in st.session_state:
        st.session_state["versao_editor_pedidos"] = 0

    if "df_rotas_calculadas" not in st.session_state:
        st.session_state["df_rotas_calculadas"] = pd.DataFrame()

    if "df_rotas_editadas" not in st.session_state:
        st.session_state["df_rotas_editadas"] = pd.DataFrame()

    if "versao_editor_rotas" not in st.session_state:
        st.session_state["versao_editor_rotas"] = 0

    if "nomes_rotas_ativas" not in st.session_state:
        st.session_state["nomes_rotas_ativas"] = []

    if "resumo_km_rotas" not in st.session_state:
        st.session_state["resumo_km_rotas"] = {}

    if "coord_partida_atual" not in st.session_state:
        st.session_state["coord_partida_atual"] = None

    if "contador_form" not in st.session_state:
        st.session_state["contador_form"] = 0

    if "avisos_duplicados" not in st.session_state:
        st.session_state["avisos_duplicados"] = []

    if "df_etiquetas" not in st.session_state:
        st.session_state["df_etiquetas"] = pd.DataFrame()

    if "df_etiquetas_editadas" not in st.session_state:
        st.session_state["df_etiquetas_editadas"] = pd.DataFrame()

    if "versao_editor_etiquetas" not in st.session_state:
        st.session_state["versao_editor_etiquetas"] = 0

    if "contador_form_etiquetas" not in st.session_state:
        st.session_state["contador_form_etiquetas"] = 0
    if "geometrias_rotas" not in st.session_state:
        st.session_state["geometrias_rotas"] = {}
    if "avisos_rotas" not in st.session_state:
        st.session_state["avisos_rotas"] = []

    if "df_otimizador" not in st.session_state:
        st.session_state["df_otimizador"] = pd.DataFrame()
    if "df_otimizador_editado" not in st.session_state:
        st.session_state["df_otimizador_editado"] = pd.DataFrame()
    if "versao_editor_otimizador" not in st.session_state:
        st.session_state["versao_editor_otimizador"] = 0
    if "nomes_rotas_otimizador" not in st.session_state:
        st.session_state["nomes_rotas_otimizador"] = []
    if "resumo_km_otimizador" not in st.session_state:
        st.session_state["resumo_km_otimizador"] = {}
    if "coord_partida_otimizador" not in st.session_state:
        st.session_state["coord_partida_otimizador"] = None
    if "geometrias_otimizador" not in st.session_state:
        st.session_state["geometrias_otimizador"] = {}
    if "avisos_otimizador" not in st.session_state:
        st.session_state["avisos_otimizador"] = []
    if "contador_form_otimizador" not in st.session_state:
        st.session_state["contador_form_otimizador"] = 0


def limpar_otimizador():
    """Zera as rotas montadas no otimizador."""
    st.session_state["df_otimizador"] = pd.DataFrame()
    st.session_state["df_otimizador_editado"] = pd.DataFrame()
    st.session_state["versao_editor_otimizador"] = st.session_state.get("versao_editor_otimizador", 0) + 1
    st.session_state["nomes_rotas_otimizador"] = []
    st.session_state["resumo_km_otimizador"] = {}
    st.session_state["coord_partida_otimizador"] = None
    st.session_state["geometrias_otimizador"] = {}
    st.session_state["avisos_otimizador"] = []
    st.session_state["contador_form_otimizador"] = st.session_state.get("contador_form_otimizador", 0) + 1


def atualizar_base_pedidos(novo_df: pd.DataFrame):
    df_limpo = novo_df.reset_index(drop=True).copy()
    st.session_state["df_pedidos"] = df_limpo
    st.session_state["df_pedidos_editados"] = df_limpo.copy()
    st.session_state["versao_editor_pedidos"] = st.session_state.get("versao_editor_pedidos", 0) + 1

def adicionar_pedidos_na_sessao(df_novos: pd.DataFrame):
    if df_novos.empty:
        return 0, []

    df_atual = st.session_state.get("df_pedidos_editados", st.session_state.get("df_pedidos", pd.DataFrame()))
    chaves_existentes = set()

    if not df_atual.empty:
        for _, r in df_atual.iterrows():
            chaves_existentes.add(chave_duplicidade(r["Cliente"], r["Endereco"]))

    linhas_validas = []
    duplicados_ignorados = []

    for _, row in df_novos.iterrows():
        ch = chave_duplicidade(row["Cliente"], row["Endereco"])
        if ch in chaves_existentes:
            duplicados_ignorados.append(f"{row['Cliente']} ({row['Endereco']})")
        else:
            chaves_existentes.add(ch)
            linhas_validas.append(row)

    if linhas_validas:
        df_para_entrar = pd.DataFrame(linhas_validas)
        if df_atual.empty:
            df_combinado = df_para_entrar.reset_index(drop=True)
        else:
            df_combinado = pd.concat([df_atual, df_para_entrar], ignore_index=True)
        atualizar_base_pedidos(df_combinado)

    return len(linhas_validas), duplicados_ignorados

def atualizar_base_etiquetas(novo_df: pd.DataFrame):
    df_limpo = novo_df.reset_index(drop=True).copy()
    st.session_state["df_etiquetas"] = df_limpo
    st.session_state["df_etiquetas_editadas"] = df_limpo.copy()
    st.session_state["versao_editor_etiquetas"] = st.session_state.get("versao_editor_etiquetas", 0) + 1
