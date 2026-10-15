import streamlit as st
import pandas as pd
import requests
import re
import json
import os
import unicodedata
from urllib.parse import quote

st.set_page_config(page_title="Gerador de Rotas", page_icon="🛵", layout="wide")

# CSS reforçado: impede "..." dentro dos botões e empilha colunas em janelas reduzidas
st.markdown("""
<style>
/* Botão externo */
div.stButton > button,
div.stFormSubmitButton > button {
    white-space: normal !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    height: auto !important;
    min-height: 2.8rem !important;
    padding: 0.5rem 0.6rem !important;
}

/* Elementos internos do botão (onde o Streamlit aplica o "...") */
div.stButton > button *,
div.stFormSubmitButton > button * {
    white-space: normal !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    text-overflow: clip !important;
    overflow: visible !important;
    line-height: 1.25 !important;
    text-align: center !important;
}

/* Quebra de linha automática na caixa de prévia de código */
pre, code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

/* Quando a janela estiver reduzida, empilha as colunas para os botões ficarem largos */
@media (max-width: 980px) {
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    div[data-testid="column"],
    div[data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)

ARQUIVO_CONFIG = "config_rotas.json"

CIDADES_RMBH = [
    "belo horizonte", "sabara", "nova lima", "contagem", "betim",
    "santa luzia", "ribeirao das neves", "ibirite", "vespasiano",
    "lagoa santa", "pedro leopoldo", "brumadinho", "caete", "sarzedo",
    "mario campos", "sao jose da lapa", "confins", "esmeraldas", "raposos"
]

PREFIXOS_RUA = (
    "rua ", "r. ", "r ", "av ", "av. ", "avenida ", "alameda ", "al. ",
    "praca ", "praça ", "travessa ", "tv. ", "beco ", "rodovia ", "estrada ", "anel "
)


# ================= FUNÇÕES DE CONFIGURAÇÃO (SALVAR PRODUTOS) =================
def carregar_config():
    padrao = {
        "ponto_partida": "Bairro Maria Goretti, Belo Horizonte, MG",
        "local_1": "skunk, orange amnesia, silver, wolf, super sheep",
        "local_2": "ice, pak, paki, dry, pod, colombia gold, uva",
        "local_3": "@, md, lsd",
        "local_4": "pren"
    }
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
                padrao.update(dados)
        except Exception:
            pass
    return padrao


def salvar_config(dados: dict):
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


# ================= FUNÇÕES DE EXTRAÇÃO E ENDEREÇO =================
def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def eh_linha_produto(linha: str, palavras_produtos: list) -> bool:
    linha_limpa = linha.strip().lower()
    if not linha_limpa:
        return False
    if re.match(r"^\d+\s*([a-zA-Z@%]+)?(\s+|$)", linha_limpa):
        return True
    linha_sem_acento = remover_acentos(linha_limpa)
    for prod in palavras_produtos:
        if prod and prod in linha_sem_acento:
            return True
    return False


def eh_linha_endereco(linha: str) -> bool:
    linha_limpa = remover_acentos(linha.strip().lower())
    if not linha_limpa:
        return False
    if re.match(r"^\d+", linha_limpa):
        return False
    if linha_limpa.startswith(PREFIXOS_RUA):
        return True
    if re.search(r"[a-zA-Z]{3,}\s*,?\s*\d+", linha_limpa):
        return True
    return False


def calcular_pacotes(itens_pedido: list, locais_dict: dict) -> int:
    locais_acionados = set()
    texto_itens = remover_acentos(" ".join(itens_pedido).lower())

    for nome_local, lista_prods in locais_dict.items():
        for prod in lista_prods:
            prod_limpo = remover_acentos(prod.strip().lower())
            if prod_limpo and prod_limpo in texto_itens:
                locais_acionados.add(nome_local)

    return max(1, len(locais_acionados))


def separar_componentes_endereco(endereco_bruto: str):
    end_limpo = endereco_bruto.strip()
    end_norm = remover_acentos(end_limpo.lower())

    cidade_detectada = "Belo Horizonte"
    mapa_nomes_cidades = {
        "sabara": "Sabará",
        "ribeirao das neves": "Ribeirão das Neves",
        "ibirite": "Ibirité",
        "caete": "Caeté",
        "mario campos": "Mário Campos",
        "sao jose da lapa": "São José da Lapa"
    }
    for cid in CIDADES_RMBH:
        if re.search(rf"\b{cid}\b", end_norm):
            cidade_detectada = mapa_nomes_cidades.get(cid, cid.title())
            break

    match_num = re.search(r"(?:,\s*|\s+)(\d+)\b(.*)$", end_limpo)
    if match_num:
        rua = end_limpo[:match_num.start()].strip(" ,.-")
        numero = match_num.group(1).strip()
        resto = match_num.group(2).strip(" ,.-")
    else:
        rua = end_limpo
        numero = ""
        resto = ""

    return rua, numero, resto, cidade_detectada


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_endereco_completo(endereco_bruto: str):
    if not str(endereco_bruto).strip():
        return "", "❌ NÃO ENCONTRADO - CORRIGIR", None, None

    rua, numero, bairro_dica, cidade = separar_componentes_endereco(str(endereco_bruto))
    rua_sem_prefixo = re.sub(
        r"^(rua|r\.|r|avenida|av\.|av|alameda|al\.|praca|praça|travessa|beco)\s+",
        "",
        rua,
        flags=re.IGNORECASE
    ).strip()

    cep_encontrado = ""
    logradouro_oficial = ""
    bairro_oficial = ""
    cidade_oficial = cidade
    lat, lon = None, None

    # 1. Consulta ViaCEP
    if len(rua_sem_prefixo) >= 3:
        try:
            url_viacep = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade))}/{quote(remover_acentos(rua_sem_prefixo))}/json/"
            resp = requests.get(url_viacep, timeout=5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and len(dados) > 0:
                    escolhido = dados[0]
                    if bairro_dica:
                        dica_norm = remover_acentos(bairro_dica.lower())
                        for item in dados:
                            b_item = remover_acentos(item.get("bairro", "").lower())
                            if b_item and (b_item in dica_norm or dica_norm in b_item):
                                escolhido = item
                                break
                    logradouro_oficial = escolhido.get("logradouro", "")
                    bairro_oficial = escolhido.get("bairro", "")
                    cidade_oficial = escolhido.get("localidade", cidade)
                    cep_encontrado = escolhido.get("cep", "")
        except Exception:
            pass

    # 2. Consulta ArcGIS Geocoder
    try:
        query_geo = f"{rua}, {numero}, {bairro_dica}, {cidade}, Minas Gerais, Brasil"
        url_arcgis = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(query_geo)}&outFields=StName,StType,AddNum,Nbrhd,City,Postal&maxLocations=1&f=json"
        )
        resp_geo = requests.get(url_arcgis, timeout=5)
        if resp_geo.status_code == 200:
            cands = resp_geo.json().get("candidates", [])
            if cands and cands[0].get("score", 0) >= 75:
                melhor = cands[0]
                lat = melhor["location"]["y"]
                lon = melhor["location"]["x"]
                atrib = melhor.get("attributes", {})

                if not bairro_oficial and atrib.get("Nbrhd"):
                    bairro_oficial = atrib.get("Nbrhd")
                if atrib.get("City"):
                    cidade_oficial = atrib.get("City")
                if not cep_encontrado and atrib.get("Postal"):
                    cep_raw = re.sub(r"\D", "", atrib.get("Postal", ""))
                    if len(cep_raw) == 8:
                        cep_encontrado = f"{cep_raw[:5]}-{cep_raw[5:]}"
    except Exception:
        pass

    # 3. Segunda tentativa ViaCEP caso a cidade seja da RMBH
    if not cep_encontrado and cidade_oficial and len(rua_sem_prefixo) >= 3:
        try:
            url_viacep2 = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade_oficial))}/{quote(remover_acentos(rua_sem_prefixo))}/json/"
            resp2 = requests.get(url_viacep2, timeout=5)
            if resp2.status_code == 200:
                dados2 = resp2.json()
                if isinstance(dados2, list) and len(dados2) > 0:
                    escolhido2 = dados2[0]
                    logradouro_oficial = logradouro_oficial or escolhido2.get("logradouro", "")
                    bairro_oficial = bairro_oficial or escolhido2.get("bairro", "")
                    cep_encontrado = escolhido2.get("cep", "")
        except Exception:
            pass

    if not logradouro_oficial and not lat:
        return endereco_bruto, "❌ NÃO ENCONTRADO - CORRIGIR", None, None

    nome_via_final = logradouro_oficial if logradouro_oficial else rua.title()
    bairro_final = bairro_oficial if bairro_oficial else (bairro_dica.title() if bairro_dica else "Bairro não identificado")

    partes_end = [nome_via_final]
    if numero:
        partes_end.append(numero)
    if bairro_final:
        partes_end.append(bairro_final)
    partes_end.append(cidade_oficial)
    if cep_encontrado:
        partes_end.append(cep_encontrado)

    endereco_padronizado = ", ".join(partes_end)

    if not cep_encontrado or bairro_final == "Bairro não identificado":
        status = "⚠️ INCOMPLETO (CONFERIR BAIRRO/CEP)"
    else:
        status = "✅ OK"

    return endereco_padronizado, status, lat, lon


def extrair_pedidos_brutos(texto_bruto: str, locais_dict: dict, vendedor_padrao: str = ""):
    todas_palavras_prod = [p.strip().lower() for lista in locais_dict.values() for p in lista if p.strip()]
    linhas = [l.strip() for l in texto_bruto.splitlines() if l.strip()]

    pedidos = []
    nome_atual = None
    itens_atuais = []

    for linha in linhas:
        if nome_atual is None:
            nome_atual = linha.upper().strip()
            itens_atuais = []
        else:
            if eh_linha_produto(linha, todas_palavras_prod):
                itens_atuais.append(linha)
            elif eh_linha_endereco(linha):
                qtd_pct = calcular_pacotes(itens_atuais, locais_dict)
                end_completo, status, lat, lon = buscar_endereco_completo(linha)
                pedidos.append({
                    "Excluir": False,
                    "Status": status,
                    "Cliente": nome_atual,
                    "Vendedor": vendedor_padrao.upper().strip(),
                    "Pacotes": qtd_pct,
                    "Observacao": "",
                    "Posicao": "Normal",
                    "Endereco": end_completo,
                    "Itens_Lidos": ", ".join(itens_atuais),
                    "Lat": lat,
                    "Lon": lon
                })
                nome_atual = None
                itens_atuais = []
            else:
                itens_atuais.append(linha)

    return pd.DataFrame(pedidos)


def adicionar_pedidos_na_sessao(df_novos: pd.DataFrame):
    if df_novos.empty:
        return
    if "df_pedidos" not in st.session_state or st.session_state["df_pedidos"].empty:
        st.session_state["df_pedidos"] = df_novos
    else:
        st.session_state["df_pedidos"] = pd.concat(
            [st.session_state["df_pedidos"], df_novos],
            ignore_index=True
        )


def montar_linha_cliente(row) -> str:
    partes = [str(row["Cliente"]).strip().upper()]

    vend = str(row.get("Vendedor", "")).strip().upper()
    if vend and vend != "NONE" and vend != "NAN":
        partes.append(f"[{vend}]")

    try:
        pct = int(row.get("Pacotes", 1))
    except (ValueError, TypeError):
        pct = 1
    if pct > 1:
        partes.append(f"({pct}PCT)")

    obs = str(row.get("Observacao", "")).strip().upper()
    if obs and obs != "NONE" and obs != "NAN":
        partes.append(f"({obs})")

    return " ".join(partes)


# ================= INICIALIZAÇÃO =================
config_salva = carregar_config()

if "df_pedidos" not in st.session_state:
    st.session_state["df_pedidos"] = pd.DataFrame()

st.title("🛵 Gerador de Rotas")

# --- BARRA LATERAL: CONFIGURAÇÕES SALVÁVEIS ---
with st.sidebar:
    st.header("📍 Ponto de Partida")
    ponto_partida = st.text_input(
        "Endereço de saída das rotas:",
        value=config_salva.get("ponto_partida", "Bairro Maria Goretti, Belo Horizonte, MG")
    )

    st.divider()
    st.header("📦 Locais (Pacotes)")
    st.caption("Separe os produtos por vírgula e clique em Salvar abaixo.")

    local_1 = st.text_area("Local de Saída 1:", value=config_salva.get("local_1", ""), height=70)
    local_2 = st.text_area("Local de Saída 2:", value=config_salva.get("local_2", ""), height=70)
    local_3 = st.text_area("Local de Saída 3:", value=config_salva.get("local_3", ""), height=70)
    local_4 = st.text_area("Local de Saída 4:", value=config_salva.get("local_4", ""), height=70)

    if st.button("💾 Salvar Produtos/Partida", type="primary", use_container_width=True):
        salvar_config({
            "ponto_partida": ponto_partida,
            "local_1": local_1,
            "local_2": local_2,
            "local_3": local_3,
            "local_4": local_4
        })
        st.success("✅ Produtos/Partida salvos com sucesso!")

    locais_config = {
        "Local 1": [p for p in local_1.split(",") if p.strip()],
        "Local 2": [p for p in local_2.split(",") if p.strip()],
        "Local 3": [p for p in local_3.split(",") if p.strip()],
        "Local 4": [p for p in local_4.split(",") if p.strip()],
    }

# --- PASSO 1: ADICIONAR PEDIDOS (EM LOTE OU 1 POR 1) ---
st.subheader("1️⃣ Adicionar Pedidos")

aba_lote, aba_individual = st.tabs([
    "📋 Colar Vários Pedidos",
    "➕ Adicionar 1 Pedido"
])

with aba_lote:
    texto_pedidos = st.text_area(
        "Cole os pedidos abaixo (eles serão adicionados à lista):",
        height=200,
        placeholder=(
            "Exemplo:\ngustavo ramos\n5g amendoim\n1 quebra noz\nAv flor de seda 1030, lindeia\n\n"
            "Bernardo\n1g granola\n1g amendoa\nRua Contria, 1380, Grajau"
        )
    )
    vendedor_lote = st.text_input(
        "Sigla do Vendedor `[ ]` para os pedidos acima:",
        placeholder="Ex: 2T, VG, NK"
    )
    if st.button("🔍 Adicionar à Lista", type="primary", use_container_width=True):
        if texto_pedidos.strip():
            with st.spinner("Extraindo pedidos e buscando CEPs e Bairros..."):
                df_extraidos = extrair_pedidos_brutos(texto_pedidos, locais_config, vendedor_lote)
                if not df_extraidos.empty:
                    adicionar_pedidos_na_sessao(df_extraidos)
                    st.success(f"✅ {len(df_extraidos)} pedido(s) adicionado(s) à lista!")
                else:
                    st.warning("⚠️ Não foi possível identificar um endereço válido no texto colado.")
        else:
            st.warning("Cole pelo menos um pedido antes de clicar em extrair.")

with aba_individual:
    with st.form("form_adicionar_um", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            nome_ind = st.text_input("Nome do Cliente *", placeholder="Ex: ROX")
            end_ind = st.text_input("Endereço *", placeholder="Ex: Rua Itaipu 760")
            itens_ind = st.text_input("Produtos do Pedido (Opcional - calcula pacotes sozinho)", placeholder="Ex: 1g granola, 5g amendoim")
        with col_f2:
            vend_ind = st.text_input("Sigla do Vendedor [ ] (Opcional)", placeholder="Ex: 2L")
            pct_manual = st.number_input("Nº de Pacotes (se não digitar produtos)", min_value=1, max_value=10, value=1, step=1)
            obs_ind = st.text_input("Observação ( ) (Opcional)", placeholder="Ex: TROCA")
            pos_ind = st.selectbox("Posição na Rota", ["Normal", "PRIMEIRO", "ÚLTIMO"])

        submitted_ind = st.form_submit_button("➕ Adicionar Cliente à Lista", type="primary", use_container_width=True)
        if submitted_ind:
            if not nome_ind.strip() or not end_ind.strip():
                st.error("⚠️ Preencha pelo menos o Nome do Cliente e o Endereço.")
            else:
                with st.spinner("Buscando CEP e Bairro do endereço..."):
                    end_comp, status_ind, lat_ind, lon_ind = buscar_endereco_completo(end_ind)
                    if itens_ind.strip():
                        qtd_pct_ind = calcular_pacotes([itens_ind], locais_config)
                    else:
                        qtd_pct_ind = pct_manual

                    novo_df = pd.DataFrame([{
                        "Excluir": False,
                        "Status": status_ind,
                        "Cliente": nome_ind.strip().upper(),
                        "Vendedor": vend_ind.strip().upper(),
                        "Pacotes": qtd_pct_ind,
                        "Observacao": obs_ind.strip().upper(),
                        "Posicao": pos_ind,
                        "Endereco": end_comp,
                        "Itens_Lidos": itens_ind.strip(),
                        "Lat": lat_ind,
                        "Lon": lon_ind
                    }])
                    adicionar_pedidos_na_sessao(novo_df)
                    st.success(f"✅ Cliente {nome_ind.upper()} adicionado à lista!")

# --- PASSO 2: TABELA DE CONFERÊNCIA, EDIÇÃO E EXCLUSÃO ---
if not st.session_state["df_pedidos"].empty:
    st.divider()
    st.subheader(f"2️⃣ Conferência dos Pedidos ({len(st.session_state['df_pedidos'])} na lista)")

    df_atual = st.session_state["df_pedidos"].copy()
    if "Excluir" not in df_atual.columns:
        df_atual.insert(0, "Excluir", False)

    problemas = df_atual[df_atual["Status"] != "✅ OK"]
    if not problemas.empty:
        st.warning(
            f"⚠️ **{len(problemas)} endereço(s) precisam da sua atenção!** "
            "Edite o endereço na tabela abaixo e clique em **'🔄 Atualizar Endereços'**."
        )
    else:
        st.success(f"✅ Todos os {len(df_atual)} endereços foram localizados com Bairro e CEP!")

    df_editado = st.data_editor(
        df_atual,
        use_container_width=True,
        hide_index=True,
        column_order=["Excluir", "Status", "Cliente", "Vendedor", "Pacotes", "Observacao", "Posicao", "Endereco", "Itens_Lidos"],
        column_config={
            "Excluir": st.column_config.CheckboxColumn("🗑️", width="small", default=False),
            "Status": st.column_config.TextColumn("Status", disabled=True, width="medium"),
            "Cliente": st.column_config.TextColumn("Cliente (CAIXA ALTA)", width="medium"),
            "Vendedor": st.column_config.TextColumn("Vendedor [ ]", width="small"),
            "Pacotes": st.column_config.NumberColumn("Pacotes", min_value=1, max_value=10, step=1, width="small"),
            "Observacao": st.column_config.TextColumn("Obs ( )", width="small"),
            "Posicao": st.column_config.SelectboxColumn(
                "Posição",
                options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                default="Normal",
                width="small"
            ),
            "Endereco": st.column_config.TextColumn("Endereço Completo (Editável)", width="large"),
            "Itens_Lidos": st.column_config.TextColumn("Itens Lidos", disabled=True, width="medium"),
        }
    )

    df_editado["Cliente"] = df_editado["Cliente"].astype(str).str.upper()
    st.session_state["df_pedidos"] = df_editado

    # Botões de ação responsivos
    col_acao1, col_acao2, col_acao3 = st.columns(3)

    with col_acao1:
        if st.button("🔄 Atualizar Endereços", use_container_width=True):
            with st.spinner("Atualizando endereços..."):
                for idx, row in df_editado.iterrows():
                    end_novo, novo_status, lat, lon = buscar_endereco_completo(row["Endereco"])
                    df_editado.at[idx, "Endereco"] = end_novo
                    df_editado.at[idx, "Status"] = novo_status
                    df_editado.at[idx, "Lat"] = lat
                    df_editado.at[idx, "Lon"] = lon
                st.session_state["df_pedidos"] = df_editado
                st.rerun()

    with col_acao2:
        qtd_marcados = int(df_editado["Excluir"].sum()) if "Excluir" in df_editado.columns else 0
        texto_btn_excluir = f"🗑️ Excluir Selecionados ({qtd_marcados})" if qtd_marcados > 0 else "🗑️ Excluir Marcados"
        if st.button(texto_btn_excluir, use_container_width=True):
            if qtd_marcados > 0:
                df_restante = df_editado[~df_editado["Excluir"]].copy()
                df_restante["Excluir"] = False
                st.session_state["df_pedidos"] = df_restante.reset_index(drop=True)
                st.rerun()
            else:
                st.toast("Marque a caixinha '🗑️' na tabela ao lado do cliente que deseja remover.")

    with col_acao3:
        if st.button("🧹 Limpar Lista", use_container_width=True):
            st.session_state["df_pedidos"] = pd.DataFrame()
            st.rerun()

    with st.expander("👀 Ver prévia dos pedidos", expanded=True):
        linhas_previa = []
        for _, row in df_editado.iterrows():
            linhas_previa.append(f"{row['Endereco']}\n{montar_linha_cliente(row)}")
        st.code("\n\n".join(linhas_previa), language="text", wrap_lines=True)
