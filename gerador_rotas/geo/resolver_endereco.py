import math
import re

import streamlit as st

from gerador_rotas.dominio.endereco_texto import (
    cidade_escrita,
    cidades_rmbh_para_busca,
    eh_nome_de_cidade,
    eh_regional_bh,
    escolher_registro_viacep,
    formatar_via_com_prefixo,
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
    numero_confirmado_viacep = False
    bairro_travado = False
    bairro_vem_do_cep = False

    def bairro_util(nome_b, aceitar_regional=False):
        nome = str(nome_b or "").strip()
        if not nome or eh_nome_de_cidade(nome):
            return False
        if eh_regional_bh(nome) and not aceitar_regional:
            return False
        return True

    def adotar_bairro(nome, do_cep=False):
        nonlocal bairro_oficial, bairro_vem_do_cep
        texto = str(nome or "").strip()
        if not texto:
            return
        bairro_oficial = texto
        if do_cep or eh_regional_bh(texto):
            bairro_vem_do_cep = True

    def registrar_opcao_bairro(logr_op, bair_op, cid_op, cep_op, aceitar_regional=False):
        b_limpo = str(bair_op).strip()
        if not bairro_util(b_limpo, aceitar_regional=aceitar_regional):
            return
        if logr_op and similaridade_ruas(rua, logr_op) < 0.90:
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

    cidades_para_testar = cidades_rmbh_para_busca(cidade)
    cidade_fixa = bool(cidade_escrita(str(endereco_bruto))) or cidade != "Belo Horizonte"

    if len(rua_sem_prefixo) >= 2:
        for cid_teste in cidades_para_testar:
            if cidade_fixa and cid_teste != cidade:
                break
            try:
                dados_viacep = consultar_viacep_com_tolerancia(rua, rua_sem_prefixo, cid_teste)
            except ConnectionError:
                if cid_teste == cidade:
                    break
                continue
            if not dados_viacep:
                continue

            mesma_rua = [
                d for d in dados_viacep
                if d.get("bairro") and similaridade_ruas(rua, d.get("logradouro", "")) >= 0.90
            ]
            if not mesma_rua:
                if cid_teste == cidade:
                    melhor_bh = max(
                        similaridade_ruas(rua, d.get("logradouro", "")) for d in dados_viacep
                    )
                    if melhor_bh >= 0.80:
                        break
                continue

            decisao = escolher_registro_viacep(mesma_rua, numero, bairro_dica)
            if decisao["bairro_travado"] and decisao["escolhido"]:
                escolhido = decisao["escolhido"]
                mapa_bairros_opcoes.clear()
                logradouro_oficial = formatar_via_com_prefixo(escolhido.get("logradouro", ""), rua)
                adotar_bairro(escolhido.get("bairro") or bairro_dica, do_cep=True)
                cidade_oficial = escolhido.get("localidade", cid_teste)
                cep_encontrado = escolhido.get("cep", "") or cep_encontrado
                numero_confirmado_viacep = True
                bairro_travado = True
                break
            if bairro_dica and not decisao["bairro_travado"] and cid_teste != cidade:
                mapa_bairros_opcoes.clear()
                continue

            if decisao["escolhido"]:
                escolhido = decisao["escolhido"]
                if bairro_dica and similaridade_bairros(bairro_dica, escolhido.get("bairro") or "") < 0.72:
                    mapa_bairros_opcoes.clear()
                    if cid_teste == cidade:
                        break
                    continue
                mapa_bairros_opcoes.clear()
                logradouro_oficial = formatar_via_com_prefixo(escolhido.get("logradouro", ""), rua)
                adotar_bairro(escolhido.get("bairro", ""), do_cep=True)
                cidade_oficial = escolhido.get("localidade", cid_teste)
                cep_encontrado = escolhido.get("cep", "") or cep_encontrado
                numero_confirmado_viacep = True
                break

            if decisao["opcoes"]:
                logradouro_oficial = formatar_via_com_prefixo(
                    decisao["opcoes"][0].get("logradouro", ""), rua
                )
                cidade_oficial = decisao["opcoes"][0].get("localidade", cid_teste)
                for item in decisao["opcoes"]:
                    registrar_opcao_bairro(
                        item.get("logradouro") or rua,
                        item.get("bairro", ""),
                        item.get("localidade") or cid_teste,
                        item.get("cep", ""),
                        aceitar_regional=True,
                    )
                break

    candidatos_geo = buscar_candidatos_multifonte(
        logradouro_oficial if logradouro_oficial else rua,
        numero,
        bairro_oficial if bairro_oficial else bairro_dica,
        cidade_oficial
    )
    if candidatos_geo and cidade_oficial:
        na_cidade = [
            cg for cg in candidatos_geo
            if not cg.get("cidade")
            or remover_acentos(str(cg.get("cidade")).lower()) == remover_acentos(cidade_oficial.lower())
        ]
        candidatos_geo = na_cidade

    def metros_entre(lat1, lon1, lat2, lon2):
        raio = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * raio * math.asin(math.sqrt(min(1.0, a)))

    if candidatos_geo:
        if not numero_confirmado_viacep and not bairro_dica:
            ancoras = []
            for cg in candidatos_geo:
                bairro_cg = cg.get("bairro") or ""
                if not bairro_util(bairro_cg, aceitar_regional=True):
                    continue
                if similaridade_ruas(rua, cg.get("logradouro", "")) < 0.90:
                    continue
                if cg.get("lat") is None or cg.get("lon") is None:
                    continue
                mesmo_lugar = False
                for alat, alon, abairro in ancoras:
                    if similaridade_bairros(bairro_cg, abairro) >= 0.72 or metros_entre(cg["lat"], cg["lon"], alat, alon) < 400:
                        mesmo_lugar = True
                        break
                if mesmo_lugar:
                    continue
                ancoras.append((cg["lat"], cg["lon"], bairro_cg))
                if len(ancoras) > 1:
                    registrar_opcao_bairro(
                        cg["logradouro"], bairro_cg, cg["cidade"], cg.get("cep") or cep_encontrado,
                        aceitar_regional=True,
                    )
            if len(ancoras) > 1 and candidatos_geo:
                primeiro = next(
                    (
                        cg for cg in candidatos_geo
                        if bairro_util(cg.get("bairro"), aceitar_regional=True)
                        and similaridade_ruas(rua, cg.get("logradouro", "")) >= 0.90
                    ),
                    None,
                )
                if primeiro:
                    registrar_opcao_bairro(
                        primeiro["logradouro"],
                        primeiro["bairro"],
                        primeiro["cidade"],
                        primeiro.get("cep") or cep_encontrado,
                        aceitar_regional=True,
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
        if not bairro_oficial and len(mapa_bairros_opcoes) < 2:
            if melhor_cg.get("bairro") and bairro_util(melhor_cg["bairro"], aceitar_regional=True) and (
                not bairro_dica or similaridade_bairros(bairro_dica, melhor_cg["bairro"]) >= 0.65
            ):
                adotar_bairro(melhor_cg["bairro"], do_cep=eh_regional_bh(melhor_cg["bairro"]))
            elif bairro_dica and bairro_util(bairro_dica, aceitar_regional=True):
                adotar_bairro(bairro_dica.title(), do_cep=eh_regional_bh(bairro_dica))
            elif melhor_cg.get("bairro") and bairro_util(melhor_cg["bairro"], aceitar_regional=True):
                adotar_bairro(melhor_cg["bairro"], do_cep=eh_regional_bh(melhor_cg["bairro"]))
    if cep_encontrado:
        dados_cep = consultar_cep_direto(cep_encontrado)
        if dados_cep and dados_cep.get("logradouro"):
            if similaridade_ruas(rua, dados_cep["logradouro"]) >= 0.65 or not logradouro_oficial:
                logradouro_oficial = formatar_via_com_prefixo(dados_cep["logradouro"], rua)
                if dados_cep.get("bairro") and bairro_util(dados_cep["bairro"], aceitar_regional=True):
                    combina = similaridade_bairros(bairro_oficial, dados_cep["bairro"]) >= 0.72
                    if bairro_travado and not combina:
                        pass
                    elif not numero_confirmado_viacep or not bairro_oficial or combina:
                        adotar_bairro(dados_cep["bairro"], do_cep=True)
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
    if bairro_oficial and bairro_util(bairro_oficial, aceitar_regional=bairro_vem_do_cep or bairro_travado):
        bairro_final = bairro_oficial
    elif bairro_dica and bairro_util(bairro_dica, aceitar_regional=True):
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

    opcoes_bairros = []
    if not bairro_travado:
        vistas = set()
        for texto_op in mapa_bairros_opcoes.values():
            chave_op = remover_acentos(texto_op.lower())
            if chave_op in vistas:
                continue
            vistas.add(chave_op)
            opcoes_bairros.append(texto_op)
        if len(opcoes_bairros) < 2:
            opcoes_bairros = []

    if len(opcoes_bairros) > 1:
        status = f"⚠️ {len(opcoes_bairros)} BAIRROS ENCONTRADOS (ESCOLHER)"
    elif bairro_final == "Bairro não identificado":
        status = "⚠️ INCOMPLETO (CONFERIR BAIRRO/CEP)"
    else:
        status = "✅ OK"

    if (lat is None or lon is None) and status == "✅ OK":
        status = "⚠️ ENDEREÇO SEM COORDENADA NO MAPA"

    return endereco_padronizado, status, lat, lon, opcoes_bairros
