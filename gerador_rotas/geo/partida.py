import re

from gerador_rotas.dominio.constantes import CIDADES_RMBH, MAPA_NOMES_CIDADES, PREFIXOS_RUA
from gerador_rotas.dominio.endereco_texto import detectar_cidade_rmbh
from gerador_rotas.dominio.similaridade import remover_acentos
from gerador_rotas.geo.cep import consultar_cep_direto
from gerador_rotas.geo.geocodificadores import (
    buscar_coordenada_bairro,
    geocodificar_endereco_rua,
)
from gerador_rotas.geo.resolver_endereco import buscar_endereco_completo

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
            if lat is None or lon is None:
                return False, "❌ CEP encontrado, mas o ponto não foi localizado no mapa.", None, None
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
