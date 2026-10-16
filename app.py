import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import re
import json
import os
import math
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from urllib.parse import quote
from io import BytesIO
from pypdf import PdfReader, PdfWriter, PageObject
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import portrait
from reportlab.lib.units import mm

st.set_page_config(page_title="Sistema de Rotas e Etiquetas", page_icon="🛵", layout="wide")

# CSS reforçado: impede "..." dentro dos botões e empilha colunas em janelas reduzidas
st.markdown("""
<style>
div.stButton > button,
div.stFormSubmitButton > button,
div.stDownloadButton > button {
    white-space: normal !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    height: auto !important;
    min-height: 2.8rem !important;
    padding: 0.5rem 0.6rem !important;
}

div.stButton > button *,
div.stFormSubmitButton > button *,
div.stDownloadButton > button * {
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

# ================= CONTROLE DE AUTENTICAÇÃO POR SENHA =================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Rotas & Etiquetas")
    st.markdown("Digite a senha de acesso para entrar no sistema.")

    with st.form("form_login"):
        senha_digitada = st.text_input("Senha:", type="password", placeholder="Digite a senha...")
        btn_entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if btn_entrar:
            if senha_digitada.strip() == "2k12345":
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("❌ Senha incorreta. Tente novamente.")

    st.stop()


# ================= CONSTANTES E MAPAS =================
ARQUIVO_CONFIG = "config_rotas.json"
NOMES_ARQUIVO_MODELO = ["Etiqueta.pdf", "etiqueta.pdf", "Modelo Etiqueta.pdf", "modelo_etiqueta.pdf"]

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

MAPA_BAIRROS_RMBH = {
    "vila da serra": "Nova Lima",
    "vale do sereno": "Nova Lima",
    "jardim canada": "Nova Lima",
    "alphaville": "Nova Lima",
    "vila castela": "Nova Lima",
    "vale dos cristais": "Nova Lima",
    "bosque da ribeira": "Nova Lima",
    "ouro velho": "Nova Lima",
    "eldorado": "Contagem",
    "novo eldorado": "Contagem",
    "parque sao joao": "Contagem",
    "jardim riacho": "Contagem",
    "riacho das pedras": "Contagem",
    "inconfidentes": "Contagem",
    "cidade industrial": "Contagem",
    "jardim industrial": "Contagem",
    "industrial": "Contagem",
    "agua branca": "Contagem",
    "nacional": "Contagem",
    "cabral": "Contagem",
    "kennedy": "Contagem",
    "ressaca": "Contagem",
    "amazonas": "Contagem",
    "alterosas": "Betim",
    "jardim alterosas": "Betim",
    "angola": "Betim",
    "filadelfia": "Betim",
    "ptb": "Betim",
    "citrolandia": "Betim",
    "sao benedito": "Santa Luzia",
    "palmital": "Santa Luzia",
    "conjunto cristina": "Santa Luzia",
    "justinopolis": "Ribeirão das Neves",
    "veneza": "Ribeirão das Neves",
    "sevilha": "Ribeirão das Neves",
    "nacoes unidas": "Sabará",
    "general carneiro": "Sabará",
    "roca grande": "Sabará",
}

COORDENADAS_BAIRROS_FIXOS = {
    "maria goretti": (-19.8808, -43.9178, "Bairro Santa Maria Goretti (Regional Nordeste), Belo Horizonte"),
    "santa maria goretti": (-19.8808, -43.9178, "Bairro Santa Maria Goretti (Regional Nordeste), Belo Horizonte"),
    "savassi": (-19.9369, -43.9366, "Bairro Savassi (Centro-Sul), Belo Horizonte"),
    "centro": (-19.9191, -43.9386, "Bairro Centro, Belo Horizonte"),
}

REGIONAIS_BH = {
    "centro-sul", "centro sul", "noroeste", "nordeste", "norte",
    "leste", "oeste", "pampulha", "venda nova", "barreiro"
}

PREFIXOS_RUA = (
    "rua ", "r. ", "r.", "r ", "av ", "av. ", "av.", "avenida ", "alameda ", "al. ", "al.",
    "praca ", "praça ", "travessa ", "tv. ", "tv.", "beco ", "rodovia ", "estrada ", "anel "
)

TITULOS_E_STOPWORDS_RUA = {
    "rua", "r", "avenida", "av", "alameda", "al", "praca", "travessa", "tv",
    "beco", "rodovia", "estrada", "anel", "de", "da", "do", "dos", "das", "e",
    "doutor", "dr", "dra", "professor", "prof", "profa", "presidente", "pres",
    "coronel", "cel", "general", "gen", "padre", "pe", "deputado", "dep",
    "senador", "sen", "governador", "gov", "engenheiro", "eng", "desembargador",
    "des", "dom", "dona", "conde", "visconde", "barao", "marques", "prefeito"
}

PALAVRAS_GENERICAS_BAIRRO = {
    "bairro", "vila", "jardim", "parque", "conjunto", "conj", "residencial",
    "condominio", "santa", "santo", "sao", "nossa", "senhora", "de", "da", "do", "dos", "das"
}

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


def detectar_cidade_rmbh(texto: str, bairro_dica: str = "") -> str:
    texto_norm = remover_acentos(texto.lower())
    for cid in CIDADES_RMBH:
        if re.search(rf"\b{cid}\b", texto_norm):
            return MAPA_NOMES_CIDADES.get(cid, cid.title())

    check_bairro = remover_acentos(f"{bairro_dica} {texto}".lower())
    for b_rmbh, cid_rmbh in MAPA_BAIRROS_RMBH.items():
        if re.search(rf"\b{re.escape(b_rmbh)}\b", check_bairro):
            return cid_rmbh

    return "Belo Horizonte"


def extrair_palavras_item(texto_linha: str) -> list:
    limpo = remover_acentos(texto_linha.lower())
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


def tokens_nucleo_rua(nome_rua: str) -> list:
    limpo = remover_acentos(str(nome_rua).lower())
    palavras = re.findall(r"[a-z0-9]+", limpo)
    nucleo = [p for p in palavras if p not in TITULOS_E_STOPWORDS_RUA and len(p) >= 2]
    if not nucleo:
        nucleo = [p for p in palavras if p not in ("rua", "r", "av", "avenida", "alameda", "praca", "travessa", "beco")]
    return nucleo


def similaridade_ruas(rua_digitada: str, rua_candidata: str) -> float:
    t_dig = tokens_nucleo_rua(rua_digitada)
    t_cand = tokens_nucleo_rua(rua_candidata)
    if not t_dig or not t_cand:
        return 0.0

    str_dig = " ".join(t_dig)
    str_cand = " ".join(t_cand)
    sim_frase = SequenceMatcher(None, str_dig, str_cand).ratio()

    notas_palavras = []
    for p_d in t_dig:
        melhor = max(SequenceMatcher(None, p_d, p_c).ratio() for p_c in t_cand)
        notas_palavras.append(melhor)

    media_palavras = sum(notas_palavras) / len(notas_palavras)
    menor_palavra = min(notas_palavras)

    if menor_palavra >= 0.80 and media_palavras >= 0.84:
        return max(sim_frase, media_palavras)

    if menor_palavra < 0.55 and len(t_dig) >= 2:
        return min(sim_frase, media_palavras) * 0.75

    return (sim_frase * 0.45) + (media_palavras * 0.55)


def similaridade_bairros(bairro_dica: str, bairro_candidato: str) -> float:
    if not bairro_dica or not bairro_candidato:
        return 0.0
    b1 = remover_acentos(bairro_dica.lower()).strip()
    b2 = remover_acentos(bairro_candidato.lower()).strip()
    if b1 == b2 or (len(b1) >= 4 and b1 in b2) or (len(b2) >= 4 and b2 in b1):
        return 1.0
    return SequenceMatcher(None, b1, b2).ratio()


def nome_bairro_partida_bate(bairro_buscado: str, bairro_retornado: str) -> bool:
    b_alvo = remover_acentos(bairro_buscado.lower()).strip()
    b_ret = remover_acentos(bairro_retornado.lower()).strip()
    if not b_alvo or not b_ret:
        return False
    if b_alvo in b_ret or b_ret in b_alvo:
        return True

    palavras_alvo = [p for p in re.findall(r"[a-z0-9]+", b_alvo) if p not in PALAVRAS_GENERICAS_BAIRRO]
    palavras_ret = [p for p in re.findall(r"[a-z0-9]+", b_ret) if p not in PALAVRAS_GENERICAS_BAIRRO]

    if not palavras_alvo:
        palavras_alvo = re.findall(r"[a-z0-9]+", b_alvo)
    if not palavras_ret:
        palavras_ret = re.findall(r"[a-z0-9]+", b_ret)

    if not palavras_alvo or not palavras_ret:
        return False

    for p_a in palavras_alvo:
        melhor = max(SequenceMatcher(None, p_a, p_r).ratio() for p_r in palavras_ret)
        if melhor < 0.78:
            return False
    return True


def identificar_locais_dos_itens(itens_pedido: list, locais_dict: dict):
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
    bruta = linha.strip()
    limpa = remover_acentos(bruta.lower()).strip(" ()[]")
    if not limpa or eh_subtitulo_ou_divisoria(bruta):
        return False
    if re.match(r"^\d+(?:[.,/]\d+)?\s*([a-z@#%]+\b)?", limpa):
        return True
    if re.match(r"^(pacote|pct)\s+[a-z0-9]+", limpa):
        return True
    return False


def eh_linha_endereco(linha: str, locais_dict: dict = None) -> bool:
    bruta = linha.strip()
    if not bruta:
        return False

    if bruta.startswith("(") and bruta.endswith(")"):
        return False

    linha_limpa = remover_acentos(bruta.lower())

    if re.match(r"^(endereco|end\.?|local|entrega)\s*[:\-]", linha_limpa):
        return True

    if eh_subtitulo_ou_divisoria(bruta) or bruta.endswith(";") or bruta.endswith(":"):
        return False

    for pal_proibida in PALAVRAS_NAO_ENDERECO:
        if re.match(rf"^{pal_proibida}\b", linha_limpa):
            return False

    if re.match(r"^\d+", linha_limpa):
        return False

    if linha_limpa.startswith(PREFIXOS_RUA):
        return True

    if re.search(r"\b(rua|avenida|av\.?|alameda|travessa|praca|rodovia)\s*[a-z]{2,}", linha_limpa) and re.search(r"\b(?:n\.?\s*)?\d{1,5}\b", linha_limpa):
        return True

    if re.search(r"\b\d+(?:[.,/]\d+)?\s*(g|gr|kg|ml|un|pct|x|@|#)\b", linha_limpa) or "@" in linha_limpa or "#" in linha_limpa:
        return False

    match_via_num = re.search(r"^([a-z\s.,'-]{3,}?)\s*(?:[,.]|\s+|\bn\.?\s*)(\d{1,5})\b", linha_limpa)
    if match_via_num:
        nome_antes_num = match_via_num.group(1).strip(" ,.-")
        palavras_todas = re.findall(r"[a-z]{2,}", linha_limpa)
        if len(palavras_todas) >= 2 and not texto_parece_produto_cadastrado(nome_antes_num, locais_dict):
            return True
        if len(nome_antes_num) >= 4 and not texto_parece_produto_cadastrado(nome_antes_num, locais_dict):
            return True

    return False


def eh_complemento_pos_endereco(linha: str, locais_dict: dict = None) -> bool:
    bruta = linha.strip()
    limpa = remover_acentos(bruta.lower())
    if not limpa or eh_subtitulo_ou_divisoria(bruta):
        return False
    if eh_linha_produto_clara(bruta, locais_dict) or texto_parece_produto_cadastrado(bruta, locais_dict):
        return False
    if re.match(r"^(cliente|nome|pedido|ped|mercadoria|itens?)\s*[:\-]", limpa):
        return False
    if re.match(r"^(cep|bairro|apto|ap\.?|apartamento|bloco|bl\.?|casa|condominio|ed\.?|edificio|proximo|prox|ref|referencia|academia|clube|loja|portaria)\b", limpa):
        return True
    if re.match(r"^\d{5}-?\d{3}$", limpa):
        return True
    for cid in CIDADES_RMBH:
        if re.search(rf"\b{cid}\b", limpa):
            return True
    for b_rmbh in MAPA_BAIRROS_RMBH:
        if re.search(rf"\b{re.escape(b_rmbh)}\b", limpa):
            return True
    if "no gps" in limpa or "centro de " in limpa or re.match(r"^(jardim|vila|parque|conjunto|santa|sao|santo|padre|nossa senhora|vereda|planalto|providencia|camargos|caicara|barro preto|sion|serra|ipiranga|cidade nova|rio branco|bonsucesso)\b", limpa):
        return True
    return False


def limpar_nome_cliente(linha: str) -> str:
    limpa = re.sub(r"^(cliente|nome|pedido|ped)\s*[:\-]?\s+", "", linha.strip(), flags=re.IGNORECASE)
    return limpa.strip(" .,-:").upper()


def pode_ser_nome_cliente(linha: str, locais_dict: dict = None) -> bool:
    bruta = linha.strip()
    limpa = remover_acentos(bruta.lower())
    if not limpa:
        return False
    if bruta.startswith("(") or eh_subtitulo_ou_divisoria(bruta) or bruta.endswith(";"):
        return False
    if re.match(r"^(mercadoria|item|itens|endereco|end\.?|local|entrega|obs)\s*[:\-]", limpa):
        return False
    if re.match(r"^\d+", limpa) or re.match(r"^(pacote|pct)\b", limpa):
        return False
    if texto_parece_produto_cadastrado(bruta, locais_dict):
        return False
    return True


def separar_componentes_endereco(endereco_bruto: str):
    end_limpo = str(endereco_bruto).strip()
    # Remove rótulos como "Endereço:", "End:", "Local:" mesmo com acento ou repetidos
    end_limpo = re.sub(r"\b(endere[cç]o|end\.?|local|entrega)\s*[:\-]?\s*", " ", end_limpo, flags=re.IGNORECASE).strip()
    # Remove observações entre parênteses como "(No gps pode apontar...)"
    end_limpo = re.sub(r"\([^)]*\)", " ", end_limpo)
    # Normaliza prefixo colado como "AV.PRESIDENTE" -> "Av. Presidente"
    end_limpo = re.sub(r"^(av|r|al|tv)\.([a-zA-Z])", r"\1. \2", end_limpo, flags=re.IGNORECASE)
    # Normaliza número com 'n' colado como "n300" ou "nº 300" -> " 300"
    end_limpo = re.sub(r"\b(?:n[º°.]?\s*)(\d{1,5})\b", r" \1", end_limpo, flags=re.IGNORECASE)

    cep_explicito = ""
    m_cep = re.search(r"\b(\d{5})-?(\d{3})\b", end_limpo)
    if m_cep:
        cep_explicito = f"{m_cep.group(1)}-{m_cep.group(2)}"
        end_limpo = end_limpo[:m_cep.start()] + " " + end_limpo[m_cep.end():]

    bairro_antes_da_rua = ""
    match_meio = re.search(
        r"^(.+?)\s+\b(rua|r\.|avenida|av\.|av|alameda|al\.|travessa|tv\.|praca|praça|beco|rodovia)\s+(.+)$",
        end_limpo,
        flags=re.IGNORECASE
    )
    if match_meio:
        possivel_bairro_antes = match_meio.group(1).strip(" ,.-:")
        if possivel_bairro_antes and not remover_acentos(possivel_bairro_antes.lower()).startswith(PREFIXOS_RUA):
            bairro_antes_da_rua = possivel_bairro_antes
            end_limpo = f"{match_meio.group(2)} {match_meio.group(3)}"

    match_num = re.search(r"(?:[,.]\s*|\s+)(\d{1,5})\b(.*)$", end_limpo)
    if match_num:
        rua = end_limpo[:match_num.start()].strip(" ,.-:")
        numero = match_num.group(1).strip()
        resto = match_num.group(2).strip(" ,.-:")
    else:
        rua = end_limpo.strip(" ,.-:")
        numero = ""
        resto = ""

    # Remove complementos de apartamento, bloco, sala, academia, clube, referência
    resto_limpo = re.sub(
        r"\b(ap\.?|apto\.?|apartamento|bl\.?|bloco|casa|sl\.?|sala|lj\.?|loja)\s*\d*[a-zA-Z]?\b",
        " ",
        resto,
        flags=re.IGNORECASE
    )
    resto_limpo = re.sub(
        r"\b(clube|academia|condominio|ed\.?|edificio|shopping|supermercado|igreja|escola|hospital)\b.*$",
        " ",
        resto_limpo,
        flags=re.IGNORECASE
    )
    resto_limpo = re.sub(r"\bbairro\s*[:\-]?\s*", " ", resto_limpo, flags=re.IGNORECASE)
    resto_limpo = re.sub(r"\bcentro\s+de\s+([a-zA-ZÀ-ÿ\s]+)", r"Centro, \1", resto_limpo, flags=re.IGNORECASE)

    cidade_detectada = detectar_cidade_rmbh(endereco_bruto, f"{bairro_antes_da_rua} {resto_limpo}")

    for cid in CIDADES_RMBH:
        resto_limpo = re.sub(rf"\b{cid}\b", " ", resto_limpo, flags=re.IGNORECASE)
        resto_limpo = re.sub(rf"\b{MAPA_NOMES_CIDADES[cid]}\b", " ", resto_limpo, flags=re.IGNORECASE)

    resto_limpo = re.sub(r"\b(mg|minas gerais|brasil)\b", " ", resto_limpo, flags=re.IGNORECASE)
    for reg in REGIONAIS_BH:
        resto_limpo = re.sub(rf"\b{re.escape(reg)}\b", " ", resto_limpo, flags=re.IGNORECASE)

    partes_resto = [p.strip(" ,.-/:") for p in re.split(r"[,/\-]", resto_limpo) if p.strip(" ,.-/:")]
    bairro_pos = partes_resto[0] if partes_resto else ""

    if bairro_antes_da_rua and bairro_pos:
        bairro_dica = bairro_antes_da_rua
    elif bairro_antes_da_rua:
        bairro_dica = bairro_antes_da_rua
    else:
        bairro_dica = bairro_pos

    # Se a rua não tiver prefixo (ex: "Tamoios", "Galba Veloso", "Dulce Maria"), preserva o nome limpo
    rua = re.sub(r"\s+", " ", rua).strip(" ,.-:")
    bairro_dica = re.sub(r"\s+", " ", bairro_dica).strip(" ,.-:")

    return rua, numero, bairro_dica, cidade_detectada


def dentro_perimetro_rmbh(lat: float, lon: float) -> bool:
    return (-20.40 <= lat <= -19.40) and (-44.60 <= lon <= -43.40)


def eh_regional_bh(nome_b: str) -> bool:
    if not nome_b:
        return False
    return remover_acentos(nome_b.lower()).strip() in REGIONAIS_BH


def formatar_via_com_prefixo(nome_via: str, rua_original_usuario: str = "") -> str:
    via = str(nome_via).strip()
    if not via:
        return ""
    via_norm = remover_acentos(via.lower())
    if via_norm.startswith(PREFIXOS_RUA):
        return via
    orig_norm = remover_acentos(str(rua_original_usuario).lower()).strip()
    if orig_norm.startswith(("av ", "av.", "avenida ")):
        return f"Avenida {via}"
    if orig_norm.startswith(("al ", "al.", "alameda ")):
        return f"Alameda {via}"
    if orig_norm.startswith(("praca ", "praça ")):
        return f"Praça {via}"
    if orig_norm.startswith(("tv ", "tv.", "travessa ")):
        return f"Travessa {via}"
    return f"Rua {via}"


@st.cache_data(ttl=86400, show_spinner=False)
def consultar_cep_direto(cep_digitos: str) -> dict:
    cep_limpo = re.sub(r"\D", "", str(cep_digitos))
    if len(cep_limpo) != 8:
        return {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RotasRMBH/3.0)"}

    # 1) BrasilAPI (muito rápida em servidores cloud internacionais)
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}", headers=headers, timeout=2.5)
        if r.status_code == 200:
            d = r.json()
            if d.get("street"):
                return {
                    "logradouro": d.get("street", ""),
                    "bairro": d.get("neighborhood", ""),
                    "localidade": d.get("city", ""),
                    "cep": f"{cep_limpo[:5]}-{cep_limpo[5:]}"
                }
    except Exception:
        pass

    # 2) OpenCEP
    try:
        r2 = requests.get(f"https://opencep.com/v1/{cep_limpo}.json", headers=headers, timeout=2.5)
        if r2.status_code == 200:
            d2 = r2.json()
            if d2.get("logradouro"):
                return {
                    "logradouro": d2.get("logradouro", ""),
                    "bairro": d2.get("bairro", ""),
                    "localidade": d2.get("localidade", ""),
                    "cep": d2.get("cep", f"{cep_limpo[:5]}-{cep_limpo[5:]}")
                }
    except Exception:
        pass

    # 3) ViaCEP
    try:
        r3 = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", headers=headers, timeout=2.5)
        if r3.status_code == 200:
            d3 = r3.json()
            if not d3.get("erro") and d3.get("logradouro"):
                return {
                    "logradouro": d3.get("logradouro", ""),
                    "bairro": d3.get("bairro", ""),
                    "localidade": d3.get("localidade", ""),
                    "cep": d3.get("cep", f"{cep_limpo[:5]}-{cep_limpo[5:]}")
                }
    except Exception:
        pass

    return {}


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_coordenada_bairro(nome_bairro_limpo: str, cidade: str):
    bairro_alvo_norm = remover_acentos(nome_bairro_limpo.lower()).strip()

    if bairro_alvo_norm in COORDENADAS_BAIRROS_FIXOS and remover_acentos(cidade.lower()) == "belo horizonte":
        lat_fixo, lon_fixo, desc_fixa = COORDENADAS_BAIRROS_FIXOS[bairro_alvo_norm]
        return True, desc_fixa, lat_fixo, lon_fixo

    headers = {"User-Agent": "GeradorRotasRMBH/3.0 (contato@geradorrotas.app)"}

    try:
        q_arc = f"Bairro {nome_bairro_limpo}, {cidade}, Minas Gerais, Brasil"
        url_arc = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_arc)}&category=Neighborhood,Locality,Subregion"
            f"&searchExtent=-44.50,-20.30,-43.50,-19.50"
            f"&outFields=Addr_type,PlaceName,Nbrhd,City,Postal&maxLocations=10&f=json"
        )
        resp_a = requests.get(url_arc, headers=headers, timeout=3.5)
        if resp_a.status_code == 200:
            cands = resp_a.json().get("candidates", [])
            for c in cands:
                if c.get("score", 0) >= 75:
                    lat_a = float(c["location"]["y"])
                    lon_a = float(c["location"]["x"])
                    if dentro_perimetro_rmbh(lat_a, lon_a):
                        atrib = c.get("attributes", {})
                        nome_b = atrib.get("PlaceName") or atrib.get("Nbrhd") or ""
                        if nome_bairro_partida_bate(nome_bairro_limpo, nome_b):
                            cid_a = atrib.get("City") or cidade
                            return True, f"Bairro {nome_b}, {cid_a} - MG", lat_a, lon_a
    except Exception:
        pass

    try:
        q_photon = f"{nome_bairro_limpo} {cidade} Minas Gerais"
        url_photon = f"https://photon.komoot.io/api/?q={quote(q_photon)}&lat=-19.9167&lon=-43.9345&limit=10"
        resp_p = requests.get(url_photon, headers=headers, timeout=3.5)
        if resp_p.status_code == 200:
            features = resp_p.json().get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                if props.get("osm_key") == "highway":
                    continue
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    lon_f, lat_f = float(coords[0]), float(coords[1])
                    nome_f = props.get("name", "")
                    if dentro_perimetro_rmbh(lat_f, lon_f) and nome_bairro_partida_bate(nome_bairro_limpo, nome_f):
                        cid_f = props.get("city", cidade)
                        return True, f"Bairro {nome_f}, {cid_f} - MG", lat_f, lon_f
    except Exception:
        pass

    try:
        q_nom = f"{nome_bairro_limpo}, {cidade}, Minas Gerais, Brasil"
        url_nom = (
            f"https://nominatim.openstreetmap.org/search"
            f"?q={quote(q_nom)}&format=jsonv2&addressdetails=1&limit=8&countrycodes=br"
        )
        resp = requests.get(url_nom, headers=headers, timeout=3.5)
        if resp.status_code == 200:
            for item in resp.json():
                if item.get("category") in ("highway", "amenity", "shop", "tourism", "building"):
                    continue
                lat_i, lon_i = float(item["lat"]), float(item["lon"])
                if not dentro_perimetro_rmbh(lat_i, lon_i):
                    continue
                end_det = item.get("address", {})
                suburb = end_det.get("suburb") or end_det.get("neighbourhood") or end_det.get("quarter") or item.get("name", "")
                if nome_bairro_partida_bate(nome_bairro_limpo, suburb):
                    cid_item = end_det.get("city") or end_det.get("town") or cidade
                    return True, f"Bairro {suburb}, {cid_item}", lat_i, lon_i
    except Exception:
        pass

    return False, "❌ Bairro não localizado em BH/Região. Confira a grafia ou digite uma rua/CEP.", None, None


@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar_endereco_rua(endereco_completo_texto: str):
    headers = {"User-Agent": "GeradorRotasRMBH/3.0"}
    try:
        q_geo = f"{endereco_completo_texto}, Minas Gerais, Brasil"
        url_arcgis = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_geo)}&searchExtent=-44.50,-20.30,-43.50,-19.50&maxLocations=1&f=json"
        )
        resp = requests.get(url_arcgis, headers=headers, timeout=3.5)
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
        url_ph = f"https://photon.komoot.io/api/?q={quote(endereco_completo_texto + ' MG')}&lat=-19.9167&lon=-43.9345&limit=1"
        resp_p = requests.get(url_ph, headers=headers, timeout=3.5)
        if resp_p.status_code == 200:
            feats = resp_p.json().get("features", [])
            if feats:
                coords = feats[0].get("geometry", {}).get("coordinates", [])
                if len(coords) == 2 and dentro_perimetro_rmbh(float(coords[1]), float(coords[0])):
                    return float(coords[1]), float(coords[0])
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
    if "lado par" in comp and (num % 2 != 0):
        return False
    if "lado impar" in comp and (num % 2 == 0):
        return False

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


@st.cache_data(ttl=86400, show_spinner=False)
def consultar_viacep_com_tolerancia(rua_original: str, rua_sem_prefixo: str, cidade: str) -> list:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RotasRMBH/3.0)"}
    termos_tentativa = []
    if len(rua_sem_prefixo) >= 3:
        termos_tentativa.append(rua_sem_prefixo)
    tokens = tokens_nucleo_rua(rua_sem_prefixo)
    if len(tokens) >= 2:
        combinado = f"{tokens[0]} {tokens[-1]}"
        if len(combinado) >= 4 and combinado not in termos_tentativa:
            termos_tentativa.append(combinado)
    for tk in sorted(tokens, key=len, reverse=True):
        if len(tk) >= 4 and tk not in termos_tentativa:
            termos_tentativa.append(tk)

    for termo in termos_tentativa[:3]:
        try:
            url_viacep = f"https://viacep.com.br/ws/MG/{quote(remover_acentos(cidade))}/{quote(remover_acentos(termo))}/json/"
            resp = requests.get(url_viacep, headers=headers, timeout=2.5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and len(dados) > 0:
                    filtrados = [
                        d for d in dados
                        if d.get("logradouro") and similaridade_ruas(rua_original, d.get("logradouro", "")) >= 0.68
                    ]
                    if filtrados:
                        return filtrados
        except Exception:
            pass
    return []


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_candidatos_multifonte(rua: str, numero: str, bairro_dica: str, cidade: str):
    """
    Busca candidatos de endereço em ArcGIS, Photon e Nominatim para garantir:
    1) Reconhecimento mesmo quando ViaCEP falha ou para ruas curtas ('Rua H');
    2) Detecção do bairro real (e não Regional 'Centro-Sul'/'Noroeste');
    3) Lista de opções de bairros quando a rua existe em mais de um bairro na RMBH.
    """
    headers = {"User-Agent": "GeradorRotasRMBH/3.0 (contato@geradorrotas.app)"}
    candidatos = []
    rua_Com_pref = formatar_via_com_prefixo(rua, rua)

    # 1) ArcGIS com todos os campos (StPreType, StName, StType, Nbrhd, District, City, Postal)
    try:
        q_arc = f"{rua_Com_pref}, {numero}, {bairro_dica}, {cidade}, Minas Gerais, Brasil".replace(", ,", ",")
        url_arc = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_arc)}&searchExtent=-44.50,-20.30,-43.50,-19.50"
            f"&outFields=StPreType,StName,StType,AddNum,Nbrhd,District,City,Postal,Match_addr&maxLocations=10&f=json"
        )
        r_arc = requests.get(url_arc, headers=headers, timeout=3.0)
        if r_arc.status_code == 200:
            for c in r_arc.json().get("candidates", []):
                if c.get("score", 0) < 72:
                    continue
                lat_c = float(c["location"]["y"])
                lon_c = float(c["location"]["x"])
                if not dentro_perimetro_rmbh(lat_c, lon_c):
                    continue
                at = c.get("attributes", {})
                pre = at.get("StPreType", "").strip()
                nm = at.get("StName", "").strip()
                suf = at.get("StType", "").strip()
                partes_v = [p for p in (pre, nm, suf) if p]
                via_arc = " ".join(partes_v).strip()
                if not via_arc:
                    continue
                if similaridade_ruas(rua, via_arc) < 0.68:
                    continue

                via_arc = formatar_via_com_prefixo(via_arc, rua)
                nbr = (at.get("Nbrhd") or "").strip()
                dist = (at.get("District") or "").strip()
                bairro_c = nbr if (nbr and not eh_regional_bh(nbr)) else (dist if not eh_regional_bh(dist) else "")
                cid_c = (at.get("City") or cidade).strip()
                cep_raw = re.sub(r"\D", "", str(at.get("Postal", "")))
                cep_c = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""

                candidatos.append({
                    "logradouro": via_arc,
                    "bairro": bairro_c,
                    "cidade": cid_c,
                    "cep": cep_c,
                    "lat": lat_c,
                    "lon": lon_c,
                    "fonte": "arcgis"
                })
    except Exception:
        pass

    # 2) Photon (OpenStreetMap) - excelente para achar todos os bairros reais em BH/Contagem/Nova Lima
    try:
        q_ph = f"{rua_Com_pref} {numero} {bairro_dica} {cidade} MG".strip()
        url_ph = f"https://photon.komoot.io/api/?q={quote(q_ph)}&lat=-19.9167&lon=-43.9345&limit=10"
        r_ph = requests.get(url_ph, headers=headers, timeout=3.0)
        if r_ph.status_code == 200:
            for feat in r_ph.json().get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [])
                rua_ph = props.get("street") or props.get("name") or ""
                if len(coords) == 2 and rua_ph and similaridade_ruas(rua, rua_ph) >= 0.68:
                    lon_p, lat_p = float(coords[0]), float(coords[1])
                    if not dentro_perimetro_rmbh(lat_p, lon_p):
                        continue
                    b_ph = props.get("suburb") or props.get("district") or props.get("locality") or ""
                    if eh_regional_bh(b_ph):
                        b_ph = ""
                    cid_ph = props.get("city") or props.get("town") or cidade
                    cep_raw = re.sub(r"\D", "", str(props.get("postcode", "")))
                    cep_ph = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""
                    candidatos.append({
                        "logradouro": formatar_via_com_prefixo(rua_ph, rua),
                        "bairro": b_ph,
                        "cidade": cid_ph,
                        "cep": cep_ph,
                        "lat": lat_p,
                        "lon": lon_p,
                        "fonte": "photon"
                    })
    except Exception:
        pass

    # 3) Se não tinha bairro informado ou ainda faltou bairro real, consulta Nominatim para listar bairros homônimos
    precisa_nominatim = (not bairro_dica) or all(not c.get("bairro") for c in candidatos)
    if precisa_nominatim:
        try:
            q_nom = f"{rua_Com_pref}, {cidade}, Minas Gerais, Brasil"
            url_nom = (
                f"https://nominatim.openstreetmap.org/search"
                f"?q={quote(q_nom)}&format=jsonv2&addressdetails=1&limit=10&countrycodes=br"
            )
            r_nom = requests.get(url_nom, headers=headers, timeout=3.0)
            if r_nom.status_code == 200:
                for item in r_nom.json():
                    lat_n, lon_n = float(item["lat"]), float(item["lon"])
                    if not dentro_perimetro_rmbh(lat_n, lon_n):
                        continue
                    ed = item.get("address", {})
                    via_n = ed.get("road") or item.get("name") or ""
                    if not via_n or similaridade_ruas(rua, via_n) < 0.68:
                        continue
                    b_n = ed.get("suburb") or ed.get("neighbourhood") or ed.get("quarter") or ""
                    if eh_regional_bh(b_n):
                        b_n = ""
                    cid_n = ed.get("city") or ed.get("town") or ed.get("municipality") or cidade
                    cep_raw = re.sub(r"\D", "", str(ed.get("postcode", "")))
                    cep_n = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""
                    candidatos.append({
                        "logradouro": formatar_via_com_prefixo(via_n, rua),
                        "bairro": b_n,
                        "cidade": cid_n,
                        "cep": cep_n,
                        "lat": lat_n,
                        "lon": lon_n,
                        "fonte": "nominatim"
                    })
        except Exception:
            pass

    return candidatos


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_endereco_completo(endereco_bruto: str):
    if not str(endereco_bruto).strip():
        return "", "❌ NÃO ENCONTRADO - CORRIGIR", None, None, []

    # Se já possuir CEP explícito no texto, valida direto
    m_cep_texto = re.search(r"\b(\d{5})-?(\d{3})\b", str(endereco_bruto))
    cep_pre_informado = f"{m_cep_texto.group(1)}-{m_cep_texto.group(2)}" if m_cep_texto else ""

    rua, numero, bairro_dica, cidade = separar_componentes_endereco(str(endereco_bruto))
    rua_sem_prefixo = re.sub(
        r"^(rua|r\.|r|avenida|av\.|av|alameda|al\.|praca|praça|travessa|tv\.|beco)\s*",
        "",
        rua,
        flags=re.IGNORECASE
    ).strip()

    cep_encontrado = cep_pre_informado
    logradouro_oficial = ""
    bairro_oficial = ""
    cidade_oficial = cidade
    lat, lon = None, None
    mapa_bairros_opcoes = {}

    def registrar_opcao_bairro(logr_op, bair_op, cid_op, cep_op):
        b_limpo = str(bair_op).strip()
        if not b_limpo or eh_regional_bh(b_limpo):
            return
        chave_b = remover_acentos(f"{b_limpo}_{cid_op}".lower())
        if chave_b not in mapa_bairros_opcoes:
            partes_op = [formatar_via_com_prefixo(logr_op, rua)]
            if numero:
                partes_op.append(numero)
            partes_op.append(b_limpo)
            partes_op.append(cid_op)
            if cep_op:
                partes_op.append(cep_op)
            mapa_bairros_opcoes[chave_b] = ", ".join(partes_op)

    # 1) Tenta ViaCEP
    cidades_para_testar = [cidade]
    if bairro_dica:
        for cid_extra in ["Contagem", "Nova Lima", "Belo Horizonte", "Ribeirão das Neves", "Sabará", "Betim", "Santa Luzia"]:
            if cid_extra not in cidades_para_testar:
                cidades_para_testar.append(cid_extra)

    if len(rua_sem_prefixo) >= 2:
        for cid_teste in cidades_para_testar:
            dados_viacep = consultar_viacep_com_tolerancia(rua, rua_sem_prefixo, cid_teste)
            if not dados_viacep:
                continue

            candidatos_faixa = [
                d for d in dados_viacep
                if d.get("bairro") and numero_cabe_na_faixa_viacep(numero, d.get("complemento", ""))
            ]
            if not candidatos_faixa:
                candidatos_faixa = [d for d in dados_viacep if d.get("bairro")]

            def nota_candidato_viacep(item):
                s_rua = similaridade_ruas(rua, item.get("logradouro", ""))
                s_bairro = similaridade_bairros(bairro_dica, item.get("bairro", "")) if bairro_dica else 0.0
                return (s_bairro >= 0.72, s_rua + (s_bairro * 0.35))

            candidatos_faixa.sort(key=nota_candidato_viacep, reverse=True)

            for item in candidatos_faixa:
                registrar_opcao_bairro(
                    item.get("logradouro") or rua,
                    item.get("bairro", ""),
                    item.get("localidade") or cid_teste,
                    item.get("cep", "")
                )

            bateu_bairro_dica = [
                item for item in candidatos_faixa
                if bairro_dica and similaridade_bairros(bairro_dica, item.get("bairro", "")) >= 0.72
            ]

            if bateu_bairro_dica:
                escolhido = bateu_bairro_dica[0]
                mapa_bairros_opcoes.clear()  # Bairro já foi confirmado!
            elif bairro_dica and cid_teste != cidade:
                continue
            else:
                escolhido = candidatos_faixa[0] if candidatos_faixa else dados_viacep[0]

            logradouro_oficial = formatar_via_com_prefixo(escolhido.get("logradouro", ""), rua)
            bairro_oficial = escolhido.get("bairro", "")
            cidade_oficial = escolhido.get("localidade", cid_teste)
            cep_encontrado = escolhido.get("cep", "") or cep_encontrado
            break

    # 2) Busca Multifonte (ArcGIS + Photon + Nominatim)
    candidatos_geo = buscar_candidatos_multifonte(
        logradouro_oficial if logradouro_oficial else rua,
        numero,
        bairro_oficial if bairro_oficial else bairro_dica,
        cidade_oficial
    )

    if candidatos_geo:
        # Se o usuário informou bairro, prioriza candidato que bata com o bairro ou usa o bairro informado
        for cg in candidatos_geo:
            if not bairro_dica and cg.get("bairro"):
                registrar_opcao_bairro(
                    cg["logradouro"],
                    cg["bairro"],
                    cg["cidade"],
                    cg.get("cep") or cep_encontrado
                )

        melhor_cg = candidatos_geo[0]
        if bairro_dica:
            for cg in candidatos_geo:
                if cg.get("bairro") and similaridade_bairros(bairro_dica, cg["bairro"]) >= 0.70:
                    melhor_cg = cg
                    break

        lat, lon = melhor_cg["lat"], melhor_cg["lon"]
        if not logradouro_oficial:
            logradouro_oficial = melhor_cg["logradouro"]
        if not cep_encontrado and melhor_cg.get("cep"):
            cep_encontrado = melhor_cg["cep"]
        if not bairro_oficial:
            if melhor_cg.get("bairro") and (not bairro_dica or similaridade_bairros(bairro_dica, melhor_cg["bairro"]) >= 0.65):
                bairro_oficial = melhor_cg["bairro"]
            elif bairro_dica:
                bairro_oficial = bairro_dica.title()
            elif melhor_cg.get("bairro"):
                bairro_oficial = melhor_cg["bairro"]
        if melhor_cg.get("cidade"):
            cidade_oficial = melhor_cg["cidade"]

    # 3) Se temos CEP (do ArcGIS/Photon/Texto), enriquece via BrasilAPI/OpenCEP/ViaCEP para ter o Bairro Oficial exato!
    if cep_encontrado:
        dados_cep = consultar_cep_direto(cep_encontrado)
        if dados_cep and dados_cep.get("logradouro"):
            if similaridade_ruas(rua, dados_cep["logradouro"]) >= 0.65 or not logradouro_oficial:
                logradouro_oficial = formatar_via_com_prefixo(dados_cep["logradouro"], rua)
                if dados_cep.get("bairro") and not eh_regional_bh(dados_cep["bairro"]):
                    bairro_oficial = dados_cep["bairro"]
                if dados_cep.get("localidade"):
                    cidade_oficial = dados_cep["localidade"]
                cep_encontrado = dados_cep.get("cep", cep_encontrado)

    if not logradouro_oficial:
        partes_orig = [formatar_via_com_prefixo(rua.title(), rua)]
        if numero:
            partes_orig.append(numero)
        if bairro_dica:
            partes_orig.append(bairro_dica.title())
        partes_orig.append(cidade_oficial)
        end_mantido = ", ".join(partes_orig)

        if bairro_dica:
            ok_b, _, lat_b, lon_b = buscar_coordenada_bairro(bairro_dica, cidade_oficial)
            if ok_b:
                lat, lon = lat_b, lon_b
        return end_mantido, "❌ RUA NÃO CONFIRMADA - CONFERIR", lat, lon, []

    nome_via_final = formatar_via_com_prefixo(logradouro_oficial, rua)
    if bairro_oficial and not eh_regional_bh(bairro_oficial):
        bairro_final = bairro_oficial
    elif bairro_dica and not eh_regional_bh(bairro_dica):
        bairro_final = bairro_dica.title()
    else:
        bairro_final = "Bairro não identificado"

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

    opcoes_bairros = list(mapa_bairros_opcoes.values()) if (not bairro_dica and len(mapa_bairros_opcoes) > 1) else []

    if len(opcoes_bairros) > 1:
        status = f"⚠️ {len(opcoes_bairros)} BAIRROS ENCONTRADOS (ESCOLHER)"
    elif bairro_final == "Bairro não identificado":
        status = "⚠️ INCOMPLETO (CONFERIR BAIRRO/CEP)"
    else:
        status = "✅ OK"

    return endereco_padronizado, status, lat, lon, opcoes_bairros


@st.cache_data(ttl=86400, show_spinner=False)
def validar_e_geocodificar_partida(texto_partida: str):
    bruto = str(texto_partida).strip()
    if not bruto:
        return False, "❌ Digite um bairro, rua ou CEP de partida.", None, None

    apenas_digitos = re.sub(r"\D", "", bruto)
    if len(apenas_digitos) == 8:
        d_cep = consultar_cep_direto(apenas_digitos)
        if d_cep:
            logr = d_cep.get("logradouro", "")
            bair = d_cep.get("bairro", "")
            cid = d_cep.get("localidade", "Belo Horizonte")
            cep_f = d_cep.get("cep", bruto)
            desc = f"{logr}, {bair}, {cid} ({cep_f})".strip(" ,")
            lat, lon = geocodificar_endereco_rua(desc)
            return True, f"CEP localizado: {desc}", lat, lon

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


def extrair_dados_brutos_do_bloco(linhas_bloco: list, locais_dict: dict, vendedor_padrao: str = "") -> list:
    """
    Extrai cliente(s), itens e endereço de um bloco de mensagem.
    Se uma mesma mensagem tiver um único endereço e múltiplos clientes (ex: Vinicius, Ryan, Ana Clara),
    divide automaticamente mantendo o endereço para cada um.
    """
    linhas_endereco = []
    outras_linhas = []

    for linha in linhas_bloco:
        l_strip = linha.strip()
        if not l_strip or eh_subtitulo_ou_divisoria(l_strip):
            continue

        # Se a linha começa com "Mercadoria:" ou "Itens:", limpa o rótulo e força como item
        if re.match(r"^(mercadoria|itens?|produtos?)\s*[:\-]", remover_acentos(l_strip.lower())):
            item_limpo = re.sub(r"^(mercadoria|itens?|produtos?)\s*[:\-]\s*", "", l_strip, flags=re.IGNORECASE).strip()
            if item_limpo:
                outras_linhas.append(("ITEM", item_limpo))
            continue

        if re.match(r"^(cliente|nome|pedido|ped)\s*[:\-]", remover_acentos(l_strip.lower())):
            outras_linhas.append(("NOME", limpar_nome_cliente(l_strip)))
            continue

        if eh_linha_endereco(l_strip, locais_dict):
            linhas_endereco.append(l_strip)
        elif linhas_endereco and eh_complemento_pos_endereco(l_strip, locais_dict):
            linhas_endereco[-1] = f"{linhas_endereco[-1]}, {l_strip}"
        elif eh_linha_produto_clara(l_strip, locais_dict):
            outras_linhas.append(("ITEM", l_strip))
        elif pode_ser_nome_cliente(l_strip, locais_dict):
            outras_linhas.append(("NOME", limpar_nome_cliente(l_strip)))
        else:
            outras_linhas.append(("ITEM", l_strip))

    if not linhas_endereco:
        return []

    endereco_bruto_final = ", ".join(linhas_endereco)

    # Agrupa por cliente caso haja mais de um cliente para o mesmo endereço no bloco
    sub_pedidos = []
    cliente_atual = None
    itens_atuais = []

    for tipo, valor in outras_linhas:
        if tipo == "NOME":
            if cliente_atual and itens_atuais:
                sub_pedidos.append((cliente_atual, itens_atuais))
                cliente_atual = valor
                itens_atuais = []
            elif cliente_atual is None:
                cliente_atual = valor
            else:
                # Dois nomes seguidos sem itens entre eles: mantém o primeiro
                pass
        else:
            itens_atuais.append(valor)

    if cliente_atual:
        sub_pedidos.append((cliente_atual, itens_atuais))
    elif itens_atuais:
        sub_pedidos.append(("CLIENTE", itens_atuais))

    pre_pedidos = []
    for nome_cli, lista_it in sub_pedidos:
        qtd_pct, locais_detectados = identificar_locais_dos_itens(lista_it, locais_dict)
        resumo_itens = ", ".join(lista_it)
        if locais_detectados:
            resumo_itens += f" ➔ [{', '.join(locais_detectados)}]"
        pre_pedidos.append({
            "Cliente": nome_cli,
            "Vendedor": vendedor_padrao.upper().strip(),
            "Pacotes": qtd_pct,
            "Itens_Lidos": resumo_itens,
            "Endereco_Bruto": endereco_bruto_final
        })

    return pre_pedidos


def resolver_enderecos_em_paralelo(lista_enderecos_brutos: list) -> dict:
    """Executa buscar_endereco_completo em paralelo (até 12 threads) para carregar 35+ pedidos em ~3 segundos."""
    unicos = list(dict.fromkeys([e for e in lista_enderecos_brutos if str(e).strip()]))
    resultados = {}
    if not unicos:
        return resultados

    max_workers = min(12, len(unicos))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {executor.submit(buscar_endereco_completo, end_b): end_b for end_b in unicos}
        for fut in as_completed(futuros):
            end_b = futuros[fut]
            try:
                resultados[end_b] = fut.result()
            except Exception:
                resultados[end_b] = (end_b, "❌ ERRO NA BUSCA - CONFERIR", None, None, [])
    return resultados


def extrair_pedidos_brutos(texto_bruto: str, locais_dict: dict, vendedor_padrao: str = ""):
    linhas_originais = texto_bruto.splitlines()
    tem_cabecalho_chat = any(REGEX_CABECALHO_CHAT.match(l) for l in linhas_originais if l.strip())

    blocos = []

    if tem_cabecalho_chat:
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
    else:
        linhas_cruas = [l.strip() for l in linhas_originais if l.strip()]
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
                while (i + 1) < n and eh_complemento_pos_endereco(linhas_cruas[i + 1], locais_dict):
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

    pre_pedidos = []
    for b in blocos:
        pre_pedidos.extend(extrair_dados_brutos_do_bloco(b, locais_dict, vendedor_padrao))

    if not pre_pedidos:
        return pd.DataFrame()

    mapa_resolvidos = resolver_enderecos_em_paralelo([p["Endereco_Bruto"] for p in pre_pedidos])

    pedidos_finais = []
    for p in pre_pedidos:
        end_completo, status, lat, lon, opcoes_amb = mapa_resolvidos.get(
            p["Endereco_Bruto"],
            (p["Endereco_Bruto"], "❌ RUA NÃO CONFIRMADA - CONFERIR", None, None, [])
        )
        pedidos_finais.append({
            "Excluir": False,
            "Status": status,
            "Cliente": p["Cliente"],
            "Vendedor": p["Vendedor"],
            "Pacotes": p["Pacotes"],
            "Observacao": "",
            "Posicao": "Normal",
            "Endereco": end_completo,
            "Itens_Lidos": p["Itens_Lidos"],
            "Lat": lat,
            "Lon": lon,
            "Opcoes_Endereco": json.dumps(opcoes_amb, ensure_ascii=False)
        })

    return pd.DataFrame(pedidos_finais)


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


# ================= FUNÇÕES DO GERADOR DE ETIQUETAS (10x15cm) =================
def localizar_modelo_pdf_no_repositorio():
    """Busca automaticamente o arquivo Etiqueta.pdf na mesma pasta do repositório GitHub."""
    pasta_base = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    for nome_arq in NOMES_ARQUIVO_MODELO:
        caminho_tentativa = os.path.join(pasta_base, nome_arq)
        if os.path.exists(caminho_tentativa):
            return caminho_tentativa
        if os.path.exists(nome_arq):
            return nome_arq
    return None


def limpar_nome_para_etiqueta(nome_bruto: str) -> str:
    """Remove colchetes de vendedor [2T] para a etiqueta impressa, mantendo o nome limpo."""
    sem_vendedor = re.sub(r"\[.*?\]", "", str(nome_bruto))
    sem_espacos_duplos = re.sub(r"\s+", " ", sem_vendedor).strip()
    return sem_espacos_duplos.upper()


def formatar_endereco_para_etiqueta(endereco_bruto: str) -> str:
    """
    Remove apenas CEPs que estejam intercalados no formato antigo do Circuit ('Rua X, 10, 30000-000 - Bairro')
    sem nunca apagar o número da rua ou cortar o CEP no final do endereço do Gerador de Rotas.
    """
    end = str(endereco_bruto).strip()
    end = re.sub(r",\s*\d{5}-?\d{3}\s*-\s*", " - ", end)
    end = re.sub(r"\s+", " ", end).strip(" ,")
    return end


def atualizar_base_etiquetas(novo_df: pd.DataFrame):
    df_limpo = novo_df.reset_index(drop=True).copy()
    st.session_state["df_etiquetas"] = df_limpo
    st.session_state["df_etiquetas_editadas"] = df_limpo.copy()
    st.session_state["versao_editor_etiquetas"] = st.session_state.get("versao_editor_etiquetas", 0) + 1


def extrair_etiquetas_de_texto_rota(texto_colado: str) -> pd.DataFrame:
    """
    Lê a lista de nomes e endereços exatamente como é gerada no Gerador de Rotas:
    Exemplo:
        ROTA FP

        Rua Marrocos, 47, Vila Jardim Leblon, Belo Horizonte, 31575-230
        AXEL [2T] (2PCT)
    Também aceita a ordem inversa (Nome na linha de cima e Endereço na linha de baixo).
    """
    linhas = [l.strip() for l in texto_colado.splitlines()]
    rota_atual = "GERAL"
    registros = []
    buffer_linhas = []

    def processar_par(linhas_bloco, nome_rota):
        if not linhas_bloco:
            return
        if len(linhas_bloco) == 1:
            unica = linhas_bloco[0]
            if eh_linha_endereco(unica):
                registros.append({
                    "Imprimir": True,
                    "Rota": nome_rota,
                    "Ordem": f"{len(registros) + 1}º",
                    "Nome Etiqueta": "CLIENTE",
                    "Endereco Etiqueta": formatar_endereco_para_etiqueta(unica),
                    "Nome Original": "CLIENTE",
                    "Endereco Original": unica
                })
            return

        l1, l2 = linhas_bloco[0], linhas_bloco[1]
        if eh_linha_endereco(l1) and not eh_linha_endereco(l2):
            end_orig, nome_orig = l1, l2
        elif eh_linha_endereco(l2) and not eh_linha_endereco(l1):
            nome_orig, end_orig = l1, l2
        else:
            # Padrão do Gerador de Rotas: 1ª linha é Endereço, 2ª linha é Cliente
            end_orig, nome_orig = l1, l2

        registros.append({
            "Imprimir": True,
            "Rota": nome_rota,
            "Ordem": f"{len(registros) + 1}º",
            "Nome Etiqueta": limpar_nome_para_etiqueta(nome_orig),
            "Endereco Etiqueta": formatar_endereco_para_etiqueta(end_orig),
            "Nome Original": nome_orig.strip().upper(),
            "Endereco Original": end_orig.strip()
        })

    for ln in linhas:
        if not ln:
            if buffer_linhas:
                processar_par(buffer_linhas, rota_atual)
                buffer_linhas = []
            continue

        # Identifica cabeçalho de rota (ex: "ROTA FP", "ROTA LE", "ROTA 1")
        if re.match(r"^ROTA\b", ln, flags=re.IGNORECASE) and not eh_linha_endereco(ln):
            if buffer_linhas:
                processar_par(buffer_linhas, rota_atual)
                buffer_linhas = []
            rota_atual = ln.strip().upper()
            continue

        buffer_linhas.append(ln)
        if len(buffer_linhas) == 2:
            processar_par(buffer_linhas, rota_atual)
            buffer_linhas = []

    if buffer_linhas:
        processar_par(buffer_linhas, rota_atual)

    return pd.DataFrame(registros)


def importar_etiquetas_das_rotas_calculadas(df_rotas: pd.DataFrame) -> pd.DataFrame:
    """Converte o DataFrame das rotas calculadas no Passo 4 diretamente para o formato de Etiquetas."""
    registros = []
    for idx, row in df_rotas.iterrows():
        nome_completo_rota = montar_linha_cliente(row)
        end_completo = str(row.get("Endereco", "")).strip()
        registros.append({
            "Imprimir": True,
            "Rota": str(row.get("Rota", "ROTA")).strip().upper(),
            "Ordem": str(row.get("Ordem", f"{idx + 1}º")),
            "Nome Etiqueta": limpar_nome_para_etiqueta(nome_completo_rota),
            "Endereco Etiqueta": formatar_endereco_para_etiqueta(end_completo),
            "Nome Original": nome_completo_rota,
            "Endereco Original": end_completo
        })
    return pd.DataFrame(registros)


def quebrar_endereco_duas_linhas(endereco: str, limite_chars: int = 50):
    """Divide o endereço em até 2 linhas para caber perfeitamente na largura de 10cm da etiqueta."""
    end = endereco.strip()
    if "MG," in end:
        partes = end.split("MG,", 1)
        return partes[0].strip() + " MG", partes[1].strip()

    if len(end) <= limite_chars:
        return end, ""

    # Tenta quebrar na vírgula mais próxima antes do limite
    corte = end.rfind(",", 0, limite_chars)
    if corte == -1:
        corte = end.rfind(" ", 0, limite_chars)
    if corte == -1:
        return end[:limite_chars], end[limite_chars:].strip()

    linha1 = end[:corte].strip(" ,")
    linha2 = end[corte:].strip(" ,")
    return linha1, linha2


def gerar_pdf_etiquetas_10x15(df_selecionadas: pd.DataFrame, fonte_modelo_pdf) -> bytes:
    """
    Gera um único PDF no formato 10x15cm (100x150mm) mesclando cada etiqueta selecionada
    sobre o arquivo modelo Etiqueta.pdf.
    """
    largura, altura = 100 * mm, 150 * mm
    pdf_final_writer = PdfWriter()

    for _, row in df_selecionadas.iterrows():
        # Lê uma cópia limpa da página do modelo para cada etiqueta
        modelo_reader = PdfReader(fonte_modelo_pdf)
        modelo_pagina = modelo_reader.pages[0]

        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=portrait((largura, altura)))

        # Nome do Destinatário
        can.setFont("Helvetica-Bold", 9)
        can.drawString(38 * mm, 200, str(row.get("Nome Etiqueta", "")).strip())

        # Endereço do Destinatário (com quebra inteligente em 2 linhas se necessário)
        can.setFont("Helvetica", 8)
        end_str = str(row.get("Endereco Etiqueta", "")).strip()
        linha_end_1, linha_end_2 = quebrar_endereco_duas_linhas(end_str, limite_chars=50)

        if linha_end_2:
            can.drawString(9 * mm, 184, linha_end_1)
            can.drawString(9 * mm, 175, linha_end_2)
        else:
            can.drawString(9 * mm, 182, linha_end_1)

        can.save()
        packet.seek(0)

        overlay = PdfReader(packet).pages[0]
        saida_pag = PageObject.create_blank_page(width=largura, height=altura)
        saida_pag.merge_page(modelo_pagina)
        saida_pag.merge_page(overlay)
        pdf_final_writer.add_page(saida_pag)

    pdf_saida = BytesIO()
    pdf_final_writer.write(pdf_saida)
    return pdf_saida.getvalue()


# ================= INICIALIZAÇÃO DE ESTADO =================
config_salva = carregar_config()

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
    st.session_state["coord_partida_atual"] = (-19.9167, -43.9345)

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


# ================= BARRA LATERAL (CONFIGURAÇÕES GERAIS) =================
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

    st.divider()
    if st.button("🔒 Sair / Bloquear Acesso", use_container_width=True):
        st.session_state["autenticado"] = False
        st.rerun()

    locais_config = {
        "Local 1": [p for p in local_1.split(",") if p.strip()],
        "Local 2": [p for p in local_2.split(",") if p.strip()],
        "Local 3": [p for p in local_3.split(",") if p.strip()],
        "Local 4": [p for p in local_4.split(",") if p.strip()],
    }


# ================= SELETOR DE MÓDULOS NO TOPO (2 BOTÕES PRINCIPAIS) =================
col_nav1, col_nav2 = st.columns(2)
with col_nav1:
    tipo_btn_rotas = "primary" if st.session_state["modulo_ativo"] == "rotas" else "secondary"
    if st.button("🛵 Gerador de Rotas", type=tipo_btn_rotas, use_container_width=True):
        st.session_state["modulo_ativo"] = "rotas"
        st.rerun()

with col_nav2:
    qtd_etiq_badge = len(st.session_state["df_etiquetas"])
    texto_btn_etiq = f"🏷️ Gerador de Etiquetas ({qtd_etiq_badge})" if qtd_etiq_badge > 0 else "🏷️ Gerador de Etiquetas"
    tipo_btn_etiq = "primary" if st.session_state["modulo_ativo"] == "etiquetas" else "secondary"
    if st.button(texto_btn_etiq, type=tipo_btn_etiq, use_container_width=True):
        st.session_state["modulo_ativo"] = "etiquetas"
        st.rerun()

st.divider()


# ==============================================================================
# MÓDULO 1: GERADOR DE ROTAS
# ==============================================================================
if st.session_state["modulo_ativo"] == "rotas":
    st.title("🛵 Gerador de Rotas")

    if (
        partida_ok
        and not st.session_state["df_rotas_calculadas"].empty
        and st.session_state["coord_partida_atual"] != (lat_partida, lon_partida)
    ):
        df_reotim, novo_km, nova_coord = recalcular_todas_as_rotas(
            st.session_state.get("df_rotas_editadas", st.session_state["df_rotas_calculadas"]),
            st.session_state["nomes_rotas_ativas"],
            lat_partida,
            lon_partida
        )
        st.session_state["df_rotas_calculadas"] = df_reotim
        st.session_state["df_rotas_editadas"] = df_reotim.copy()
        st.session_state["versao_editor_rotas"] += 1
        st.session_state["resumo_km_rotas"] = novo_km
        st.session_state["coord_partida_atual"] = nova_coord

    # --- PASSO 1: ADICIONAR PEDIDOS ---
    st.subheader("1️⃣ Adicionar Pedidos")

    texto_pedidos = st.text_area(
        "Cole os pedidos abaixo:",
        height=200,
        key=f"texto_pedidos_{st.session_state['contador_form']}",
        placeholder=(
            "Exemplo:\n[14/10/2026 13:53]: Fulano\n25g castanha\nRua São Vicente 250\n\n"
        )
    )
    vendedor_lote = st.text_input(
        "Sigla do Vendedor `[ ]` para os pedidos acima:",
        key=f"vendedor_lote_{st.session_state['contador_form']}",
        placeholder="Ex: 2T, VG, NK"
    )

    if st.button("🔍 Adicionar à Lista", type="primary", use_container_width=True):
        if texto_pedidos.strip():
            with st.spinner("Extraindo pedidos, filtrando mensagens e buscando CEPs..."):
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

        @st.fragment
        def render_passo_2():
            df_base = st.session_state["df_pedidos"]
            if "Excluir" not in df_base.columns:
                df_base.insert(0, "Excluir", False)
            if "Opcoes_Endereco" not in df_base.columns:
                df_base["Opcoes_Endereco"] = "[]"

            linhas_ambiguas = []
            for idx_amb, row_amb in df_base.iterrows():
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
                            df_sync = st.session_state.get("df_pedidos_editados", df_base).copy()
                            lat_novo, lon_novo = geocodificar_endereco_rua(escolha_end)
                            df_sync.at[idx_amb, "Endereco"] = escolha_end
                            df_sync.at[idx_amb, "Status"] = "✅ OK"
                            df_sync.at[idx_amb, "Lat"] = lat_novo
                            df_sync.at[idx_amb, "Lon"] = lon_novo
                            df_sync.at[idx_amb, "Opcoes_Endereco"] = "[]"
                            atualizar_base_pedidos(df_sync)
                            st.rerun()

            problemas = df_base[df_base["Status"] != "✅ OK"]
            if not problemas.empty:
                st.warning(
                    f"⚠️ **{len(problemas)} endereço(s) precisam da sua atenção!** "
                    "Escolha o bairro acima ou corrija o endereço na tabela abaixo e clique em '🔍 Buscar CEP após Editar Tabela'."
                )
            else:
                st.success(f"✅ Todos os {len(df_base)} endereços foram localizados com Bairro e CEP!")

            df_editado = st.data_editor(
                df_base,
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
                },
                key=f"editor_tabela_pedidos_{st.session_state['versao_editor_pedidos']}"
            )

            df_editado["Cliente"] = df_editado["Cliente"].astype(str).str.upper()
            st.session_state["df_pedidos_editados"] = df_editado

            col_acao1, col_acao2, col_acao3 = st.columns(3)

        with col_acao1:
                if st.button(
                    "🔍 Buscar CEP após Editar Tabela",
                    use_container_width=True,
                    help="Rebusca rapidamente apenas os endereços que você editou ou que estavam com aviso."
                ):
                    with st.spinner("Atualizando endereços editados/pendentes em paralelo..."):
                        df_atualizados = df_editado.copy()
                        indices_para_buscar = []
                        enderecos_para_buscar = []

                        for idx, row in df_atualizados.iterrows():
                            end_antigo = str(df_base.at[idx, "Endereco"]) if idx in df_base.index else ""
                            end_atual = str(row["Endereco"])
                            status_atual = str(row["Status"])
                            if end_atual != end_antigo or status_atual != "✅ OK":
                                indices_para_buscar.append(idx)
                                enderecos_para_buscar.append(end_atual)

                        if enderecos_para_buscar:
                            mapa_novos = resolver_enderecos_em_paralelo(enderecos_para_buscar)
                            for idx in indices_para_buscar:
                                end_atual = str(df_atualizados.at[idx, "Endereco"])
                                end_novo, novo_status, lat, lon, novas_opcoes = mapa_novos.get(
                                    end_atual,
                                    buscar_endereco_completo(end_atual)
                                )
                                df_atualizados.at[idx, "Endereco"] = end_novo
                                df_atualizados.at[idx, "Status"] = novo_status
                                df_atualizados.at[idx, "Lat"] = lat
                                df_atualizados.at[idx, "Lon"] = lon
                                df_atualizados.at[idx, "Opcoes_Endereco"] = json.dumps(novas_opcoes, ensure_ascii=False)

                        atualizar_base_pedidos(df_atualizados)
                        st.rerun()

            with col_acao2:
                qtd_marcados = int(df_editado["Excluir"].sum()) if "Excluir" in df_editado.columns else 0
                texto_btn_excluir = f"🗑️ Excluir Selecionados ({qtd_marcados})" if qtd_marcados > 0 else "🗑️ Excluir Selecionados"
                if st.button(texto_btn_excluir, use_container_width=True):
                    if qtd_marcados > 0:
                        df_restante = df_editado[~df_editado["Excluir"]].copy()
                        df_restante["Excluir"] = False
                        atualizar_base_pedidos(df_restante)
                        st.session_state["df_rotas_calculadas"] = pd.DataFrame()
                        st.session_state["df_rotas_editadas"] = pd.DataFrame()
                        st.rerun()
                    else:
                        st.toast("Marque a caixinha '🗑️' na tabela ao lado do cliente que deseja remover.")

            with col_acao3:
                if st.button("🧹 Limpar Lista", use_container_width=True):
                    atualizar_base_pedidos(pd.DataFrame())
                    st.session_state["df_rotas_calculadas"] = pd.DataFrame()
                    st.session_state["df_rotas_editadas"] = pd.DataFrame()
                    st.session_state["avisos_duplicados"] = []
                    st.rerun()

            with st.expander("👀 Ver prévia dos pedidos (Nomes e Endereços)", expanded=True):
                linhas_previa = []
                for _, row in df_editado.iterrows():
                    linhas_previa.append(f"{row['Endereco']}\n{montar_linha_cliente(row)}")
                st.code("\n\n".join(linhas_previa), language="text", wrap_lines=True)

        render_passo_2()

        # --- PASSO 3: DIVISÃO E CÁLCULO DAS ROTAS ---
        st.divider()
        st.subheader("3️⃣ Dividir e Calcular Melhores Rotas")

        df_para_calculo = st.session_state.get("df_pedidos_editados", st.session_state["df_pedidos"])
        total_pedidos_atual = len(df_para_calculo)

        qtd_rotas = st.radio(
            "Em quantas rotas deseja dividir os pedidos?",
            options=[1, 2, 3, 4],
            index=1 if total_pedidos_atual >= 2 else 0,
            horizontal=True
        )

        base_por_rota = total_pedidos_atual // qtd_rotas
        sobra = total_pedidos_atual % qtd_rotas
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
                    max_value=total_pedidos_atual,
                    value=sugestoes_padrao[i],
                    step=1,
                    key=f"cota_rota_{i}_{qtd_rotas}_{total_pedidos_atual}"
                )
                nomes_escolhidos.append(formatar_titulo_rota(nome_r))
                cotas_escolhidas.append(int(cota_r))

        soma_cotas = sum(cotas_escolhidas)
        if soma_cotas != total_pedidos_atual:
            diferenca = total_pedidos_atual - soma_cotas
            if diferenca > 0:
                st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você tem **{total_pedidos_atual}** na lista (faltam distribuir **{diferenca}**).")
            else:
                st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você só tem **{total_pedidos_atual}** na lista (passou **{abs(diferenca)}**).")

        if not partida_ok:
            st.error("⚠️ Corrija o Ponto de Partida na barra lateral esquerda antes de gerar as rotas.")

        if st.button(
            "🚀 Gerar e Otimizar Rotas",
            type="primary",
            use_container_width=True,
            disabled=(soma_cotas != total_pedidos_atual or not partida_ok)
        ):
            with st.spinner("Agrupando regiões e calculando a melhor sequência rua a rua..."):
                df_mais_recente = st.session_state.get("df_pedidos_editados", st.session_state["df_pedidos"]).copy().reset_index(drop=True)
                atualizar_base_pedidos(df_mais_recente)

                nomes_unicos = []
                for idx_n, nm in enumerate(nomes_escolhidos):
                    if nm in nomes_unicos:
                        nm = f"{nm} ({idx_n + 1})"
                    nomes_unicos.append(nm)

                rotas_atribuidas = dividir_pedidos_por_cota(
                    df_mais_recente,
                    nomes_unicos,
                    cotas_escolhidas,
                    lat_partida,
                    lon_partida
                )
                df_mais_recente["Rota"] = rotas_atribuidas

                df_otimizado, resumo_km, coord_p = recalcular_todas_as_rotas(
                    df_mais_recente,
                    nomes_unicos,
                    lat_partida,
                    lon_partida
                )

                st.session_state["df_rotas_calculadas"] = df_otimizado
                st.session_state["df_rotas_editadas"] = df_otimizado.copy()
                st.session_state["versao_editor_rotas"] += 1
                st.session_state["nomes_rotas_ativas"] = nomes_unicos
                st.session_state["resumo_km_rotas"] = resumo_km
                st.session_state["coord_partida_atual"] = coord_p
                st.rerun()

    # --- PASSO 4: ROTAS PRONTAS, TROCA ENTRE ROTAS E BOTÃO DE ETIQUETAS ---
    if not st.session_state["df_rotas_calculadas"].empty:
        st.divider()
        st.subheader("4️⃣ Rotas Otimizadas e Ajuste Entre Rotas")

        @st.fragment
        def render_passo_4():
            df_rotas_base = st.session_state["df_rotas_calculadas"]
            nomes_ativas = st.session_state["nomes_rotas_ativas"]
            resumo_km = st.session_state["resumo_km_rotas"]

            st.caption(
                "💡 **Quer passar um pedido de uma rota para outra ou mudar quem é o PRIMEIRO/ÚLTIMO?** "
                "Basta alterar a coluna **'Rota'** ou **'Posição'** na tabela abaixo que o sistema recalcula a melhor ordem das rotas automaticamente!"
            )

            df_rotas_edit = st.data_editor(
                df_rotas_base,
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
                },
                key=f"editor_tabela_rotas_{st.session_state['versao_editor_rotas']}"
            )

            df_rotas_edit["Cliente"] = df_rotas_edit["Cliente"].astype(str).str.upper()
            st.session_state["df_rotas_editadas"] = df_rotas_edit

            mudou_rota_ou_pos = (
                not df_rotas_edit["Rota"].equals(df_rotas_base["Rota"]) or
                not df_rotas_edit["Posicao"].equals(df_rotas_base["Posicao"])
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
                    st.session_state["df_rotas_editadas"] = df_reotimizado.copy()
                    st.session_state["versao_editor_rotas"] += 1
                    st.session_state["resumo_km_rotas"] = novo_km
                    st.session_state["coord_partida_atual"] = coord_p
                    st.rerun()

            df_exibicao = st.session_state.get("df_rotas_editadas", df_rotas_base)

            with st.expander("🗺️ Ver Mapa das Rotas (Pinos Numerados por Ordem de Entrega)", expanded=True):
                renderizar_mapa_rotas(
                    df_exibicao,
                    nomes_ativas,
                    st.session_state["coord_partida_atual"],
                    desc_partida_validada
                )

            st.markdown("### 📋 Textos Prontos para Copiar (WhatsApp / Telegram)")
            st.caption("Clique no ícone de copiar no canto superior direito de cada caixa preta abaixo:")

            cols_texto = st.columns(min(len(nomes_ativas), 2))

            for idx_r, nome_r in enumerate(nomes_ativas):
                sub_rota = df_exibicao[df_exibicao["Rota"] == nome_r]
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

            st.divider()
            st.markdown("### 🏷️ Gerar Etiquetas 10x15 das Rotas Criadas")
            st.caption("Clique no botão abaixo para enviar todas as rotas acima diretamente para o Gerador de Etiquetas:")
            if st.button("🏷️ Gerar Etiquetas das Rotas Criadas", type="primary", use_container_width=True):
                df_etiq_importadas = importar_etiquetas_das_rotas_calculadas(df_exibicao)
                atualizar_base_etiquetas(df_etiq_importadas)
                st.session_state["modulo_ativo"] = "etiquetas"
                st.rerun()

        render_passo_4()


# ==============================================================================
# MÓDULO 2: GERADOR DE ETIQUETAS (10x15cm)
# ==============================================================================
elif st.session_state["modulo_ativo"] == "etiquetas":
    st.title("🏷️ Gerador de Etiquetas (10x15 cm)")

    caminho_modelo_repo = localizar_modelo_pdf_no_repositorio()
    arquivo_modelo_upload = None

    if caminho_modelo_repo:
        st.success(f"✅ Modelo de etiqueta carregado automaticamente do repositório (`{os.path.basename(caminho_modelo_repo)}`).")
    else:
        st.warning("⚠️ O arquivo `Etiqueta.pdf` não foi encontrado na pasta do GitHub. Faça o upload dele abaixo ou adicione `Etiqueta.pdf` ao repositório.")
        arquivo_modelo_upload = st.file_uploader("Subir modelo Etiqueta.pdf", type="pdf")

    # Se já existirem rotas calculadas no Gerador de Rotas, oferece atalho rápido para puxá-las
    if not st.session_state["df_rotas_calculadas"].empty:
        df_rotas_disp = st.session_state.get("df_rotas_editadas", st.session_state["df_rotas_calculadas"])
        if st.button(f"📥 Puxar Automaticamente as {len(df_rotas_disp)} Entregas das Rotas Calculadas", use_container_width=True):
            df_imp = importar_etiquetas_das_rotas_calculadas(df_rotas_disp)
            atualizar_base_etiquetas(df_imp)
            st.rerun()

    # --- 1) COLAR LISTA DE NOMES E ENDEREÇOS (MESMO FORMATO DO GERADOR DE ROTAS) ---
    st.subheader("1️⃣ Colar Lista de Nomes e Endereços")
    texto_lista_etiquetas = st.text_area(
        "Cole abaixo a lista de entregas (no mesmo formato gerado pelo Gerador de Rotas):",
        height=200,
        key=f"texto_etiquetas_{st.session_state['contador_form_etiquetas']}",
        placeholder=(
            "ROTA FP\n\n"
            "Rua Marrocos, 47, Vila Jardim Leblon, Belo Horizonte, 31575-230\n"
            "AXEL [2T] (2PCT)\n\n"
            "Rua São Vicente, 250, Granja Werneck, Belo Horizonte, 31840-410\n"
            "JOÃO SILVA [VG]"
        )
    )

    if st.button("➕ Extrair e Adicionar Etiquetas da Lista", type="primary", use_container_width=True):
        if texto_lista_etiquetas.strip():
            df_novas_etiq = extrair_etiquetas_de_texto_rota(texto_lista_etiquetas)
            if not df_novas_etiq.empty:
                df_atual_etiq = st.session_state.get("df_etiquetas_editadas", st.session_state["df_etiquetas"])
                if df_atual_etiq.empty:
                    df_comb = df_novas_etiq
                else:
                    df_comb = pd.concat([df_atual_etiq, df_novas_etiq], ignore_index=True)
                atualizar_base_etiquetas(df_comb)
                st.session_state["contador_form_etiquetas"] += 1
                st.rerun()
            else:
                st.warning("⚠️ Não foi possível identificar pares de endereço e cliente no texto colado.")
        else:
            st.warning("Cole a lista de entregas antes de clicar no botão.")

    with st.expander("➕ Adicionar um Cliente Individualmente"):
        col_m1, col_m2, col_m3 = st.columns([2, 3, 1])
        with col_m1:
            m_nome = st.text_input("Nome do Cliente (ex: AXEL [2T] (2PCT)):")
        with col_m2:
            m_end = st.text_input("Endereço Completo (ex: Rua Marrocos, 47, Vila Jardim Leblon, Belo Horizonte, 31575-230):")
        with col_m3:
            m_rota = st.text_input("Rota:", value="AVULSO")

        if st.button("Adicionar Cliente Avulso", use_container_width=True):
            if m_nome.strip() and m_end.strip():
                df_atual_etiq = st.session_state.get("df_etiquetas_editadas", st.session_state["df_etiquetas"])
                nova_linha = pd.DataFrame([{
                    "Imprimir": True,
                    "Rota": m_rota.strip().upper() or "AVULSO",
                    "Ordem": f"{len(df_atual_etiq) + 1}º",
                    "Nome Etiqueta": limpar_nome_para_etiqueta(m_nome),
                    "Endereco Etiqueta": formatar_endereco_para_etiqueta(m_end),
                    "Nome Original": m_nome.strip().upper(),
                    "Endereco Original": m_end.strip()
                }])
                df_comb = pd.concat([df_atual_etiq, nova_linha], ignore_index=True) if not df_atual_etiq.empty else nova_linha
                atualizar_base_etiquetas(df_comb)
                st.rerun()
            else:
                st.warning("Preencha o Nome e o Endereço.")

    # --- 2) SELEÇÃO, EDIÇÃO E DOWNLOAD DO PDF 10x15 ---
    if not st.session_state["df_etiquetas"].empty:
        st.divider()
        st.subheader("2️⃣ Selecionar e Baixar Etiquetas em PDF Único (10x15 cm)")

        @st.fragment
        def render_tabela_etiquetas():
            df_base_e = st.session_state["df_etiquetas"]
            if "Imprimir" not in df_base_e.columns:
                df_base_e.insert(0, "Imprimir", True)

            rotas_presentes = sorted(list(df_base_e["Rota"].dropna().unique()))

            # Botões rápidos de seleção
            c_sel1, c_sel2, c_sel3, c_sel4 = st.columns(4)
            with c_sel1:
                if st.button("☑️ Marcar Todas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_sync["Imprimir"] = True
                    atualizar_base_etiquetas(df_sync)
                    st.rerun()
            with c_sel2:
                if st.button("🔲 Desmarcar Todas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_sync["Imprimir"] = False
                    atualizar_base_etiquetas(df_sync)
                    st.rerun()
            with c_sel3:
                if st.button("🗑️ Excluir Desmarcadas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_rest = df_sync[df_sync["Imprimir"]].copy()
                    atualizar_base_etiquetas(df_rest)
                    st.rerun()
            with c_sel4:
                if st.button("🧹 Limpar Lista de Etiquetas", use_container_width=True):
                    atualizar_base_etiquetas(pd.DataFrame())
                    st.rerun()

            if len(rotas_presentes) > 1:
                st.caption("Filtrar seleção rápida por Rota:")
                cols_f = st.columns(len(rotas_presentes))
                for idx_f, r_nome in enumerate(rotas_presentes):
                    with cols_f[idx_f]:
                        if st.button(f"🎯 Só {r_nome}", key=f"btn_filtro_etiq_{idx_f}", use_container_width=True):
                            df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                            df_sync["Imprimir"] = df_sync["Rota"] == r_nome
                            atualizar_base_etiquetas(df_sync)
                            st.rerun()

            df_etiq_edit = st.data_editor(
                df_base_e,
                use_container_width=True,
                hide_index=True,
                column_order=["Imprimir", "Rota", "Ordem", "Nome Etiqueta", "Endereco Etiqueta"],
                column_config={
                    "Imprimir": st.column_config.CheckboxColumn("🖨️ Imprimir", width="small", default=True),
                    "Rota": st.column_config.TextColumn("Rota", width="small"),
                    "Ordem": st.column_config.TextColumn("Ordem", width="small"),
                    "Nome Etiqueta": st.column_config.TextColumn("Destinatário na Etiqueta (Editável)", width="medium"),
                    "Endereco Etiqueta": st.column_config.TextColumn("Endereço na Etiqueta (Editável)", width="large"),
                },
                key=f"editor_tabela_etiquetas_{st.session_state['versao_editor_etiquetas']}"
            )

            df_etiq_edit["Nome Etiqueta"] = df_etiq_edit["Nome Etiqueta"].astype(str).str.upper()
            st.session_state["df_etiquetas_editadas"] = df_etiq_edit

            df_selecionadas = df_etiq_edit[df_etiq_edit["Imprimir"]].copy()
            qtd_selecionadas = len(df_selecionadas)

            st.markdown(f"**Etiquetas selecionadas para o PDF:** `{qtd_selecionadas}` de `{len(df_etiq_edit)}`")

            fonte_pdf = caminho_modelo_repo if caminho_modelo_repo else arquivo_modelo_upload

            if not fonte_pdf:
                st.error("⚠️ Adicione o arquivo `Etiqueta.pdf` no seu repositório GitHub ou faça upload acima para liberar o download.")
            elif qtd_selecionadas == 0:
                st.warning("⚠️ Marque pelo menos uma etiqueta na coluna '🖨️ Imprimir' para gerar o PDF.")
            else:
                pdf_bytes = gerar_pdf_etiquetas_10x15(df_selecionadas, fonte_pdf)
                st.download_button(
                    label=f"📥 BAIXAR PDF ÚNICO 10x15 ({qtd_selecionadas} ETIQUETAS SELECIONADAS)",
                    data=pdf_bytes,
                    file_name="etiquetas_10x15.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

        render_tabela_etiquetas()
