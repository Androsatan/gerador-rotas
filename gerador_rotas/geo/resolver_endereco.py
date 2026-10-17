import re

import streamlit as st

from gerador_rotas.dominio.endereco_texto import (
    eh_regional_bh,
    formatar_via_com_prefixo,
    numero_cabe_na_faixa_viacep,
    separar_componentes_endereco,
)
from gerador_rotas.dominio.similaridade import (
    remover_acentos,
    similaridade_bairros,
    similaridade_ruas,
)
from gerador_rotas.geo.cep import consultar_cep_direto, consultar_viacep_com_tolerancia
from gerador_rotas.geo.geocodificadores import (
    buscar_candidatos_multifonte,
    buscar_coordenada_bairro,
    geocodificar_endereco_rua,
)

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_endereco_completo(endereco_bruto: str):
    if not str(endereco_bruto).strip():
        return "", "❌ NÃO ENCONTRADO - CORRIGIR", None, None, []

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
                mapa_bairros_opcoes.clear()
            elif bairro_dica and cid_teste != cidade:
                continue
            else:
                escolhido = candidatos_faixa[0] if candidatos_faixa else dados_viacep[0]

            logradouro_oficial = formatar_via_com_prefixo(escolhido.get("logradouro", ""), rua)
            bairro_oficial = escolhido.get("bairro", "")
            cidade_oficial = escolhido.get("localidade", cid_teste)
            cep_encontrado = escolhido.get("cep", "") or cep_encontrado
            break

    candidatos_geo = buscar_candidatos_multifonte(
        logradouro_oficial if logradouro_oficial else rua,
        numero,
        bairro_oficial if bairro_oficial else bairro_dica,
        cidade_oficial
    )

    if candidatos_geo:
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

    if (lat is None or lon is None) and status == "✅ OK":
        status = "⚠️ ENDEREÇO SEM COORDENADA NO MAPA"

    return endereco_padronizado, status, lat, lon, opcoes_bairros
