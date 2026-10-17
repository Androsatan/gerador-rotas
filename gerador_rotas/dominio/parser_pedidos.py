import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from gerador_rotas.dominio.constantes import REGEX_CABECALHO_CHAT
from gerador_rotas.dominio.endereco_texto import (
    eh_complemento_pos_endereco,
    eh_linha_endereco,
    eh_linha_produto_clara,
    eh_subtitulo_ou_divisoria,
    limpar_nome_cliente,
    pode_ser_nome_cliente,
    separar_componentes_endereco,
)
from gerador_rotas.dominio.produtos import identificar_locais_dos_itens
from gerador_rotas.dominio.similaridade import remover_acentos
from gerador_rotas.geo.resolver_endereco import buscar_endereco_completo

def extrair_dados_brutos_do_bloco(linhas_bloco: list, locais_dict: dict, vendedor_padrao: str = "") -> list:
    linhas_endereco = []
    outras_linhas = []

    for linha in linhas_bloco:
        l_strip = linha.strip()
        if not l_strip or eh_subtitulo_ou_divisoria(l_strip):
            continue

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

    cliente_atual = None
    itens_atuais = []

    for tipo, valor in outras_linhas:
        if tipo == "NOME":
            if cliente_atual is None:
                cliente_atual = valor
        else:
            itens_atuais.append(valor)

    sub_pedidos = []
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

def _bloco_tem_endereco(bloco: list, locais_dict: dict) -> bool:
    return any(eh_linha_endereco(linha, locais_dict) for linha in bloco)

def _fundir_continuacao_sem_endereco(blocos: list, locais_dict: dict) -> list:
    """Junta ao pedido anterior as linhas que ficaram sem endereço.

    O endereço no topo seguido de vários nomes partia o texto em dois:
    o endereço sozinho e os nomes à parte. Esses nomes são o mesmo pedido.
    """
    if not blocos:
        return []
    fundidos = [list(blocos[0])]
    for bloco in blocos[1:]:
        if fundidos and not _bloco_tem_endereco(bloco, locais_dict):
            fundidos[-1].extend(bloco)
        else:
            fundidos.append(list(bloco))
    return fundidos

def listar_pre_pedidos(texto_bruto: str, locais_dict: dict, vendedor_padrao: str = "") -> list:
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
        blocos = _fundir_continuacao_sem_endereco(blocos, locais_dict)

    pre_pedidos = []
    for b in blocos:
        pre_pedidos.extend(extrair_dados_brutos_do_bloco(b, locais_dict, vendedor_padrao))
    return pre_pedidos

def extrair_pedidos_brutos(texto_bruto: str, locais_dict: dict, vendedor_padrao: str = ""):
    pre_pedidos = listar_pre_pedidos(texto_bruto, locais_dict, vendedor_padrao)

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
