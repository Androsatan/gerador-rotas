"""Lê o texto pronto de rota (endereço na linha de cima, cliente na de baixo)."""

import re

import pandas as pd

from gerador_rotas.dominio.endereco_texto import eh_linha_endereco
from gerador_rotas.dominio.parser_pedidos import chave_duplicidade
from gerador_rotas.dominio.similaridade import remover_acentos


def _titulo_rota(nome: str) -> str:
    limpo = str(nome or "").strip().upper()
    if not limpo:
        return "ROTA"
    if not limpo.startswith("ROTA"):
        return f"ROTA {limpo}"
    return limpo


def _nome_do_titulo(linha: str) -> str:
    base = re.split(r"\s*(?:—|–|\|)\s*", linha.strip(), maxsplit=1)[0]
    base = re.split(r"\s+-\s+", base, maxsplit=1)[0]
    return _titulo_rota(base)


def _eh_titulo_rota(linha: str) -> bool:
    """«ROTA 3» é título. Um endereço com CEP que comece com a palavra Rota não é."""
    bruta = linha.strip()
    if not re.match(r"^ROTA\b", bruta, flags=re.IGNORECASE):
        return False
    if re.search(r"\b\d{5}-?\d{3}\b", bruta):
        return False
    if bruta.count(",") >= 2:
        return False
    return True


def _eh_linha_de_resumo(linha: str) -> bool:
    if eh_linha_endereco(linha):
        return False
    limpa = remover_acentos(linha.lower())
    if re.search(r"\b(entrega|entregas|km)\b", limpa):
        return True
    return bool(re.fullmatch(r"[\d\s.|~-]*pacotes?", limpa.strip()))


def separar_linha_cliente(linha: str) -> tuple[str, str, int, str]:
    """Nome, sigla, pacotes e observação de uma linha como 'CAROLINE [TR] (2PCT)'."""
    texto = str(linha or "").strip()
    vendedor = ""
    achado = re.search(r"\[([^\]]+)\]", texto)
    if achado:
        vendedor = achado.group(1).strip().upper()
        texto = f"{texto[:achado.start()]} {texto[achado.end():]}"

    pacotes = 1
    observacoes = []

    def _trocar(match):
        nonlocal pacotes
        interno = match.group(1).strip()
        qtd = re.fullmatch(r"(\d+)\s*PCT", interno, flags=re.IGNORECASE)
        if qtd:
            pacotes = int(qtd.group(1))
        elif interno:
            observacoes.append(interno.upper())
        return " "

    texto = re.sub(r"\(([^)]*)\)", _trocar, texto)
    nome = re.sub(r"\s+", " ", texto).strip(" -,")
    return (nome.upper() or "CLIENTE"), vendedor, max(1, pacotes), " ".join(observacoes)


def extrair_paradas_de_rotas_prontas(texto: str) -> tuple[pd.DataFrame, list]:
    """Devolve as paradas na ordem colada e os nomes das rotas, sem mudar o endereço."""
    linhas = [ln.strip() for ln in str(texto or "").splitlines()]
    rota_atual = "ROTA"
    registros = []
    buffer = []
    contagem = {}

    def _guardar(endereco: str, cliente_linha: str, nome_rota: str):
        cliente, vendedor, pacotes, obs = separar_linha_cliente(cliente_linha)
        contagem[nome_rota] = contagem.get(nome_rota, 0) + 1
        registros.append({
            "Rota": nome_rota,
            "Ordem": f"{contagem[nome_rota]}º",
            "Posicao": "Normal",
            "Cliente": cliente,
            "Vendedor": vendedor,
            "Pacotes": pacotes,
            "Observacao": obs,
            "Endereco": str(endereco).strip(),
            "Lat": None,
            "Lon": None,
        })

    def _fechar_buffer(nome_rota: str):
        if not buffer:
            return
        if len(buffer) == 1:
            unica = buffer[0]
            if eh_linha_endereco(unica):
                _guardar(unica, "CLIENTE", nome_rota)
            return
        primeira, segunda = buffer[0], buffer[1]
        if eh_linha_endereco(primeira) and not eh_linha_endereco(segunda):
            _guardar(primeira, segunda, nome_rota)
        elif eh_linha_endereco(segunda) and not eh_linha_endereco(primeira):
            _guardar(segunda, primeira, nome_rota)
        else:
            _guardar(primeira, segunda, nome_rota)

    for linha in linhas:
        if _eh_titulo_rota(linha):
            if buffer:
                _fechar_buffer(rota_atual)
                buffer = []
            rota_atual = _nome_do_titulo(linha)
            continue
        if not linha or _eh_linha_de_resumo(linha):
            if buffer:
                _fechar_buffer(rota_atual)
                buffer = []
            continue
        buffer.append(linha)
        if len(buffer) == 2:
            _fechar_buffer(rota_atual)
            buffer = []

    if buffer:
        _fechar_buffer(rota_atual)

    nomes = []
    for registro in registros:
        if registro["Rota"] not in nomes:
            nomes.append(registro["Rota"])
    if not registros:
        return pd.DataFrame(), []
    return pd.DataFrame(registros), nomes


def _renumerar(df: pd.DataFrame) -> pd.DataFrame:
    contagem = {}
    ordens = []
    for rota in df["Rota"]:
        contagem[rota] = contagem.get(rota, 0) + 1
        ordens.append(f"{contagem[rota]}º")
    saida = df.copy()
    saida["Ordem"] = ordens
    return saida


def parada_avulsa(cliente_linha: str, endereco: str, rota: str) -> pd.DataFrame:
    """Um pedido solto, já destinado à rota escolhida. O endereço permanece como foi escrito."""
    endereco_limpo = str(endereco or "").strip()
    if not endereco_limpo:
        return pd.DataFrame()
    cliente, vendedor, pacotes, obs = separar_linha_cliente(cliente_linha or "CLIENTE")
    return pd.DataFrame([{
        "Rota": _titulo_rota(rota),
        "Ordem": "1º",
        "Posicao": "Normal",
        "Cliente": cliente,
        "Vendedor": vendedor,
        "Pacotes": pacotes,
        "Observacao": obs,
        "Endereco": endereco_limpo,
        "Lat": None,
        "Lon": None,
    }])


def remover_paradas_excluidas(df: pd.DataFrame, nomes_atuais: list):
    """Tira as linhas marcadas e some a rota que ficar sem ninguém."""
    base = df.copy()
    if "Excluir" in base.columns:
        marcados = base["Excluir"].fillna(False).astype(bool)
        base = base.loc[~marcados].drop(columns=["Excluir"])
    elif not base.empty:
        base = base.copy()
    base = base.reset_index(drop=True)
    if base.empty:
        return base, []
    base = _renumerar(base)
    nomes = [nome for nome in nomes_atuais if (base["Rota"] == nome).any()]
    for rota in base["Rota"]:
        if rota not in nomes:
            nomes.append(rota)
    return base, nomes


def acrescentar_paradas(df_atual: pd.DataFrame, nomes_atuais: list, df_novo: pd.DataFrame):
    """Soma paradas novas. Uma rota já existente recebe os clientes no fim."""
    if df_novo is None or df_novo.empty:
        return df_atual, list(nomes_atuais), []

    if df_atual is None or df_atual.empty:
        nomes = []
        for rota in df_novo["Rota"]:
            if rota not in nomes:
                nomes.append(rota)
        return _renumerar(df_novo), nomes, []

    ja_estao = {
        chave_duplicidade(row["Cliente"], row["Endereco"])
        for _, row in df_atual.iterrows()
    }
    pulados = []
    linhas = []
    for _, row in df_novo.iterrows():
        chave = chave_duplicidade(row["Cliente"], row["Endereco"])
        if chave in ja_estao:
            pulados.append(str(row["Cliente"]))
            continue
        ja_estao.add(chave)
        linhas.append(row)

    nomes = list(nomes_atuais)
    for rota in df_atual["Rota"]:
        if rota not in nomes:
            nomes.append(rota)
    if not linhas:
        return df_atual, nomes, pulados

    df_add = pd.DataFrame(linhas)
    partes = []
    for nome in nomes:
        bloco = df_atual[df_atual["Rota"] == nome]
        extra = df_add[df_add["Rota"] == nome]
        if not bloco.empty and not extra.empty:
            partes.append(pd.concat([bloco, extra], ignore_index=True))
        elif not bloco.empty:
            partes.append(bloco)
        elif not extra.empty:
            partes.append(extra)
    for nome in df_add["Rota"]:
        if nome not in nomes:
            nomes.append(nome)
            partes.append(df_add[df_add["Rota"] == nome])

    return _renumerar(pd.concat(partes, ignore_index=True)), nomes, pulados
