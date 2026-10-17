import re

from gerador_rotas.dominio.constantes import (
    CIDADES_RMBH,
    MAPA_BAIRROS_RMBH,
    MAPA_NOMES_CIDADES,
    PALAVRAS_NAO_ENDERECO,
    PREFIXOS_RUA,
    REGIONAIS_BH,
)
from gerador_rotas.dominio.similaridade import remover_acentos, similaridade_palavras

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

def linha_pode_ser_bairro_informado(linha: str, linha_seguinte: str = "", locais_dict: dict = None) -> bool:
    """Linha curta logo depois da rua, sem produto em seguida, é o bairro.

    «Lourdes» no fim do pedido é o bairro. «Vinicius» seguido de «2 g md» é o cliente.
    """
    bruta = str(linha or "").strip()
    limpa = remover_acentos(bruta.lower())
    if not limpa or eh_subtitulo_ou_divisoria(bruta):
        return False
    if eh_linha_endereco(bruta, locais_dict) or eh_linha_produto_clara(bruta, locais_dict):
        return False
    if texto_parece_produto_cadastrado(bruta, locais_dict):
        return False
    if re.search(r"\d", bruta):
        return False
    if re.match(r"^(cliente|nome|pedido|ped|mercadoria|itens?|produtos?|endereco|end\.?)\s*[:\-]", limpa):
        return False
    palavras = re.findall(r"[a-zA-ZÀ-ÿ]{2,}", bruta)
    if not (1 <= len(palavras) <= 4) or len(bruta) > 40:
        return False
    seguinte = str(linha_seguinte or "").strip()
    if seguinte and (eh_linha_produto_clara(seguinte, locais_dict) or texto_parece_produto_cadastrado(seguinte, locais_dict)):
        return False
    return True

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
    end_limpo = re.sub(r"\b(endere[cç]o|end\.?|local|entrega)\s*[:\-]?\s*", " ", end_limpo, flags=re.IGNORECASE).strip()
    end_limpo = re.sub(r"\([^)]*\)", " ", end_limpo)
    end_limpo = re.sub(r"^(av|r|al|tv)\.([a-zA-Z])", r"\1. \2", end_limpo, flags=re.IGNORECASE)
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

    rua = re.sub(r"\s+", " ", rua).strip(" ,.-:")
    bairro_dica = re.sub(r"\s+", " ", bairro_dica).strip(" ,.-:")

    return rua, numero, bairro_dica, cidade_detectada

def dentro_perimetro_rmbh(lat: float, lon: float) -> bool:
    return (-20.40 <= lat <= -19.40) and (-44.60 <= lon <= -43.40)

def eh_regional_bh(nome_b: str) -> bool:
    if not nome_b:
        return False
    return remover_acentos(nome_b.lower()).strip() in REGIONAIS_BH

def eh_nome_de_cidade(nome: str) -> bool:
    if not nome:
        return False
    n = remover_acentos(str(nome).lower()).strip()
    if n in CIDADES_RMBH:
        return True
    return any(n == remover_acentos(oficial.lower()) for oficial in MAPA_NOMES_CIDADES.values())

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

def numero_cabe_na_faixa_viacep(numero_str: str, complemento_viacep: str) -> bool:
    if not numero_str:
        return True
    try:
        num = int(re.sub(r"\D", "", numero_str))
    except ValueError:
        return True
    if not complemento_viacep or not str(complemento_viacep).strip():
        return False

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

    numeros = [int(n) for n in re.findall(r"\d+", comp)]
    if numeros:
        return num in numeros
    return False
