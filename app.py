import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import re
import json
import os
import math
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote

st.set_page_config(page_title="Gerador de Rotas", page_icon="🛵", layout="wide")

# CSS reforçado: impede "..." dentro dos botões e empilha colunas em janelas reduzidas
st.markdown("""
<style>
div.stButton > button,
div.stFormSubmitButton > button {
    white-space: normal !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    height: auto !important;
    min-height: 2.8rem !important;
    padding: 0.5rem 0.6rem !important;
}

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

pre, code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

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

MAPA_NOMES_CIDADES = {
    "belo horizonte": "Belo Horizonte",
    "sabara": "Sabará",
    "nova lima": "Nova Lima",
    "contagem": "Contagem",
    "betim": "Betim",
    "santa luzia": "Santa Luzia",
    "ribeirao das neves": "Ribeirão das Neves",
    "ibirite": "Ibirité",
    "vespasiano": "Vespasiano",
    "lagoa santa": "Lagoa Santa",
    "pedro leopoldo": "Pedro Leopoldo",
    "brumadinho": "Brumadinho",
    "caete": "Caeté",
    "sarzedo": "Sarzedo",
    "mario campos": "Mário Campos",
    "sao jose da lapa": "São José da Lapa",
    "confins": "Confins",
    "esmeraldas": "Esmeraldas",
    "raposos": "Raposos"
}

PREFIXOS_RUA = (
    "rua ", "r. ", "r ", "av ", "av. ", "avenida ", "alameda ", "al. ",
    "praca ", "praça ", "travessa ", "tv. ", "beco ", "rodovia ", "estrada ", "anel "
)

PALAVRAS_NAO_ENDERECO = (
    "pacote", "pct", "pedido", "ped", "item", "itens", "kit", "combo",
    "sacola", "parte", "caixa", "obs", "observacao", "total", "valor",
    "frete", "taxa", "troco", "pix", "pagamento", "cliente", "nome"
)

STOPWORDS_PRODUTOS = {"de", "do", "da", "dos", "das", "com", "sem", "e", "ou", "a", "o", "un", "pct", "gr", "kg", "ml", "totais", "total"}

CORES_ROTAS = ["#e63946", "#2a9d8f", "#3a86ff", "#ff9f1c"]

REGEX_CABECALHO_CHAT = re.compile(
    r"^\s*\[?\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*[,\-]?\s*\d{1,2}:\d{2}(?::\d{2})?\]?\s*(?:-\s*)?[^:\n]{1,35}:\s*(.*)$"
)


# ================= FUNÇÕES DE CONFIGURAÇÃO (SALVAR PRODUTOS) =================
def carregar_config():
    padrao = {
        "ponto_partida": "Bairro Maria Goretti, Belo Horizonte, MG",
        "local_1": "skunk, orange, amnesia, silver, wolf, super sheep, og kush, indoor, zowahh",
        "local_2": "ice, pak, dry, pod, colombia gold, uva",
        "local_3": "@, md, lsd, pacote gd",
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


def detectar_cidade_rmbh(texto: str) -> str:
    texto_norm = remover_acentos(texto.lower())
    for cid in CIDADES_RMBH:
        if re.search(rf"\b{cid}\b", texto_norm):
            return MAPA_NOMES_CIDADES.get(cid, cid.title())
    return "Belo Horizonte"


def extrair_palavras_item(texto_linha: str) -> list:
    limpo = remover_acentos(texto_linha.lower())
    # Remove números inteiros, decimais (12.5g, 12,5), frações (7/5) e símbolos (#)
    limpo = re.sub(r"\b\d+(?:[.,/]\d+)?\s*(g|gr|kg|ml|l|un|pct|x|#)?\b", " ", limpo)
    palavras = re.findall(r"[a-z0-9@]+", limpo)
    return [p for p in palavras if p not in STOPWORDS_PRODUTOS and len(p) >= 2]


def similaridade_palavras(palavra_cliente: str, palavra_cadastro: str) -> float:
    if palavra_cliente == palavra_cadastro:
        return 1.0
    menor, maior = sorted([palavra_cliente, palavra_cadastro], key=len)
    if len(menor) >= 3 and maior.startswith(menor):
        return 0.90
    if len(palavra_cliente) >= 3 and len(palavra_cadastro) >= 3:
        return SequenceMatcher(None, palavra_cliente, palavra_cadastro).ratio()
    return 0.0


def identificar_locais_dos_itens(itens_pedido: list, locais_dict: dict):
    """
    Analisa todos os itens do pedido (inclusive quando vêm vários produtos na mesma linha
    separados por '+' ou entre parênteses) e identifica de quais locais saem.
    """
    locais_acionados = set()

    vocab_locais = {}
    for nome_local, lista_prods in locais_dict.items():
        frases_e_palavras = []
        for prod in lista_prods:
            prod_norm = remover_acentos(prod.strip().lower())
            if not prod_norm:
                continue
            palavras_prod = [
                p for p in re.findall(r"[a-z0-9@]+", prod_norm)
                if p not in STOPWORDS_PRODUTOS
            ]
            colado = "".join(palavras_prod)
            if colado and colado not in palavras_prod:
                palavras_prod.append(colado)
            frases_e_palavras.append((prod_norm, palavras_prod))
        vocab_locais[nome_local] = frases_e_palavras

    # Divide linhas que contenham '+' (ex: '( 5g colombia + 5g Colômbia + 1g Dry )') em sub-itens
    sub_itens = []
    for linha in itens_pedido:
        partes_plus = re.split(r"[+;]", linha)
        for p in partes_plus:
            if p.strip():
                sub_itens.append(p.strip())

    for item_str in sub_itens:
        linha_norm = remover_acentos(item_str.lower()).strip(" ()[]")
        if not linha_norm:
            continue

        # 1. Verifica frases exatas ou símbolos ('@', 'md', 'lsd', 'pacote gd', etc.)
        for nome_local, lista_fp in vocab_locais.items():
            for frase_completa, _ in lista_fp:
                frase_sem_espaco = frase_completa.replace(" ", "")
                if frase_completa in ("@", "md", "lsd") and re.search(rf"(?:^|\d|\s|#){re.escape(frase_completa)}(?:$|\s)", linha_norm):
                    locais_acionados.add(nome_local)
                elif len(frase_completa) >= 3 and (
                    re.search(rf"\b{re.escape(frase_completa)}\b", linha_norm)
                    or (len(frase_sem_espaco) >= 5 and frase_sem_espaco in linha_norm)
                ):
                    locais_acionados.add(nome_local)

        # 2. Avalia palavra por palavra para pegar abreviações e erros de digitação
        palavras_cliente = extrair_palavras_item(linha_norm)
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

            if maior_nota_palavra >= 0.76 and melhor_local_palavra:
                locais_acionados.add(melhor_local_palavra)

    lista_locais_ordenada = sorted(list(locais_acionados))
    qtd_pacotes = max(1, len(lista_locais_ordenada))
    return qtd_pacotes, lista_locais_ordenada


def eh_subtitulo_ou_divisoria(linha: str) -> bool:
    limpa = remover_acentos(linha.strip().lower())
    if not limpa:
        return True
    if re.match(r"^[-=_*.;:]+$", limpa):
        return True
    if re.match(r"^(pacote|pct|pedido|ped|item|itens|kit|combo|sacola|parte|caixa|produtos?|lista)\b\s*\d*\s*[;:.-]*$", limpa):
        return True
    return False


def texto_parece_produto_cadastrado(texto_sem_num: str, locais_dict: dict) -> bool:
    """Verifica se o texto antes de um número é na verdade o nome de um produto cadastrado."""
    if not locais_dict:
        return False
    palavras = [p for p in re.findall(r"[a-z]+", remover_acentos(texto_sem_num.lower())) if len(p) >= 3]
    if not palavras:
        return False

    for lista_prods in locais_dict.values():
        for prod in lista_prods:
            p_cads = re.findall(r"[a-z]+", remover_acentos(prod.lower()))
            for pal in palavras:
                for pc in p_cads:
                    if similaridade_palavras(pal, pc) >= 0.80:
                        return True
    return False


def eh_linha_produto_clara(linha: str, locais_dict: dict = None) -> bool:
    """Identifica linhas que são claramente produtos (ex: '10g uva', '( 5g colombia + 1g Dry )', '2# lsd', 'Pacote GD')."""
    bruta = linha.strip()
    limpa = remover_acentos(bruta.lower()).strip(" ()[]")
    if not limpa or eh_subtitulo_ou_divisoria(bruta):
        return False
    # Começa com quantidade numérica (ex: 5g, 12.5G, 12,5, 7/5, 1@, 2#)
    if re.match(r"^\d+(?:[.,/]\d+)?\s*([a-z@#%]+\b)?", limpa):
        return True
    # Começa com 'pacote ' (ex: 'Pacote GD')
    if re.match(r"^(pacote|pct)\s+[a-z0-9]+", limpa):
        return True
    return False


def eh_linha_endereco(linha: str, locais_dict: dict = None) -> bool:
    """
    Reconhece qualquer formato de endereço em BH/RMBH, incluindo:
    - Com prefixo ('Rua ...', 'Av ...')
    - Bairro antes da rua ('Granja de Freitas rua São Vicente 530')
    - Sem 'Rua' e com bairro ('Batista Carneiro 112 Salgado Filho', 'Paulo Brandão 77 santa efigenia')
    - Apenas 1 nome de rua + número ('timbiras 2898', 'Lambari 403')
    """
    bruta = linha.strip()
    if not bruta:
        return False

    # Linhas entre parênteses como '( 5g colombia + 1g Dry )' são produtos/observações
    if bruta.startswith("(") and bruta.endswith(")"):
        return False

    linha_limpa = remover_acentos(bruta.lower())

    if eh_subtitulo_ou_divisoria(bruta) or bruta.endswith(";") or bruta.endswith(":"):
        return False

    for pal_proibida in PALAVRAS_NAO_ENDERECO:
        if re.match(rf"^{pal_proibida}\b", linha_limpa):
            return False

    if re.match(r"^(endereco|end\.?|local|entrega)\s*[:\-]", linha_limpa):
        return True

    # Se começa com número (5g, 10, 2#, 1@), é produto
    if re.match(r"^\d+", linha_limpa):
        return False

    # Começa com Rua, Av, Avenida, Alameda, etc.
    if linha_limpa.startswith(PREFIXOS_RUA):
        return True

    # Contém Rua/Avenida no meio da linha + número (ex: 'Granja de Freitas rua São Vicente 530')
    if re.search(r"\b(rua|avenida|av\.?|alameda|travessa|praca|rodovia)\s+[a-z]{3,}", linha_limpa) and re.search(r"\b\d{1,5}\b", linha_limpa):
        return True

    # Se tiver unidade de produto colada em número (5g, 50g, 1@, 2#), é produto
    if re.search(r"\b\d+(?:[.,/]\d+)?\s*(g|gr|kg|ml|un|pct|x|@|#)\b", linha_limpa) or "@" in linha_limpa or "#" in linha_limpa:
        return False

    # Verifica padrão de rua sem prefixo 'Rua/Av' seguida de número (ex: 'timbiras 2898', 'Lambari 403', 'itaparica 420, portao verde')
    match_via_num = re.search(r"^([a-z\s.,'-]{3,}?)\s*[,.]?\s*(\d{1,5})\b", linha_limpa)
    if match_via_num:
        nome_antes_num = match_via_num.group(1).strip(" ,.-")
        palavras_todas = re.findall(r"[a-z]{2,}", linha_limpa)
        # Se tem 2 ou mais palavras (ex: 'Paulo Brandão 77 santa efigenia') é endereço
        if len(palavras_todas) >= 2:
            return True
        # Se tem apenas 1 palavra + número (ex: 'timbiras 2898', 'Lambari 403'),
        # confirma que essa palavra tem pelo menos 4 letras e não é um produto cadastrado
        if len(nome_antes_num) >= 4 and not texto_parece_produto_cadastrado(nome_antes_num, locais_dict):
            return True

    return False


def eh_complemento_pos_endereco(linha: str) -> bool:
    limpa = remover_acentos(linha.strip().lower())
    if not limpa:
        return False
    if re.match(r"^(cep|bairro|apto|ap\.?|apartamento|bloco|bl\.?|casa|condominio|ed\.?|edificio)\b", limpa):
        return True
    if re.match(r"^\d{5}-?\d{3}$", limpa):
        return True
    return False


def limpar_nome_cliente(linha: str) -> str:
    nome = re.sub(r"^(cliente|nome|pedido|ped)\s*[:\-]?\s+", "", linha.strip(), flags=re.IGNORECASE)
    return nome.strip().upper()


def pode_ser_nome_cliente(linha: str) -> bool:
    bruta = linha.strip()
    limpa = remover_acentos(bruta.lower())
    if not limpa:
        return False
    if bruta.startswith("(") or eh_subtitulo_ou_divisoria(bruta) or bruta.endswith(";"):
        return False
    if re.match(r"^\d+", limpa):
        return False
    if re.match(r"^(pacote|pct)\b", limpa):
        return False
    return True


def separar_componentes_endereco(endereco_bruto: str):
    """
    Separa Rua, Número, Bairro (dica) e Cidade limpando pontuações como
    'costa. 321 , Bairro : santa amelia' ou 'ap 504 bairro santo antonio'.
    """
    end_limpo = re.sub(r"^(endereco|end\.?|local|entrega)\s*[:\-]\s*", "", endereco_bruto.strip(), flags=re.IGNORECASE)
    cidade_detectada = detectar_cidade_rmbh(end_limpo)

    bairro_antes_da_rua = ""
    match_meio = re.search(
        r"^(.+?)\s+\b(rua|r\.|avenida|av\.|av|alameda|al\.|travessa|tv\.|praca|praça|beco|rodovia)\s+(.+)$",
        end_limpo,
        flags=re.IGNORECASE
    )
    if match_meio:
        possivel_bairro_antes = match_meio.group(1).strip(" ,.-")
        if not remover_acentos(possivel_bairro_antes.lower()).startswith(PREFIXOS_RUA):
            bairro_antes_da_rua = possivel_bairro_antes
            end_limpo = f"{match_meio.group(2)} {match_meio.group(3)}"

    # Aceita ponto, vírgula ou espaço antes do número (ex: 'costa. 321')
    match_num = re.search(r"(?:[,.]\s*|\s+)(\d+)\b(.*)$", end_limpo)
    if match_num:
        rua = end_limpo[:match_num.start()].strip(" ,.-")
        numero = match_num.group(1).strip()
        resto = match_num.group(2).strip(" ,.-")
    else:
        rua = end_limpo.strip(" ,.-")
        numero = ""
        resto = ""

    # Remove 'ap 504', 'apto 1203', 'bloco B', etc.
    resto_limpo = re.sub(
        r"\b(ap\.?|apto\.?|apartamento|bl\.?|bloco|casa|sl\.?|sala|lj\.?|loja)\s*\d*[a-zA-Z]?\b",
        " ",
        resto,
        flags=re.IGNORECASE
    )
    # Remove a palavra 'Bairro :' ou 'Bairro' do resto para sobrar apenas o nome puro do bairro
    resto_limpo = re.sub(r"\bbairro\s*[:\-]?\s*", " ", resto_limpo, flags=re.IGNORECASE)

    for cid in CIDADES_RMBH:
        resto_limpo = re.sub(rf"\b{cid}\b", " ", resto_limpo, flags=re.IGNORECASE)
        resto_limpo = re.sub(rf"\b{MAPA_NOMES_CIDADES[cid]}\b", " ", resto_limpo, flags=re.IGNORECASE)

    resto_limpo = re.sub(r"\b\d{5}-?\d{3}\b", " ", resto_limpo)
    resto_limpo = re.sub(r"\s+", " ", resto_limpo).strip(" ,.-/ :")

    if bairro_antes_da_rua and resto_limpo:
        bairro_dica = f"{bairro_antes_da_rua}, {resto_limpo}"
    elif bairro_antes_da_rua:
        bairro_dica = bairro_antes_da_rua
    else:
        bairro_dica = resto_limpo

    return rua, numero, bairro_dica, cidade_detectada


def dentro_perimetro_rmbh(lat: float, lon: float) -> bool:
    return (-20.40 <= lat <= -19.40) and (-44.60 <= lon <= -43.40)


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_coordenada_bairro(nome_bairro_limpo: str, cidade: str):
    bairro_alvo_norm = remover_acentos(nome_bairro_limpo.lower()).strip()

    try:
        q_nom = f"{nome_bairro_limpo}, {cidade}, Minas Gerais, Brasil"
        url_nom = (
            f"https://nominatim.openstreetmap.org/search"
            f"?q={quote(q_nom)}&format=jsonv2&addressdetails=1&limit=10&countrycodes=br"
        )
        headers = {"User-Agent": "GeradorRotasRMBH/2.0 (contato@geradorrotas.app)"}
        resp = requests.get(url_nom, headers=headers, timeout=5)
        if resp.status_code == 200:
            resultados = resp.json()
            for item in resultados:
                cat = item.get("category", "")
                tipo = item.get("type", "")
                end_det = item.get("address", {})

                if cat in ("highway", "amenity", "shop", "tourism", "building"):
                    continue

                lat_i = float(item["lat"])
                lon_i = float(item["lon"])
                if not dentro_perimetro_rmbh(lat_i, lon_i):
                    continue

                suburb = end_det.get("suburb") or end_det.get("neighbourhood") or end_det.get("quarter") or item.get("name", "")
                suburb_norm = remover_acentos(suburb.lower())

                if tipo in ("suburb", "neighbourhood", "quarter", "administrative", "city_district") or (
                    bairro_alvo_norm in suburb_norm or suburb_norm in bairro_alvo_norm
                ):
                    regional = end_det.get("city_district") or end_det.get("municipality") or ""
                    cid_item = end_det.get("city") or end_det.get("town") or cidade
                    cep_item = end_det.get("postcode", "")
                    detalhe = f"Bairro {suburb}"
                    if regional and regional.lower() != suburb.lower():
                        detalhe += f" ({regional})"
                    detalhe += f", {cid_item}"
                    if cep_item:
                        detalhe += f" | CEP: {cep_item}"
                    return True, detalhe, lat_i, lon_i
    except Exception:
        pass

    try:
        q_photon = f"{nome_bairro_limpo} {cidade} Minas Gerais"
        url_photon = f"https://photon.komoot.io/api/?q={quote(q_photon)}&lat=-19.9167&lon=-43.9345&limit=10"
        resp_p = requests.get(url_photon, timeout=5)
        if resp_p.status_code == 200:
            features = resp_p.json().get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                osm_key = props.get("osm_key", "")
                osm_val = props.get("osm_value", "")
                if osm_key == "highway":
                    continue
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    lon_f, lat_f = float(coords[0]), float(coords[1])
                    if dentro_perimetro_rmbh(lat_f, lon_f) and osm_val in (
                        "suburb", "neighbourhood", "quarter", "district", "locality", "administrative"
                    ):
                        nome_f = props.get("name", nome_bairro_limpo.title())
                        cid_f = props.get("city", cidade)
                        return True, f"Bairro {nome_f}, {cid_f} - MG", lat_f, lon_f
    except Exception:
        pass

    try:
        q_arc = f"{nome_bairro_limpo}, {cidade}, Minas Gerais, Brasil"
        url_arc = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_arc)}&category=Neighborhood,Locality,Subregion"
            f"&searchExtent=-44.50,-20.30,-43.50,-19.50"
            f"&outFields=Addr_type,PlaceName,Nbrhd,City,Postal&maxLocations=5&f=json"
        )
        resp_a = requests.get(url_arc, timeout=5)
        if resp_a.status_code == 200:
            cands = resp_a.json().get("candidates", [])
            for c in cands:
                if c.get("score", 0) >= 80:
                    lat_a = float(c["location"]["y"])
                    lon_a = float(c["location"]["x"])
                    if dentro_perimetro_rmbh(lat_a, lon_a):
                        atrib = c.get("attributes", {})
                        nome_b = atrib.get("PlaceName") or atrib.get("Nbrhd") or nome_bairro_limpo.title()
                        cid_a = atrib.get("City") or cidade
                        return True, f"Bairro {nome_b}, {cid_a} - MG", lat_a, lon_a
    except Exception:
        pass

    return False, "❌ Bairro não localizado em BH/Região. Confira a grafia ou digite uma rua/CEP.", None, None


@st.cache_data(ttl=3600, show_spinner=False)
def geocodificar_endereco_rua(endereco_completo_texto: str):
    try:
        q_geo = f"{endereco_completo_texto}, Minas Gerais, Brasil"
        url_arcgis = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_geo)}&searchExtent=-44.50,-20.30,-43.50,-19.50&maxLocations=1&f=json"
        )
        resp = requests.get(url_arcgis, timeout=5)
        if resp.status_code == 200:
            cands = resp.json().get("candidates", [])
            if cands:
                lat = float(cands[0]["location"]["y"])
                lon = float(cands[0]["location"]["x"])
                if dentro_perimetro_rmbh(lat, lon):
                    return lat, lon
    except Exception:
        pass

    try:
        url_nom = (
            f"https://nominatim.openstreetmap.org/search"
            f"?q={quote(endereco_completo_texto + ', Minas Gerais, Brasil')}&format=json&limit=1"
        )
        headers = {"User-Agent": "GeradorRotasRMBH/2.0"}
        resp_n = requests.get(url_nom, headers=headers, timeout=5)
        if resp_n.status_code == 200:
            dados = resp_n.json()
            if dados:
                return float(dados[0]["lat"]), float(dados[0]["lon"])
    except Exception:
        pass

    return -19.9167, -43.9345


def numero_cabe_na_faixa_viacep(numero_str: str, complemento_viacep: str) -> bool:
    if not numero_str or not complemento_viacep:
        return True
    try:
        num = int(re.sub(r"\D", "", numero_str))
    except ValueError:
        return True

    comp = remover_acentos(complemento_viacep.lower())
    m_de_a = re.search(r"de\s+(\d+)(?:/\d+)?\s+a\s+(\d+)(?:/\d+)?", comp)
    if m_de_a:
        ini, fim = int(m_de_a.group(1)), int(m_de_a.group(2))
        return ini <= num <= fim
    m_ate = re.search(r"ate\s+(\d+)", comp)
    if m_ate:
        return num <= int(m_ate.group(1))
    m_fim = re.search(r"de\s+(\d+)(?:/\d+)?\s+ao\s+fim", comp)
    if m_fim:
        return num >= int(m_fim.group(1))
    return True


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_endereco_completo(endereco_bruto: str):
    if not str(endereco_bruto).strip():
        return "", "❌ NÃO ENCONTRADO - CORRIGIR", None, None, []

    rua, numero, bairro_dica, cidade = separar_componentes_endereco(str(endereco_bruto))
    rua_sem_prefixo = re.sub(
        r"^(rua|r\.|r|avenida|av\.|av|alameda|al\.|praca|praça|travessa|tv\.|beco)\s+",
        "",
        rua,
        flags=re.IGNORECASE
    ).strip()

    cep_encontrado = ""
    logradouro_oficial = ""
    bairro_oficial = ""
    cidade_oficial = cidade
    lat, lon = None, None
    opcoes_bairros = []

    # 1. Consulta ViaCEP pelo nome da rua
    if len(rua_sem_prefixo) >= 3:
        try:
            url_viacep = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade))}/{quote(remover_acentos(rua_sem_prefixo))}/json/"
            resp = requests.get(url_viacep, timeout=5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and len(dados) > 0:
                    candidatos_faixa = [
                        d for d in dados
                        if d.get("bairro") and numero_cabe_na_faixa_viacep(numero, d.get("complemento", ""))
                    ]
                    if not candidatos_faixa:
                        candidatos_faixa = [d for d in dados if d.get("bairro")]

                    bateu_bairro_dica = []
                    if bairro_dica:
                        dica_norm = remover_acentos(bairro_dica.lower())
                        for item in candidatos_faixa:
                            b_item = remover_acentos(item.get("bairro", "").lower())
                            if b_item and (b_item in dica_norm or dica_norm in b_item or SequenceMatcher(None, b_item, dica_norm).ratio() >= 0.78):
                                bateu_bairro_dica.append(item)

                    if bateu_bairro_dica:
                        escolhido = bateu_bairro_dica[0]
                    else:
                        escolhido = candidatos_faixa[0] if candidatos_faixa else dados[0]

                        mapa_bairros_unicos = {}
                        for item in candidatos_faixa:
                            b_nome = item.get("bairro", "").strip()
                            if b_nome and b_nome not in mapa_bairros_unicos:
                                logr_i = item.get("logradouro") or rua.title()
                                cid_i = item.get("localidade") or cidade
                                cep_i = item.get("cep", "")
                                partes_op = [logr_i]
                                if numero:
                                    partes_op.append(numero)
                                partes_op.append(b_nome)
                                partes_op.append(cid_i)
                                if cep_i:
                                    partes_op.append(cep_i)
                                mapa_bairros_unicos[b_nome] = ", ".join(partes_op)

                        if len(mapa_bairros_unicos) > 1:
                            opcoes_bairros = list(mapa_bairros_unicos.values())

                    logradouro_oficial = escolhido.get("logradouro", "")
                    bairro_oficial = escolhido.get("bairro", "")
                    cidade_oficial = escolhido.get("localidade", cidade)
                    cep_encontrado = escolhido.get("cep", "")
        except Exception:
            pass

    # 2. Consulta ArcGIS Geocoder
    rua_busca = logradouro_oficial if logradouro_oficial else rua
    bairro_busca = bairro_oficial if bairro_oficial else bairro_dica
    try:
        query_geo = f"{rua_busca}, {numero}, {bairro_busca}, {cidade_oficial}, Minas Gerais, Brasil"
        url_arcgis = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(query_geo)}&searchExtent=-44.50,-20.30,-43.50,-19.50"
            f"&outFields=StName,StType,AddNum,Nbrhd,City,Postal&maxLocations=1&f=json"
        )
        resp_geo = requests.get(url_arcgis, timeout=5)
        if resp_geo.status_code == 200:
            cands = resp_geo.json().get("candidates", [])
            if cands and cands[0].get("score", 0) >= 75:
                melhor = cands[0]
                lat_cand = float(melhor["location"]["y"])
                lon_cand = float(melhor["location"]["x"])
                if dentro_perimetro_rmbh(lat_cand, lon_cand):
                    lat, lon = lat_cand, lon_cand
                    atrib = melhor.get("attributes", {})

                    if not bairro_oficial and atrib.get("Nbrhd"):
                        bairro_oficial = atrib.get("Nbrhd")
                    if atrib.get("City"):
                        cidade_oficial = atrib.get("City")
                    if not cep_encontrado and atrib.get("Postal"):
                        cep_raw = re.sub(r"\D", "", atrib.get("Postal", ""))
                        if len(cep_raw) == 8:
                            cep_encontrado = f"{cep_raw[:5]}-{cep_raw[5:]}"
                    if not logradouro_oficial and atrib.get("StName"):
                        st_type = atrib.get("StType", "")
                        st_name = atrib.get("StName", "")
                        logradouro_oficial = f"{st_type} {st_name}".strip()
    except Exception:
        pass

    # 3. Se achou CEP pelo geocoder, busca nome oficial no ViaCEP
    if cep_encontrado and not opcoes_bairros:
        cep_digitos = re.sub(r"\D", "", cep_encontrado)
        if len(cep_digitos) == 8:
            try:
                resp_cep_direto = requests.get(f"https://viacep.com.br/ws/{cep_digitos}/json/", timeout=4)
                if resp_cep_direto.status_code == 200:
                    d_cep = resp_cep_direto.json()
                    if not d_cep.get("erro"):
                        logradouro_oficial = d_cep.get("logradouro") or logradouro_oficial
                        bairro_oficial = d_cep.get("bairro") or bairro_oficial
                        cidade_oficial = d_cep.get("localidade") or cidade_oficial
                        cep_encontrado = d_cep.get("cep") or cep_encontrado
            except Exception:
                pass

    # 4. Segunda tentativa ViaCEP caso a cidade seja outra da RMBH
    if not cep_encontrado and cidade_oficial and len(rua_sem_prefixo) >= 3:
        try:
            url_viacep2 = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade_oficial))}/{quote(remover_acentos(rua_sem_prefixo))}/json/"
            resp2 = requests.get(url_viacep2, timeout=5)
            if resp2.status_code == 200:
                dados2 = resp2.json()
                if isinstance(dados2, list) and len(dados2) > 0:
                    escolhido2 = dados2[0]
                    if bairro_dica:
                        dica_norm = remover_acentos(bairro_dica.lower())
                        for item in dados2:
                            b_item = remover_acentos(item.get("bairro", "").lower())
                            if b_item and (b_item in dica_norm or dica_norm in b_item):
                                escolhido2 = item
                                break
                    logradouro_oficial = logradouro_oficial or escolhido2.get("logradouro", "")
                    bairro_oficial = bairro_oficial or escolhido2.get("bairro", "")
                    cep_encontrado = escolhido2.get("cep", "")
        except Exception:
            pass

    if not logradouro_oficial and lat is None:
        return endereco_bruto, "❌ NÃO ENCONTRADO - CORRIGIR", None, None, []

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

    if lat is None or lon is None:
        lat, lon = geocodificar_endereco_rua(endereco_padronizado)

    if len(opcoes_bairros) > 1:
        status = f"⚠️ {len(opcoes_bairros)} BAIRROS ENCONTRADOS (ESCOLHER)"
    elif not cep_encontrado or bairro_final == "Bairro não identificado":
        status = "⚠️ INCOMPLETO (CONFERIR BAIRRO/CEP)"
    else:
        status = "✅ OK"

    return endereco_padronizado, status, lat, lon, opcoes_bairros


@st.cache_data(ttl=3600, show_spinner=False)
def validar_e_geocodificar_partida(texto_partida: str):
    bruto = str(texto_partida).strip()
    if not bruto:
        return False, "❌ Digite um bairro, rua ou CEP de partida.", None, None

    apenas_digitos = re.sub(r"\D", "", bruto)
    if len(apenas_digitos) == 8:
        try:
            resp_cep = requests.get(f"https://viacep.com.br/ws/{apenas_digitos}/json/", timeout=5)
            if resp_cep.status_code == 200:
                d_cep = resp_cep.json()
                if not d_cep.get("erro"):
                    logr = d_cep.get("logradouro", "")
                    bair = d_cep.get("bairro", "")
                    cid = d_cep.get("localidade", "Belo Horizonte")
                    cep_f = d_cep.get("cep", bruto)
                    desc = f"{logr}, {bair}, {cid} ({cep_f})".strip(" ,")
                    lat, lon = geocodificar_endereco_rua(desc)
                    return True, f"CEP localizado: {desc}", lat, lon
        except Exception:
            pass

    texto_norm = remover_acentos(bruto.lower())
    tem_prefixo_rua = texto_norm.startswith(PREFIXOS_RUA)
    tem_numero_imovel = bool(re.search(r"\b\d+\b", texto_norm))

    if tem_prefixo_rua or tem_numero_imovel:
        end_form, status_end, lat, lon, _ = buscar_endereco_completo(bruto)
        if status_end.startswith("❌") or lat is None:
            return False, "❌ Endereço de partida não encontrado. Confira a rua/número.", None, None
        return True, f"Endereço: {end_form}", lat, lon

    cidade_alvo = detectar_cidade_rmbh(bruto)
    nome_bairro = re.sub(r"\bbairro\b", "", bruto, flags=re.IGNORECASE)
    for cid in CIDADES_RMBH:
        nome_bairro = re.sub(rf"\b{cid}\b", "", nome_bairro, flags=re.IGNORECASE)
        nome_bairro = re.sub(rf"\b{MAPA_NOMES_CIDADES[cid]}\b", "", nome_bairro, flags=re.IGNORECASE)
    nome_bairro = re.sub(r"\b(mg|minas gerais|brasil)\b", "", nome_bairro, flags=re.IGNORECASE)
    nome_bairro = nome_bairro.strip(" ,.-/")

    if not nome_bairro:
        return False, "❌ Informe o nome do bairro ou da rua de partida.", None, None

    ok_b, desc_b, lat_b, lon_b = buscar_coordenada_bairro(nome_bairro, cidade_alvo)
    if ok_b:
        return True, desc_b, lat_b, lon_b

    end_form, status_end, lat, lon, _ = buscar_endereco_completo(bruto)
    if not status_end.startswith("❌") and lat is not None:
        return True, f"Via localizada: {end_form}", lat, lon

    return False, desc_b, None, None


def processar_bloco_unico_pedido(linhas_bloco: list, locais_dict: dict, vendedor_padrao: str = ""):
    nome_cliente = None
    itens_pedido = []
    linhas_endereco = []

    for linha in linhas_bloco:
        l_strip = linha.strip()
        if not l_strip or eh_subtitulo_ou_divisoria(l_strip):
            continue

        if eh_linha_endereco(l_strip, locais_dict):
            linhas_endereco.append(l_strip)
        elif eh_complemento_pos_endereco(l_strip) and linhas_endereco:
            linhas_endereco[-1] = f"{linhas_endereco[-1]}, {l_strip}"
        elif eh_linha_produto_clara(l_strip, locais_dict):
            itens_pedido.append(l_strip)
        elif nome_cliente is None and pode_ser_nome_cliente(l_strip):
            nome_cliente = limpar_nome_cliente(l_strip)
        else:
            itens_pedido.append(l_strip)

    if not nome_cliente or not linhas_endereco:
        return None

    endereco_bruto_final = ", ".join(linhas_endereco)
    qtd_pct, locais_detectados = identificar_locais_dos_itens(itens_pedido, locais_dict)
    end_completo, status, lat, lon, opcoes_amb = buscar_endereco_completo(endereco_bruto_final)

    resumo_itens = ", ".join(itens_pedido)
    if locais_detectados:
        resumo_itens += f" ➔ [{', '.join(locais_detectados)}]"

    return {
        "Excluir": False,
        "Status": status,
        "Cliente": nome_cliente,
        "Vendedor": vendedor_padrao.upper().strip(),
        "Pacotes": qtd_pct,
        "Observacao": "",
        "Posicao": "Normal",
        "Endereco": end_completo,
        "Itens_Lidos": resumo_itens,
        "Lat": lat,
        "Lon": lon,
        "Opcoes_Endereco": json.dumps(opcoes_amb, ensure_ascii=False)
    }


def extrair_pedidos_brutos(texto_bruto: str, locais_dict: dict, vendedor_padrao: str = ""):
    linhas_originais = texto_bruto.splitlines()
    tem_cabecalho_chat = any(REGEX_CABECALHO_CHAT.match(l) for l in linhas_originais if l.strip())

    pedidos = []

    if tem_cabecalho_chat:
        blocos = []
        bloco_atual = []
        for l in linhas_originais:
            m_chat = REGEX_CABECALHO_CHAT.match(l)
            if m_chat:
                if bloco_atual:
                    blocos.append(bloco_atual)
                resto_primeira_linha = m_chat.group(1).strip()
                bloco_atual = [resto_primeira_linha] if resto_primeira_linha else []
            else:
                if l.strip():
                    bloco_atual.append(l.strip())
        if bloco_atual:
            blocos.append(bloco_atual)

        for b in blocos:
            ped = processar_bloco_unico_pedido(b, locais_dict, vendedor_padrao)
            if ped:
                pedidos.append(ped)
        return pd.DataFrame(pedidos)

    # Modo sem cabeçalho do Telegram: separa blocos mesmo se houver produto após endereço
    linhas_cruas = [l.strip() for l in linhas_originais if l.strip()]
    blocos = []
    bloco_atual = []
    ja_tem_endereco_no_bloco = False

    i = 0
    n = len(linhas_cruas)
    while i < n:
        linha = linhas_cruas[i]

        if eh_subtitulo_ou_divisoria(linha):
            i += 1
            continue

        if not bloco_atual:
            bloco_atual.append(linha)
            ja_tem_endereco_no_bloco = eh_linha_endereco(linha, locais_dict)
            i += 1
            continue

        if eh_linha_endereco(linha, locais_dict):
            bloco_atual.append(linha)
            ja_tem_endereco_no_bloco = True
            while (i + 1) < n and eh_complemento_pos_endereco(linhas_cruas[i + 1]):
                bloco_atual.append(linhas_cruas[i + 1])
                i += 1
            i += 1
            continue

        if ja_tem_endereco_no_bloco:
            if eh_linha_produto_clara(linha, locais_dict):
                bloco_atual.append(linha)
                i += 1
                continue
            else:
                blocos.append(bloco_atual)
                bloco_atual = [linha]
                ja_tem_endereco_no_bloco = False
                i += 1
                continue

        bloco_atual.append(linha)
        i += 1

    if bloco_atual:
        blocos.append(bloco_atual)

    for b in blocos:
        ped = processar_bloco_unico_pedido(b, locais_dict, vendedor_padrao)
        if ped:
            pedidos.append(ped)

    return pd.DataFrame(pedidos)


def chave_duplicidade(cliente: str, endereco: str) -> tuple:
    cli_norm = remover_acentos(str(cliente).lower()).strip()
    rua, num, _, _ = separar_componentes_endereco(str(endereco))
    rua_norm = re.sub(
        r"^(rua|r\.|r|avenida|av\.|av|alameda|al\.|praca|praça|travessa|tv\.|beco)\s+",
        "",
        remover_acentos(rua.lower()),
        flags=re.IGNORECASE
    ).strip()
    return (cli_norm, f"{rua_norm}_{num}")


def adicionar_pedidos_na_sessao(df_novos: pd.DataFrame):
    if df_novos.empty:
        return 0, []

    df_atual = st.session_state.get("df_pedidos", pd.DataFrame())
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
            st.session_state["df_pedidos"] = df_para_entrar.reset_index(drop=True)
        else:
            st.session_state["df_pedidos"] = pd.concat([df_atual, df_para_entrar], ignore_index=True)

    return len(linhas_validas), duplicados_ignorados


def montar_linha_cliente(row) -> str:
    partes = [str(row["Cliente"]).strip().upper()]

    vend = str(row.get("Vendedor", "")).strip().upper()
    if vend and vend not in ("NONE", "NAN"):
        partes.append(f"[{vend}]")

    try:
        pct = int(row.get("Pacotes", 1))
    except (ValueError, TypeError):
        pct = 1
    if pct > 1:
        partes.append(f"({pct}PCT)")

    obs = str(row.get("Observacao", "")).strip().upper()
    if obs and obs not in ("NONE", "NAN"):
        partes.append(f"({obs})")

    return " ".join(partes)


# ================= MOTOR MATEMÁTICO DE DIVISÃO E OTIMIZAÇÃO DE ROTAS =================
def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def dividir_pedidos_por_cota(df: pd.DataFrame, nomes_rotas: list, cotas_rotas: list, lat_saida: float, lon_saida: float) -> list:
    n = len(df)
    k = len(nomes_rotas)
    if k <= 1 or n <= 1:
        return [nomes_rotas[0]] * n

    coords = []
    for _, row in df.iterrows():
        lat = row.get("Lat")
        lon = row.get("Lon")
        if pd.isna(lat) or pd.isna(lon) or lat is None or lon is None:
            lat, lon = geocodificar_endereco_rua(str(row.get("Endereco", "")))
        coords.append((float(lat), float(lon)))

    angulos = []
    for idx, (lat, lon) in enumerate(coords):
        ang = math.atan2(lat - lat_saida, lon - lon_saida)
        angulos.append((ang, idx))
    angulos.sort()

    centros = []
    for r_idx in range(k):
        pos_escolhida = int((r_idx + 0.5) * n / k)
        pos_escolhida = min(max(0, pos_escolhida), n - 1)
        centros.append(coords[angulos[pos_escolhida][1]])

    atribuicao = [-1] * n
    vagas = list(cotas_rotas)

    ordem_prioridade = []
    for i, (lat, lon) in enumerate(coords):
        dists = sorted([distancia_km(lat, lon, c[0], c[1]) for c in centros])
        penalidade = (dists[1] - dists[0]) if len(dists) > 1 else dists[0]
        ordem_prioridade.append((-penalidade, i))
    ordem_prioridade.sort()

    for _, idx_ponto in ordem_prioridade:
        lat, lon = coords[idx_ponto]
        opcoes = sorted(
            [(distancia_km(lat, lon, centros[r][0], centros[r][1]), r) for r in range(k) if vagas[r] > 0]
        )
        rota_escolhida = opcoes[0][1]
        atribuicao[idx_ponto] = rota_escolhida
        vagas[rota_escolhida] -= 1

    for _ in range(40):
        novos_centros = []
        for r in range(k):
            pts_r = [coords[i] for i in range(n) if atribuicao[i] == r]
            if pts_r:
                novos_centros.append((
                    sum(p[0] for p in pts_r) / len(pts_r),
                    sum(p[1] for p in pts_r) / len(pts_r)
                ))
            else:
                novos_centros.append(centros[r])
        centros = novos_centros

        melhorou = False
        for i in range(n):
            for j in range(i + 1, n):
                ri, rj = atribuicao[i], atribuicao[j]
                if ri != rj:
                    custo_atual = (
                        distancia_km(coords[i][0], coords[i][1], centros[ri][0], centros[ri][1]) ** 2 +
                        distancia_km(coords[j][0], coords[j][1], centros[rj][0], centros[rj][1]) ** 2
                    )
                    custo_troca = (
                        distancia_km(coords[i][0], coords[i][1], centros[rj][0], centros[rj][1]) ** 2 +
                        distancia_km(coords[j][0], coords[j][1], centros[ri][0], centros[ri][1]) ** 2
                    )
                    if custo_troca + 1e-6 < custo_atual:
                        atribuicao[i], atribuicao[j] = rj, ri
                        melhorou = True
        if not melhorou:
            break

    return [nomes_rotas[r] for r in atribuicao]


def obter_matriz_osrm(pontos_lat_lon: list):
    m = len(pontos_lat_lon)
    try:
        coords_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in pontos_lat_lon])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration,distance"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and "durations" in data:
                durations = data["durations"]
                distances = data.get("distances", durations)
                return durations, distances
    except Exception:
        pass

    matriz_dist = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(m):
            if i != j:
                d_km = distancia_km(
                    pontos_lat_lon[i][0], pontos_lat_lon[i][1],
                    pontos_lat_lon[j][0], pontos_lat_lon[j][1]
                ) * 1.35
                matriz_dist[i][j] = d_km * 1000.0
    return matriz_dist, matriz_dist


def otimizar_sequencia_grupo(indices_grupo: list, nodo_anterior: int, matriz_custo: list) -> list:
    if len(indices_grupo) <= 1:
        return list(indices_grupo)

    restantes = set(indices_grupo)
    rota = []
    atual = nodo_anterior

    while restantes:
        prox = min(restantes, key=lambda x: matriz_custo[atual][x] if matriz_custo[atual][x] is not None else 1e9)
        rota.append(prox)
        restantes.remove(prox)
        atual = prox

    melhorou = True
    n_r = len(rota)
    while melhorou:
        melhorou = False
        for i in range(n_r - 1):
            for j in range(i + 1, n_r):
                nova_rota = rota[:i] + rota[i:j + 1][::-1] + rota[j + 1:]

                def custo_sequencia(seq):
                    c = matriz_custo[nodo_anterior][seq[0]]
                    for k in range(len(seq) - 1):
                        c += matriz_custo[seq[k]][seq[k + 1]]
                    return c

                if custo_sequencia(nova_rota) + 1e-4 < custo_sequencia(rota):
                    rota = nova_rota
                    melhorou = True

    return rota


def otimizar_rota_unica(df_rota: pd.DataFrame, lat_saida: float, lon_saida: float):
    if df_rota.empty:
        return df_rota, 0.0

    df_trab = df_rota.copy().reset_index(drop=True)

    pontos = [(lat_saida, lon_saida)]
    for idx, row in df_trab.iterrows():
        lat, lon = row.get("Lat"), row.get("Lon")
        if pd.isna(lat) or pd.isna(lon) or lat is None or lon is None:
            lat, lon = geocodificar_endereco_rua(str(row.get("Endereco", "")))
            df_trab.at[idx, "Lat"] = lat
            df_trab.at[idx, "Lon"] = lon
        pontos.append((float(lat), float(lon)))

    matriz_tempo, matriz_metros = obter_matriz_osrm(pontos)

    primeiros = []
    normais = []
    ultimos = []

    for idx, row in df_trab.iterrows():
        nodo_osrm = idx + 1
        pos = str(row.get("Posicao", "Normal")).upper().strip()
        if pos == "PRIMEIRO":
            primeiros.append(nodo_osrm)
        elif pos in ("ÚLTIMO", "ULTIMO"):
            ultimos.append(nodo_osrm)
        else:
            normais.append(nodo_osrm)

    sequencia_final = []
    nodo_atual = 0

    if primeiros:
        seq_p = otimizar_sequencia_grupo(primeiros, nodo_atual, matriz_tempo)
        sequencia_final.extend(seq_p)
        nodo_atual = seq_p[-1]

    if normais:
        seq_n = otimizar_sequencia_grupo(normais, nodo_atual, matriz_tempo)
        if ultimos and len(seq_n) >= 2:
            alvo_final = ultimos[0]
            melhorou = True
            while melhorou:
                melhorou = False
                for i in range(len(seq_n) - 1):
                    for j in range(i + 1, len(seq_n)):
                        tentativa = seq_n[:i] + seq_n[i:j + 1][::-1] + seq_n[j + 1:]

                        def custo_com_fim(seq):
                            c = matriz_tempo[nodo_atual][seq[0]]
                            for k in range(len(seq) - 1):
                                c += matriz_tempo[seq[k]][seq[k + 1]]
                            c += matriz_tempo[seq[-1]][alvo_final]
                            return c

                        if custo_com_fim(tentativa) + 1e-4 < custo_com_fim(seq_n):
                            seq_n = tentativa
                            melhorou = True

        sequencia_final.extend(seq_n)
        nodo_atual = seq_n[-1]

    if ultimos:
        seq_u = otimizar_sequencia_grupo(ultimos, nodo_atual, matriz_tempo)
        sequencia_final.extend(seq_u)

    metros_totais = 0.0
    ant = 0
    for nodo in sequencia_final:
        metros_totais += (matriz_metros[ant][nodo] or 0.0)
        ant = nodo
    km_total = round(metros_totais / 1000.0, 1)

    indices_df = [nodo - 1 for nodo in sequencia_final]
    df_ordenado = df_trab.iloc[indices_df].copy().reset_index(drop=True)
    df_ordenado["Ordem"] = [f"{i + 1}º" for i in range(len(df_ordenado))]

    return df_ordenado, km_total


def recalcular_todas_as_rotas(df_com_rotas: pd.DataFrame, ordem_nomes_rotas: list, lat_s: float, lon_s: float):
    dfs_otimizados = []
    resumo_km = {}

    for nome_r in ordem_nomes_rotas:
        sub_df = df_com_rotas[df_com_rotas["Rota"] == nome_r].copy()
        if not sub_df.empty:
            sub_otim, km_r = otimizar_rota_unica(sub_df, lat_s, lon_s)
            dfs_otimizados.append(sub_otim)
            resumo_km[nome_r] = km_r
        else:
            resumo_km[nome_r] = 0.0

    if dfs_otimizados:
        df_final = pd.concat(dfs_otimizados, ignore_index=True)
    else:
        df_final = df_com_rotas.copy()

    return df_final, resumo_km, (lat_s, lon_s)


def formatar_titulo_rota(nome: str) -> str:
    limpo = nome.strip().upper()
    if not limpo:
        return "ROTA"
    if not limpo.startswith("ROTA"):
        return f"ROTA {limpo}"
    return limpo


def renderizar_mapa_rotas(df_rotas: pd.DataFrame, nomes_rotas: list, coord_partida: tuple, desc_partida: str):
    lat_p, lon_p = coord_partida
    marcadores_js = []
    linhas_js = []

    end_p_safe = str(desc_partida).replace("'", "").replace('"', "")
    marcadores_js.append(f"""
        L.marker([{lat_p}, {lon_p}], {{
            icon: L.divIcon({{
                className: 'custom-pin',
                html: '<div style="background:#111;color:#fff;border:2px solid #fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:15px;box-shadow:0 2px 5px rgba(0,0,0,0.5);">🏠</div>',
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            }})
        }}).addTo(map).bindPopup('<b>Ponto de Partida</b><br>{end_p_safe}');
    """)

    for r_idx, nome_r in enumerate(nomes_rotas):
        cor = CORES_ROTAS[r_idx % len(CORES_ROTAS)]
        sub = df_rotas[df_rotas["Rota"] == nome_r]
        if sub.empty:
            continue

        pts_linha = [[lat_p, lon_p]]
        for stop_idx, (_, row) in enumerate(sub.iterrows(), start=1):
            lat, lon = row.get("Lat"), row.get("Lon")
            if pd.isna(lat) or pd.isna(lon) or lat is None or lon is None:
                continue
            pts_linha.append([float(lat), float(lon)])
            cliente_safe = montar_linha_cliente(row).replace("'", "").replace('"', "")
            end_safe = str(row.get("Endereco", "")).replace("'", "").replace('"', "")
            rota_safe = formatar_titulo_rota(nome_r).replace("'", "")

            marcadores_js.append(f"""
                L.marker([{float(lat)}, {float(lon)}], {{
                    icon: L.divIcon({{
                        className: 'custom-pin',
                        html: '<div style="background:{cor};color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;box-shadow:0 2px 4px rgba(0,0,0,0.4);">{stop_idx}</div>',
                        iconSize: [26, 26],
                        iconAnchor: [13, 13]
                    }})
                }}).addTo(map).bindPopup('<b>{rota_safe} - {stop_idx}ª Parada</b><br>{cliente_safe}<br><small>{end_safe}</small>');
            """)

        linhas_js.append(f"""
            L.polyline({json.dumps(pts_linha)}, {{color: '{cor}', weight: 4, opacity: 0.8}}).addTo(map);
        """)

    html_mapa = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head>
    <body style="margin:0;padding:0;">
        <div id="map" style="width:100%;height:420px;border-radius:10px;"></div>
        <script>
            var map = L.map('map').setView([{lat_p}, {lon_p}], 12);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap'
            }}).addTo(map);
            {"".join(linhas_js)}
            {"".join(marcadores_js)}
        </script>
    </body>
    </html>
    """
    components.html(html_mapa, height=430)


# ================= INICIALIZAÇÃO =================
config_salva = carregar_config()

if "df_pedidos" not in st.session_state:
    st.session_state["df_pedidos"] = pd.DataFrame()

if "df_rotas_calculadas" not in st.session_state:
    st.session_state["df_rotas_calculadas"] = pd.DataFrame()

if "nomes_rotas_ativas" not in st.session_state:
    st.session_state["nomes_rotas_ativas"] = []

if "resumo_km_rotas" not in st.session_state:
    st.session_state["resumo_km_rotas"] = {}

if "coord_partida_atual" not in st.session_state:
    st.session_state["coord_partida_atual"] = (-19.9167, -43.9345)

if "contador_form" not in st.session_state:
    st.session_state["contador_form"] = 0

if "avisos_duplicados" not in st.session_state:
    st.session_state["avisos_duplicados"] = []

st.title("🛵 Gerador de Rotas")

# --- BARRA LATERAL: CONFIGURAÇÕES E VALIDAÇÃO DE PARTIDA ---
with st.sidebar:
    st.header("📍 Ponto de Partida")
    ponto_partida = st.text_input(
        "Bairro, Rua+Nº ou CEP de saída:",
        value=config_salva.get("ponto_partida", "Bairro Maria Goretti, Belo Horizonte, MG"),
        help="Pode digitar apenas o bairro (ex: 'Bairro Maria Goretti' ou 'Savassi'), uma rua com número ou um CEP."
    )

    partida_ok, desc_partida_validada, lat_partida, lon_partida = validar_e_geocodificar_partida(ponto_partida)
    if partida_ok:
        st.success(f"✅ **Partida localizada:**\n{desc_partida_validada}")
    else:
        st.error(desc_partida_validada)

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

if (
    partida_ok
    and not st.session_state["df_rotas_calculadas"].empty
    and st.session_state["coord_partida_atual"] != (lat_partida, lon_partida)
):
    df_reotim, novo_km, nova_coord = recalcular_todas_as_rotas(
        st.session_state["df_rotas_calculadas"],
        st.session_state["nomes_rotas_ativas"],
        lat_partida,
        lon_partida
    )
    st.session_state["df_rotas_calculadas"] = df_reotim
    st.session_state["resumo_km_rotas"] = novo_km
    st.session_state["coord_partida_atual"] = nova_coord

# --- PASSO 1: ADICIONAR PEDIDOS ---
st.subheader("1️⃣ Adicionar Pedidos")

texto_pedidos = st.text_area(
    "Cole os pedidos abaixo (aceita mensagens copiadas direto do Telegram/WhatsApp com data e hora):",
    height=200,
    key=f"texto_pedidos_{st.session_state['contador_form']}",
    placeholder=(
        "Exemplo:\n[14/10/2026 13:53] 2K: Kaique inacio\n25 g Gold\nGranja de Freitas rua São Vicente 530\n\n"
        "Leticia Guedes\nPacote 1;\n10g skunk wolf\nAv silviano brandoa 228 floresta"
    )
)
vendedor_lote = st.text_input(
    "Sigla do Vendedor `[ ]` para os pedidos acima:",
    key=f"vendedor_lote_{st.session_state['contador_form']}",
    placeholder="Ex: 2T, VG, NK"
)

if st.button("🔍 Adicionar à Lista", type="primary", use_container_width=True):
    if texto_pedidos.strip():
        with st.spinner("Extraindo pedidos, filtrando mensagens do Telegram e buscando CEPs..."):
            df_extraidos = extrair_pedidos_brutos(texto_pedidos, locais_config, vendedor_lote)
            if not df_extraidos.empty:
                qtd_add, lista_dups = adicionar_pedidos_na_sessao(df_extraidos)
                st.session_state["avisos_duplicados"] = lista_dups
                st.session_state["contador_form"] += 1
                st.rerun()
            else:
                st.warning("⚠️ Não foi possível identificar um endereço válido no texto colado.")
    else:
        st.warning("Cole pelo menos um pedido antes de clicar em adicionar.")

if st.session_state.get("avisos_duplicados"):
    dups_str = "\n".join([f"- **{d}**" for d in st.session_state["avisos_duplicados"]])
    st.warning(
        f"🚫 **{len(st.session_state['avisos_duplicados'])} pedido(s) com mesmo Nome e Endereço já estavam na lista e não foram inseridos duas vezes:**\n{dups_str}"
    )
    if st.button("✖️ Fechar aviso de duplicados"):
        st.session_state["avisos_duplicados"] = []
        st.rerun()

# --- PASSO 2: TABELA DE CONFERÊNCIA, EDIÇÃO E EXCLUSÃO ---
if not st.session_state["df_pedidos"].empty:
    st.divider()
    total_pedidos = len(st.session_state["df_pedidos"])
    st.subheader(f"2️⃣ Conferência dos Pedidos ({total_pedidos} na lista)")

    df_atual = st.session_state["df_pedidos"].copy()
    if "Excluir" not in df_atual.columns:
        df_atual.insert(0, "Excluir", False)
    if "Opcoes_Endereco" not in df_atual.columns:
        df_atual["Opcoes_Endereco"] = "[]"

    linhas_ambiguas = []
    for idx_amb, row_amb in df_atual.iterrows():
        try:
            opcoes_lista = json.loads(row_amb.get("Opcoes_Endereco", "[]") or "[]")
        except Exception:
            opcoes_lista = []
        if len(opcoes_lista) > 1:
            linhas_ambiguas.append((idx_amb, row_amb["Cliente"], opcoes_lista))

    if linhas_ambiguas:
        st.warning(
            f"🏘️ **Atenção: {len(linhas_ambiguas)} pedido(s) possuem rua que existe em mais de um bairro!** "
            "Escolha abaixo qual é o bairro correto de cada cliente:"
        )
        for idx_amb, nome_cli_amb, opcoes_lista in linhas_ambiguas:
            col_sel, col_btn_amb = st.columns([3, 1])
            with col_sel:
                escolha_end = st.selectbox(
                    f"Escolha o bairro/endereço correto para **{nome_cli_amb}**:",
                    options=opcoes_lista,
                    key=f"sel_amb_{idx_amb}"
                )
            with col_btn_amb:
                st.write("")
                if st.button(f"✅ Confirmar ({nome_cli_amb})", key=f"btn_amb_{idx_amb}", use_container_width=True):
                    lat_novo, lon_novo = geocodificar_endereco_rua(escolha_end)
                    df_atual.at[idx_amb, "Endereco"] = escolha_end
                    df_atual.at[idx_amb, "Status"] = "✅ OK"
                    df_atual.at[idx_amb, "Lat"] = lat_novo
                    df_atual.at[idx_amb, "Lon"] = lon_novo
                    df_atual.at[idx_amb, "Opcoes_Endereco"] = "[]"
                    st.session_state["df_pedidos"] = df_atual
                    st.rerun()

    problemas = df_atual[df_atual["Status"] != "✅ OK"]
    if not problemas.empty:
        st.warning(
            f"⚠️ **{len(problemas)} endereço(s) precisam da sua atenção!** "
            "Escolha o bairro acima ou corrija o endereço dando dois cliques na tabela abaixo."
        )
    else:
        st.success(f"✅ Todos os {total_pedidos} endereços foram localizados com Bairro e CEP!")

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

    endereco_mudou = False
    for idx in df_editado.index:
        if idx in df_atual.index and df_editado.at[idx, "Endereco"] != df_atual.at[idx, "Endereco"]:
            end_novo, novo_status, lat, lon, novas_opcoes = buscar_endereco_completo(df_editado.at[idx, "Endereco"])
            df_editado.at[idx, "Endereco"] = end_novo
            df_editado.at[idx, "Status"] = novo_status
            df_editado.at[idx, "Lat"] = lat
            df_editado.at[idx, "Lon"] = lon
            df_editado.at[idx, "Opcoes_Endereco"] = json.dumps(novas_opcoes, ensure_ascii=False)
            endereco_mudou = True

    st.session_state["df_pedidos"] = df_editado
    if endereco_mudou:
        st.rerun()

    col_acao1, col_acao2, col_acao3 = st.columns(3)

    with col_acao1:
        if st.button(
            "🔍 Buscar CEP após Editar Tabela",
            use_container_width=True,
            help="Use caso tenha corrigido algum endereço na tabela e queira rebuscar o CEP e Bairro."
        ):
            with st.spinner("Buscando CEP e Bairro dos endereços..."):
                for idx, row in df_editado.iterrows():
                    end_novo, novo_status, lat, lon, novas_opcoes = buscar_endereco_completo(row["Endereco"])
                    df_editado.at[idx, "Endereco"] = end_novo
                    df_editado.at[idx, "Status"] = novo_status
                    df_editado.at[idx, "Lat"] = lat
                    df_editado.at[idx, "Lon"] = lon
                    df_editado.at[idx, "Opcoes_Endereco"] = json.dumps(novas_opcoes, ensure_ascii=False)
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
                st.session_state["df_rotas_calculadas"] = pd.DataFrame()
                st.rerun()
            else:
                st.toast("Marque a caixinha '🗑️' na tabela ao lado do cliente que deseja remover.")

    with col_acao3:
        if st.button("🧹 Limpar Lista", use_container_width=True):
            st.session_state["df_pedidos"] = pd.DataFrame()
            st.session_state["df_rotas_calculadas"] = pd.DataFrame()
            st.session_state["avisos_duplicados"] = []
            st.rerun()

    with st.expander("👀 Ver prévia dos pedidos (Nomes e Endereços)", expanded=True):
        linhas_previa = []
        for _, row in df_editado.iterrows():
            linhas_previa.append(f"{row['Endereco']}\n{montar_linha_cliente(row)}")
        st.code("\n\n".join(linhas_previa), language="text", wrap_lines=True)

    # --- PASSO 3: DIVISÃO E CÁLCULO DAS ROTAS ---
    st.divider()
    st.subheader("3️⃣ Dividir e Calcular Melhores Rotas")

    qtd_rotas = st.radio(
        "Em quantas rotas deseja dividir os pedidos?",
        options=[1, 2, 3, 4],
        index=1 if total_pedidos >= 2 else 0,
        horizontal=True
    )

    base_por_rota = total_pedidos // qtd_rotas
    sobra = total_pedidos % qtd_rotas
    sugestoes_padrao = [base_por_rota + (1 if i < sobra else 0) for i in range(qtd_rotas)]
    nomes_sugeridos = ["ROTA FP", "ROTA LE", "ROTA 3", "ROTA 4"]

    cols_rotas = st.columns(qtd_rotas)
    nomes_escolhidos = []
    cotas_escolhidas = []

    for i in range(qtd_rotas):
        with cols_rotas[i]:
            nome_r = st.text_input(
                f"Nome da Rota {i + 1}:",
                value=nomes_sugeridos[i],
                key=f"nome_rota_{i}_{qtd_rotas}"
            )
            cota_r = st.number_input(
                f"Nº de Pedidos ({nome_r}):",
                min_value=0,
                max_value=total_pedidos,
                value=sugestoes_padrao[i],
                step=1,
                key=f"cota_rota_{i}_{qtd_rotas}_{total_pedidos}"
            )
            nomes_escolhidos.append(formatar_titulo_rota(nome_r))
            cotas_escolhidas.append(int(cota_r))

    soma_cotas = sum(cotas_escolhidas)
    if soma_cotas != total_pedidos:
        diferenca = total_pedidos - soma_cotas
        if diferenca > 0:
            st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você tem **{total_pedidos}** na lista (faltam distribuir **{diferenca}**).")
        else:
            st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você só tem **{total_pedidos}** na lista (passou **{abs(diferenca)}**).")

    if not partida_ok:
        st.error("⚠️ Corrija o Ponto de Partida na barra lateral esquerda antes de gerar as rotas.")

    if st.button(
        "🚀 Gerar e Otimizar Rotas",
        type="primary",
        use_container_width=True,
        disabled=(soma_cotas != total_pedidos or not partida_ok)
    ):
        with st.spinner("Agrupando regiões e calculando a melhor sequência rua a rua..."):
            df_para_dividir = df_editado.copy().reset_index(drop=True)

            nomes_unicos = []
            for idx_n, nm in enumerate(nomes_escolhidos):
                if nm in nomes_unicos:
                    nm = f"{nm} ({idx_n + 1})"
                nomes_unicos.append(nm)

            rotas_atribuidas = dividir_pedidos_por_cota(
                df_para_dividir,
                nomes_unicos,
                cotas_escolhidas,
                lat_partida,
                lon_partida
            )
            df_para_dividir["Rota"] = rotas_atribuidas

            df_otimizado, resumo_km, coord_p = recalcular_todas_as_rotas(
                df_para_dividir,
                nomes_unicos,
                lat_partida,
                lon_partida
            )

            st.session_state["df_rotas_calculadas"] = df_otimizado
            st.session_state["nomes_rotas_ativas"] = nomes_unicos
            st.session_state["resumo_km_rotas"] = resumo_km
            st.session_state["coord_partida_atual"] = coord_p
            st.rerun()

# --- PASSO 4: ROTAS PRONTAS, TROCA ENTRE ROTAS E TEXTO PARA COPIAR ---
if not st.session_state["df_rotas_calculadas"].empty:
    st.divider()
    st.subheader("4️⃣ Rotas Otimizadas e Ajuste Entre Rotas")

    df_rotas = st.session_state["df_rotas_calculadas"].copy()
    nomes_ativas = st.session_state["nomes_rotas_ativas"]
    resumo_km = st.session_state["resumo_km_rotas"]

    st.caption(
        "💡 **Quer passar um pedido de uma rota para outra ou mudar quem é o PRIMEIRO/ÚLTIMO?** "
        "Basta alterar a coluna **'Rota'** ou **'Posição'** na tabela abaixo que o sistema recalcula a melhor ordem das rotas automaticamente!"
    )

    df_rotas_edit = st.data_editor(
        df_rotas,
        use_container_width=True,
        hide_index=True,
        column_order=["Rota", "Ordem", "Posicao", "Cliente", "Vendedor", "Pacotes", "Observacao", "Endereco"],
        column_config={
            "Rota": st.column_config.SelectboxColumn(
                "🔄 Rota (Trocar)",
                options=nomes_ativas,
                required=True,
                width="medium"
            ),
            "Ordem": st.column_config.TextColumn("Ordem", disabled=True, width="small"),
            "Posicao": st.column_config.SelectboxColumn(
                "Posição",
                options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                required=True,
                width="small"
            ),
            "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
            "Vendedor": st.column_config.TextColumn("Vend. [ ]", width="small"),
            "Pacotes": st.column_config.NumberColumn("PCT", min_value=1, max_value=10, step=1, width="small"),
            "Observacao": st.column_config.TextColumn("Obs ( )", width="small"),
            "Endereco": st.column_config.TextColumn("Endereço", width="large"),
        }
    )

    mudou_rota_ou_pos = (
        not df_rotas_edit["Rota"].equals(df_rotas["Rota"]) or
        not df_rotas_edit["Posicao"].equals(df_rotas["Posicao"])
    )

    if mudou_rota_ou_pos and partida_ok:
        with st.spinner("Recalculando a melhor sequência das rotas após a alteração..."):
            df_reotimizado, novo_km, coord_p = recalcular_todas_as_rotas(
                df_rotas_edit,
                nomes_ativas,
                lat_partida,
                lon_partida
            )
            st.session_state["df_rotas_calculadas"] = df_reotimizado
            st.session_state["resumo_km_rotas"] = novo_km
            st.session_state["coord_partida_atual"] = coord_p
            st.rerun()
    else:
        df_rotas_edit["Cliente"] = df_rotas_edit["Cliente"].astype(str).str.upper()
        st.session_state["df_rotas_calculadas"] = df_rotas_edit

    with st.expander("🗺️ Ver Mapa das Rotas (Pinos Numerados por Ordem de Entrega)", expanded=True):
        renderizar_mapa_rotas(
            st.session_state["df_rotas_calculadas"],
            nomes_ativas,
            st.session_state["coord_partida_atual"],
            desc_partida_validada
        )

    st.markdown("### 📋 Textos Prontos para Copiar (WhatsApp / Telegram)")
    st.caption("Clique no ícone de copiar no canto superior direito de cada caixa preta abaixo:")

    cols_texto = st.columns(min(len(nomes_ativas), 2))

    for idx_r, nome_r in enumerate(nomes_ativas):
        sub_rota = st.session_state["df_rotas_calculadas"][
            st.session_state["df_rotas_calculadas"]["Rota"] == nome_r
        ]
        col_atual = cols_texto[idx_r % len(cols_texto)]

        with col_atual:
            qtd_entregas = len(sub_rota)
            total_pct_rota = int(sub_rota["Pacotes"].sum()) if not sub_rota.empty else 0
            km_desta_rota = resumo_km.get(nome_r, 0.0)

            st.markdown(
                f"**{nome_r}** — `{qtd_entregas} entregas` | `{total_pct_rota} pacotes` | `~{km_desta_rota} km`"
            )

            blocos_paradas = [nome_r]
            for _, row_p in sub_rota.iterrows():
                blocos_paradas.append(f"{row_p['Endereco']}\n{montar_linha_cliente(row_p)}")

            texto_final_rota = "\n\n".join(blocos_paradas)
            st.code(texto_final_rota, language="text", wrap_lines=True)
