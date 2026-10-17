import re

import pandas as pd

from gerador_rotas.dominio.endereco_texto import eh_linha_endereco
from gerador_rotas.dominio.parser_pedidos import montar_linha_cliente

def limpar_nome_para_etiqueta(nome_bruto: str) -> str:
    sem_vendedor = re.sub(r"\[.*?\]", "", str(nome_bruto))
    sem_espacos_duplos = re.sub(r"\s+", " ", sem_vendedor).strip()
    return sem_espacos_duplos.upper()


def formatar_endereco_para_etiqueta(endereco_bruto: str) -> str:
    end = str(endereco_bruto).strip()
    end = re.sub(r",\s*\d{5}-?\d{3}\s*-\s*", " - ", end)
    end = re.sub(r"\s+", " ", end).strip(" ,")
    return end


def endereco_etiqueta_precisa_busca(endereco: str) -> bool:
    """Rua solta, sem CEP, ainda precisa da mesma busca usada nas rotas."""
    texto = str(endereco or "").strip()
    if not texto:
        return False
    return re.search(r"\b\d{5}-?\d{3}\b", texto) is None


def endereco_de_etiqueta_resolvido(endereco_bruto: str, end_form: str, status: str) -> str:
    if str(end_form or "").strip() and not str(status).startswith("❌"):
        return formatar_endereco_para_etiqueta(end_form)
    return formatar_endereco_para_etiqueta(endereco_bruto)

def extrair_etiquetas_de_texto_rota(texto_colado: str) -> pd.DataFrame:
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
