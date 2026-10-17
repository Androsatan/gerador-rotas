import re
import unicodedata
from difflib import SequenceMatcher

from gerador_rotas.dominio.constantes import (
    PALAVRAS_GENERICAS_BAIRRO,
    STOPWORDS_PRODUTOS,
    TITULOS_E_STOPWORDS_RUA,
)

def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


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

    notas_candidato = [
        max(SequenceMatcher(None, p_c, p_d).ratio() for p_d in t_dig)
        for p_c in t_cand
    ]
    pior_candidato = min(notas_candidato)
    if len(t_cand) > len(t_dig) and pior_candidato < 0.80:
        return min(sim_frase, media_palavras, pior_candidato)

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
