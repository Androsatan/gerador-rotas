import streamlit as st
import pandas as pd
import requests
import re
import json
import os
import unicodedata
from difflib import SequenceMatcher
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

# Palavras ignoradas ao separar produtos compostos (ex: "castanha do para" -> "castanha", "para")
STOPWORDS_PRODUTOS = {"de", "do", "da", "dos", "das", "com", "sem", "e", "ou", "a", "o", "un", "pct", "gr", "kg", "ml"}


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


# ================= FUNÇÕES DE EXTRAÇÃO, PRODUTOS E ENDEREÇO =================
def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def extrair_palavras_item(texto_linha: str) -> list:
    """Extrai as palavras úteis de uma linha de pedido, removendo quantidades como '5g', '10', '2x'."""
    limpo = remover_acentos(texto_linha.lower())
    # Remove números colados em unidades no início ou meio (ex: 5g, 100gr, 2x, 10)
    limpo = re.sub(r"\b\d+\s*(g|gr|kg|ml|l|un|pct|x)?\b", " ", limpo)
    palavras = re.findall(r"[a-z0-9@]+", limpo)
    return [p for p in palavras if p not in STOPWORDS_PRODUTOS and len(p) >= 2]


def similaridade_palavras(palavra_cliente: str, palavra_cadastro: str) -> float:
    """
    Calcula o quão parecida é a palavra escrita pelo cliente com a palavra cadastrada no Local.
    Retorna de 0.0 a 1.0 (aceita abreviações como 'amendo' -> 'amendoa' e erros de digitação).
    """
    if palavra_cliente == palavra_cadastro:
        return 1.0

    # Caso uma seja abreviação/radical da outra (ex: 'amendo' e 'amendoa', 'pren' e 'prensado')
    menor, maior = sorted([palavra_cliente, palavra_cadastro], key=len)
    if len(menor) >= 3 and maior.startswith(menor):
        return 0.90

    # Caso tenha erro de digitação (ex: 'amedoa' vs 'amendoa', 'skank' vs 'skunk', 'colobia' vs 'colombia')
    if len(palavra_cliente) >= 3 and len(palavra_cadastro) >= 3:
        ratio = SequenceMatcher(None, palavra_cliente, palavra_cadastro).ratio()
        return ratio

    return 0.0


def identificar_locais_dos_itens(itens_pedido: list, locais_dict: dict):
    """
    Analisa todas as linhas de produtos do pedido (mesmo com erros de digitação ou nomes parciais)
    e retorna (quantidade_de_pacotes, lista_de_locais_acionados).
    """
    locais_acionados = set()

    # Pré-processa o vocabulário de cada local de saída
    vocab_locais = {}
    for nome_local, lista_prods in locais_dict.items():
        frases_e_palavras = []
        for prod in lista_prods:
            prod_norm = remover_acentos(prod.strip().lower())
            if not prod_norm:
                continue
            # Palavras-chave individuais do produto (ex: 'castanha do para' -> ['castanha', 'para'])
            palavras_prod = [
                p for p in re.findall(r"[a-z0-9@]+", prod_norm)
                if p not in STOPWORDS_PRODUTOS
            ]
            frases_e_palavras.append((prod_norm, palavras_prod))
        vocab_locais[nome_local] = frases_e_palavras

    for linha in itens_pedido:
        linha_norm = remover_acentos(linha.strip().lower())
        if not linha_norm:
            continue

        # 1. Verifica símbolos especiais ou frase exata (ex: '@' em '10@')
        local_encontrado_direto = False
        for nome_local, lista_fp in vocab_locais.items():
            for frase_completa, _ in lista_fp:
                if frase_completa in ("@", "md", "lsd") and re.search(rf"(?:^|\d|\s){re.escape(frase_completa)}(?:$|\s)", linha_norm):
                    locais_acionados.add(nome_local)
                    local_encontrado_direto = True
                elif len(frase_completa) >= 3 and frase_completa in linha_norm:
                    locais_acionados.add(nome_local)
                    local_encontrado_direto = True

        if local_encontrado_direto:
            continue

        # 2. Busca por palavras parciais (ex: 'para' em 'castanha do para') ou aproximadas (ex: 'amendo' -> 'amendoa')
        palavras_cliente = extrair_palavras_item(linha_norm)
        melhor_local_linha = None
        maior_nota_linha = 0.0

        for pal_cli in palavras_cliente:
            melhor_local_palavra = None
            maior_nota_palavra = 0.0

            for nome_local, lista_fp in vocab_locais.items():
                for _, palavras_prod in lista_fp:
                    for pal_cad in palavras_prod:
                        nota = similaridade_palavras(pal_cli, pal_cad)
                        if nota > maior_nota_palavra:
                            maior_nota_palavra = nota
                            melhor_local_palavra = nome_local

            # Nota >= 0.74 pega erros de digitação e abreviações sem confundir palavras aleatórias
            if maior_nota_palavra >= 0.74 and maior_nota_palavra > maior_nota_linha:
                maior_nota_linha = maior_nota_palavra
                melhor_local_linha = melhor_local_palavra

        if melhor_local_linha:
            locais_acionados.add(melhor_local_linha)

    lista_locais_ordenada = sorted(list(locais_acionados))
    qtd_pacotes = max(1, len(lista_locais_ordenada))
    return qtd_pacotes, lista_locais_ordenada


def eh_linha_endereco(linha: str) -> bool:
    linha_limpa = remover_acentos(linha.strip().lower())
    if not linha_limpa:
        return False
    # Se começa com número (ex: '5g amendo', '10@', '1 castanha'), é produto e não endereço
    if re.match(r"^\d+", linha_limpa):
        return False
    if linha_limpa.startswith(PREFIXOS_RUA):
        return True
    # Nome de rua seguido de número do imóvel (ex: 'Batista Carneiro 112 Salgado Filho')
    if re.search(r"[a-zA-Z]{3,}\s*,?\s*\d+", linha_limpa):
        return True
    return False


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
    linhas = [l.strip() for l in texto_bruto.splitlines() if l.strip()]

    pedidos = []
    nome_atual = None
    itens_atuais = []

    for linha in linhas:
        if nome_atual is None:
            nome_atual = linha.upper().strip()
            itens_atuais = []
        else:
            # Se for endereço, fecha o pedido atual e calcula os pacotes com tolerância a erros
            if eh_linha_endereco(linha):
                qtd_pct, locais_detectados = identificar_locais_dos_itens(itens_atuais, locais_dict)
                end_completo, status, lat, lon = buscar_endereco_completo(linha)
                resumo_itens = ", ".join(itens_atuais)
                if locais_detectados:
                    resumo_itens += f" ➔ [{', '.join(locais_detectados)}]"

                pedidos.append({
                    "Excluir": False,
                    "Status": status,
                    "Cliente": nome_atual,
                    "Vendedor": vendedor_padrao.upper().strip(),
                    "Pacotes": qtd_pct,
                    "Observacao": "",
                    "Posicao": "Normal",
                    "Endereco": end_completo,
                    "Itens_Lidos": resumo_itens,
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

if "contador_form" not in st.session_state:
    st.session_state["contador_form"] = 0

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

# --- PASSO 1: ADICIONAR PEDIDOS ---
st.subheader("1️⃣ Adicionar Pedidos")

texto_pedidos = st.text_area(
    "Cole os pedidos abaixo (eles serão adicionados à lista):",
    height=200,
    key=f"texto_pedidos_{st.session_state['contador_form']}",
    placeholder=(
        "Exemplo:\ngustavo ramos\n5g amendoim\n1 quebra noz\nAv flor de seda 1030, lindeia\n\n"
        "Bernardo\n1g granola\n1g amendoa\nRua Contria, 1380, Grajau"
    )
)
vendedor_lote = st.text_input(
    "Sigla do Vendedor `[ ]` para os pedidos acima:",
    key=f"vendedor_lote_{st.session_state['contador_form']}",
    placeholder="Ex: 2T, VG, NK"
)

if st.button("🔍 Adicionar à Lista", type="primary", use_container_width=True):
    if texto_pedidos.strip():
        with st.spinner("Extraindo pedidos, reconhecendo produtos e buscando CEPs..."):
            df_extraidos = extrair_pedidos_brutos(texto_pedidos, locais_config, vendedor_lote)
            if not df_extraidos.empty:
                adicionar_pedidos_na_sessao(df_extraidos)
                st.session_state["contador_form"] += 1
                st.rerun()
            else:
                st.warning("⚠️ Não foi possível identificar um endereço válido no texto colado.")
    else:
        st.warning("Cole pelo menos um pedido antes de clicar em adicionar.")

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
            "Corrija o endereço dando dois cliques na tabela abaixo."
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
            "Itens_Lidos": st.column_config.TextColumn("Itens e Locais Identificados", disabled=True, width="medium"),
        }
    )

    df_editado["Cliente"] = df_editado["Cliente"].astype(str).str.upper()

    # Se o usuário editou algum endereço na tabela, já busca o novo CEP automaticamente
    endereco_mudou = False
    for idx in df_editado.index:
        if idx in df_atual.index and df_editado.at[idx, "Endereco"] != df_atual.at[idx, "Endereco"]:
            end_novo, novo_status, lat, lon = buscar_endereco_completo(df_editado.at[idx, "Endereco"])
            df_editado.at[idx, "Endereco"] = end_novo
            df_editado.at[idx, "Status"] = novo_status
            df_editado.at[idx, "Lat"] = lat
            df_editado.at[idx, "Lon"] = lon
            endereco_mudou = True

    st.session_state["df_pedidos"] = df_editado
    if endereco_mudou:
        st.rerun()

    # Botões de ação responsivos
    col_acao1, col_acao2, col_acao3 = st.columns(3)

    with col_acao1:
        if st.button(
            "🔍 Buscar CEP após Editar Tabela",
            use_container_width=True,
            help="Use caso tenha corrigido algum endereço na tabela e queira rebuscar o CEP e Bairro."
        ):
            with st.spinner("Buscando CEP e Bairro dos endereços..."):
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
        texto_btn_excluir = f"🗑️ Excluir Selecionados ({qtd_marcados})" if qtd_marcados > 0 else "🗑️ Excluir Selecionados"
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
