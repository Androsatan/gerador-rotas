import re
from urllib.parse import quote

import requests
import streamlit as st

from gerador_rotas.dominio.similaridade import (
    remover_acentos,
    similaridade_ruas,
    tokens_nucleo_rua,
)

@st.cache_data(ttl=86400, show_spinner=False)
def consultar_cep_direto(cep_digitos: str) -> dict:
    cep_limpo = re.sub(r"\D", "", str(cep_digitos))
    if len(cep_limpo) != 8:
        return {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RotasRMBH/3.0)"}

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
