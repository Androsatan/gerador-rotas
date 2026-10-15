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
                        d
