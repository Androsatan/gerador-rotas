import streamlit as st
import pandas as pd
import requests
import re
import unicodedata
from urllib.parse import quote

st.set_page_config(page_title="Gerador de Rotas", page_icon="🛵", layout="wide")

# Cidades da Região Metropolitana de BH para detecção automática
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


def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def eh_linha_produto(linha: str, palavras_produtos: list) -> bool:
    """Identifica se a linha é um produto (ex: '10@', '5g amendoim', '1 quebra noz')."""
    linha_limpa = linha.strip().lower()
    if not linha_limpa:
        return False
    # Começa com número (ex: 10@, 5g, 1 quebra noz, 2x)
    if re.match(r"^\d+\s*([a-zA-Z@%]+)?(\s+|$)", linha_limpa):
        return True
    # Ou contém algum produto cadastrado nos 4 locais
    linha_sem_acento = remover_acentos(linha_limpa)
    for prod in palavras_produtos:
        if prod and prod in linha_sem_acento:
            return True
    return False


def eh_linha_endereco(linha: str) -> bool:
    """Identifica se a linha é um endereço (ex: 'Rua Itaipu 760' ou 'Batista Carneiro 112 Salgado Filho')."""
    linha_limpa = remover_acentos(linha.strip().lower())
    if not linha_limpa:
        return False
    # Se começa com número (ex: '5g amendoim'), não é endereço
    if re.match(r"^\d+", linha_limpa):
        return False
    # Começa com prefixo de via (Rua, Av, etc.)
    if linha_limpa.startswith(PREFIXOS_RUA):
        return True
    # Contém nome de rua seguido de número (ex: 'Batista Carneiro 112 Salgado Filho')
    if re.search(r"[a-zA-Z]{3,}\s*,?\s*\d+", linha_limpa):
        return True
    return False


def calcular_pacotes(itens_pedido: list, locais_dict: dict) -> int:
    """Calcula de quantos locais diferentes saem os produtos do pedido."""
    locais_acionados = set()
    texto_itens = remover_acentos(" ".join(itens_pedido).lower())

    for nome_local, lista_prods in locais_dict.items():
        for prod in lista_prods:
            prod_limpo = remover_acentos(prod.strip().lower())
            if prod_limpo and prod_limpo in texto_itens:
                locais_acionados.add(nome_local)

    return max(1, len(locais_acionados))


def separar_componentes_endereco(endereco_bruto: str):
    """Separa rua, número, bairro/complemento e cidade (padrão Belo Horizonte)."""
    end_limpo = endereco_bruto.strip()
    end_norm = remover_acentos(end_limpo.lower())

    # 1. Identificar se alguma cidade da RMBH foi citada no texto
    cidade_detectada = "Belo Horizonte"
    for cid in CIDADES_RMBH:
        if re.search(rf"\b{cid}\b", end_norm):
            cidade_detectada = cid.title()
            if cid == "sabara":
                cidade_detectada = "Sabará"
            elif cid == "ribeirao das neves":
                cidade_detectada = "Ribeirão das Neves"
            elif cid == "ibirite":
                cidade_detectada = "Ibirité"
            elif cid == "caete":
                cidade_detectada = "Caeté"
            elif cid == "mario campos":
                cidade_detectada = "Mário Campos"
            elif cid == "sao jose da lapa":
                cidade_detectada = "São José da Lapa"
            break

    # 2. Extrair o número do endereço
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
    """
    Busca o endereço completo (Rua, Número, Bairro, Cidade, CEP) em BH e Região Metropolitana
    usando ViaCEP + ArcGIS Geocoder (100% gratuito).
    Retorna: (endereco_formatado, status_msg, lat, lon)
    """
    rua, numero, bairro_dica, cidade = separar_componentes_endereco(endereco_bruto)
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

    # Passo 1: Tentar ViaCEP na cidade detectada (ex: Belo Horizonte)
    if len(rua_sem_prefixo) >= 3:
        try:
            url_viacep = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade))}/{quote(remover_acentos(rua_sem_prefixo))}/json/"
            resp = requests.get(url_viacep, timeout=5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and len(dados) > 0:
                    escolhido = dados[0]
                    # Se o usuário informou bairro (ex: 'lindeia', 'grajau', 'salgado filho'), filtra pelo bairro
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

    # Passo 2: Buscar coordenadas e complementar dados via ArcGIS Geocoder gratuito
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

    # Se o geocoder descobriu que a rua fica em outra cidade da RMBH (ex: Sabará/Nova Lima) e ainda não temos CEP, consulta ViaCEP na cidade certa
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

    # Validação de sucesso ou erro para avisar na tela
    if not logradouro_oficial and not lat:
        return (
            endereco_bruto,
            "❌ NÃO ENCONTRADO - CORRIGIR",
            None,
            None
        )

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
    """Lê o texto colado e separa cada pedido em Nome, Produtos, Quantidade de Pacotes e Endereço."""
    todas_palavras_prod = [p.strip().lower() for lista in locais_dict.values() for p in lista if p.strip()]
    linhas = [l.strip() for l in texto_bruto.splitlines() if l.strip()]

    pedidos = []
    nome_atual = None
    itens_atuais = []

    for linha in linhas:
        if nome_atual is None:
            # Primeira linha válida de um bloco é o nome do cliente
            nome_atual = linha.upper().strip()
            itens_atuais = []
        else:
            if eh_linha_produto(linha, todas_palavras_prod):
                itens_atuais.append(linha)
            elif eh_linha_endereco(linha):
                # Chegou no endereço: fecha o pedido atual
                qtd_pct = calcular_pacotes(itens_atuais, locais_dict)
                end_completo, status, lat, lon = buscar_endereco_completo(linha)
                pedidos.append({
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
                # Se ainda não tinha itens e apareceu outro texto sem número, pode ser complemento ou item sem número
                itens_atuais.append(linha)

    return pd.DataFrame(pedidos)


def montar_linha_cliente(row) -> str:
    """Formata a segunda linha no padrão: NOME [VENDEDOR] (XPCT) (OBS)"""
    partes = [str(row["Cliente"]).strip().upper()]

    vend = str(row.get("Vendedor", "")).strip().upper()
    if vend:
        partes.append(f"[{vend}]")

    try:
        pct = int(row.get("Pacotes", 1))
    except ValueError:
        pct = 1
    if pct > 1:
        partes.append(f"({pct}PCT)")

    obs = str(row.get("Observacao", "")).strip().upper()
    if obs:
        partes.append(f"({obs})")

    return " ".join(partes)


# ================= INTERFACE STREAMLIT =================
st.title("🛵 Gerador e Otimizador de Rotas - BH & Região")

# --- BARRA LATERAL: CONFIGURAÇÕES ---
with st.sidebar:
    st.header("📍 Ponto de Partida")
    ponto_partida = st.text_input(
        "Endereço de saída das rotas:",
        value="Bairro Maria Goretti, Belo Horizonte, MG",
        help="Você pode alterar para uma rua e número específicos quando quiser."
    )

    st.divider()
    st.header("📦 4 Locais de Saída (Pacotes)")
    st.caption(
        "Digite os produtos que saem de cada local (separados por vírgula). "
        "O sistema contará automaticamente quantos pacotes (2PCT, 3PCT, 4PCT) o pedido terá."
    )

    local_1 = st.text_area("Local de Saída 1:", placeholder="Ex: amendoim, amendoins, amendoa, quebra noz", height=70)
    local_2 = st.text_area("Local de Saída 2:", placeholder="Ex: granola", height=70)
    local_3 = st.text_area("Local de Saída 3:", placeholder="Ex: castanha", height=70)
    local_4 = st.text_area("Local de Saída 4:", placeholder="Digite os produtos do Local 4...", height=70)

    locais_config = {
        "Local 1": [p for p in local_1.split(",") if p.strip()],
        "Local 2": [p for p in local_2.split(",") if p.strip()],
        "Local 3": [p for p in local_3.split(",") if p.strip()],
        "Local 4": [p for p in local_4.split(",") if p.strip()],
    }

# --- PASSO 1: ENTRADA DOS PEDIDOS ---
st.subheader("1️⃣ Colar Pedidos")

col_input, col_opcoes = st.columns([3, 1])
with col_input:
    texto_pedidos = st.text_area(
        "Cole todos os pedidos abaixo:",
        height=240,
        placeholder=(
            "Exemplo:\ngustavo ramos\n\n5g amendoim\n1 quebra noz\n\n"
            "Av flor de seda 1030, lindeia\n\nBernardo\n\n1g granola\n1g amendoa\n\n"
            "Rua Contria, 1380, Grajau"
        )
    )

with col_opcoes:
    vendedor_lote = st.text_input(
        "Sigla do Vendedor `[ ]` (Opcional):",
        placeholder="Ex: 2L, BG, CK",
        help="Se quiser preencher a sigla de todos os pedidos colados de uma vez. Você também poderá editar um por um na tabela."
    )
    st.write("")
    btn_extrair = st.button("🔍 Extrair e Buscar Endereços", type="primary", use_container_width=True)

if btn_extrair and texto_pedidos.strip():
    with st.spinner("Extraindo pedidos e buscando CEPs e Bairros em BH e Região..."):
        st.session_state["df_pedidos"] = extrair_pedidos_brutos(texto_pedidos, locais_config, vendedor_lote)

# --- PASSO 2: TABELA DE CONFERÊNCIA E EDIÇÃO ---
if "df_pedidos" in st.session_state and not st.session_state["df_pedidos"].empty:
    st.divider()
    st.subheader("2️⃣ Conferência e Edição dos Pedidos Extraídos")

    df_atual = st.session_state["df_pedidos"]

    # Alerta visual se houver endereços não encontrados ou incompletos
    problemas = df_atual[df_atual["Status"] != "✅ OK"]
    if not problemas.empty:
        st.warning(
            f"⚠️ **{len(problemas)} endereço(s) precisam da sua atenção!** "
            "Verifique as linhas marcadas com ❌ ou ⚠️ na tabela abaixo, corrija o endereço dando dois cliques na célula "
            "e clique em **'🔄 Rebuscar Endereços Editados'**."
        )
    else:
        st.success(f"✅ Todos os {len(df_atual)} endereços foram localizados com Bairro e CEP!")

    df_editado = st.data_editor(
        df_atual,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_order=["Status", "Cliente", "Vendedor", "Pacotes", "Observacao", "Posicao", "Endereco", "Itens_Lidos"],
        column_config={
            "Status": st.column_config.TextColumn("Status do Endereço", disabled=True, width="medium"),
            "Cliente": st.column_config.TextColumn("Cliente (CAIXA ALTA)", width="medium"),
            "Vendedor": st.column_config.TextColumn("Vendedor [ ]", width="small"),
            "Pacotes": st.column_config.NumberColumn("Pacotes (PCT)", min_value=1, max_value=10, step=1, width="small"),
            "Observacao": st.column_config.TextColumn("Obs ( ) - Ex: TROCA", width="small"),
            "Posicao": st.column_config.SelectboxColumn(
                "Posição na Rota",
                options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                default="Normal",
                width="small"
            ),
            "Endereco": st.column_config.TextColumn("Endereço Completo (Editável)", width="large"),
            "Itens_Lidos": st.column_config.TextColumn("Itens Identificados", disabled=True, width="medium"),
        }
    )

    # Força nomes em CAIXA ALTA mesmo se o usuário editar em minúsculo
    df_editado["Cliente"] = df_editado["Cliente"].astype(str).str.upper()
    st.session_state["df_pedidos"] = df_editado

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("🔄 Rebuscar Endereços Editados", use_container_width=True):
            with st.spinner("Atualizando endereços..."):
                for idx, row in df_editado.iterrows():
                    end_novo, novo_status, lat, lon = buscar_endereco_completo(row["Endereco"])
                    df_editado.at[idx, "Endereco"] = end_novo
                    df_editado.at[idx, "Status"] = novo_status
                    df_editado.at[idx, "Lat"] = lat
                    df_editado.at[idx, "Lon"] = lon
                st.session_state["df_pedidos"] = df_editado
                st.rerun()

    # Prévia do formato final antes de dividirmos as rotas na Parte 2
    with st.expander("👀 Ver prévia de como os pedidos vão sair no texto final", expanded=True):
        linhas_previa = []
        for _, row in df_editado.iterrows():
            linhas_previa.append(f"{row['Endereco']}\n{montar_linha_cliente(row)}")
        st.code("\n\n".join(linhas_previa), language="text")
