"""Rotas abertas: a cota de cada entregador é fixa e a viagem termina no último cliente."""

from __future__ import annotations

import math
from itertools import permutations

import pandas as pd

from gerador_rotas.rotas.matriz import (
    distancia_km,
    obter_geometria_osrm,
    obter_matriz_osrm,
    obter_trajeto_osrm,
)

_INF = 10**15


def formatar_titulo_rota(nome: str) -> str:
    limpo = str(nome or "").strip().upper()
    if not limpo:
        return "ROTA"
    if not limpo.startswith("ROTA"):
        return f"ROTA {limpo}"
    return limpo


def _custo(matriz, i, j) -> float:
    if i == j:
        return 0.0
    try:
        valor = matriz[i][j]
    except (IndexError, TypeError):
        return float(_INF)
    if valor is None:
        return float(_INF)
    try:
        if pd.isna(valor):
            return float(_INF)
    except TypeError:
        pass
    return float(valor)


def _posicao(row) -> str:
    valor = row.get("Posicao", "Normal") if hasattr(row, "get") else "Normal"
    if valor is None:
        return "Normal"
    try:
        if pd.isna(valor):
            return "Normal"
    except TypeError:
        pass
    texto = str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
        return "Normal"
    return texto


def _tem_coord(row) -> bool:
    lat, lon = row.get("Lat"), row.get("Lon")
    if lat is None or lon is None:
        return False
    try:
        if pd.isna(lat) or pd.isna(lon):
            return False
    except TypeError:
        return False
    try:
        float(lat)
        float(lon)
    except (TypeError, ValueError):
        return False
    return True


def _respeita(ordem, primeiros, normais, ultimos) -> bool:
    rank = {node: i for i, node in enumerate(ordem)}

    def antes(grupo_a, grupo_b) -> bool:
        if not grupo_a or not grupo_b:
            return True
        return max(rank[a] for a in grupo_a) < min(rank[b] for b in grupo_b)

    return antes(primeiros, normais) and antes(primeiros, ultimos) and antes(normais, ultimos)


def _ordenar_dp_desde(matriz, nos: list[int], origem: int) -> list[int]:
    n = len(nos)
    if n <= 1:
        return list(nos)
    size = 1 << n
    dp = [[_INF] * n for _ in range(size)]
    parent = [[-1] * n for _ in range(size)]
    for i, node in enumerate(nos):
        dp[1 << i][i] = _custo(matriz, origem, node)
    for mask in range(size):
        for j in range(n):
            if not (mask & (1 << j)) or dp[mask][j] >= _INF:
                continue
            for k in range(n):
                if mask & (1 << k):
                    continue
                nmask = mask | (1 << k)
                custo = dp[mask][j] + _custo(matriz, nos[j], nos[k])
                if custo < dp[nmask][k]:
                    dp[nmask][k] = custo
                    parent[nmask][k] = j
    full = size - 1
    fim = min(range(n), key=lambda j: dp[full][j])
    if dp[full][fim] >= _INF:
        return list(nos)
    ordem_rev = []
    mask = full
    j = fim
    while j != -1:
        ordem_rev.append(nos[j])
        pj = parent[mask][j]
        mask &= ~(1 << j)
        j = pj
    ordem_rev.reverse()
    return ordem_rev


def _ordenar_brute(matriz, primeiros, normais, ultimos) -> list[int]:
    nos = list(primeiros) + list(normais) + list(ultimos)
    melhor = None
    melhor_c = float("inf")
    for perm in permutations(nos):
        if not _respeita(perm, primeiros, normais, ultimos):
            continue
        custo = 0.0
        ant = 0
        for node in perm:
            custo += _custo(matriz, ant, node)
            ant = node
        if custo < melhor_c:
            melhor_c = custo
            melhor = perm
    return list(melhor) if melhor is not None else nos


def _ordenar_guloso(matriz, nos: list[int], origem: int) -> list[int]:
    restantes = set(nos)
    ordem = []
    atual = origem
    while restantes:
        prox = min(restantes, key=lambda node: _custo(matriz, atual, node))
        ordem.append(prox)
        restantes.remove(prox)
        atual = prox
    return ordem


def _ordenar_ortools(matriz, n_stops: int, primeiros, normais, ultimos, segundos: int = 2):
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        return None

    manager = pywrapcp.RoutingIndexManager(n_stops + 1, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index, to_index):
        origem = manager.IndexToNode(from_index)
        destino = manager.IndexToNode(to_index)
        if destino == 0 and origem != 0:
            return 0
        return int(min(10**8, round(_custo(matriz, origem, destino))))

    callback = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    routing.AddDimension(callback, 0, 10**9, True, "Tempo")
    tempo = routing.GetDimensionOrDie("Tempo")
    solver = routing.solver()
    for anterior in primeiros:
        for posterior in list(normais) + list(ultimos):
            solver.Add(
                tempo.CumulVar(manager.NodeToIndex(anterior))
                <= tempo.CumulVar(manager.NodeToIndex(posterior))
            )
    for anterior in normais:
        for posterior in ultimos:
            solver.Add(
                tempo.CumulVar(manager.NodeToIndex(anterior))
                <= tempo.CumulVar(manager.NodeToIndex(posterior))
            )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(int(segundos))
    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    index = routing.Start(0)
    ordem = []
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != 0:
            ordem.append(node)
        index = solution.Value(routing.NextVar(index))
    if len(ordem) != n_stops:
        return None
    return ordem


def _cadeia_blocos(matriz, primeiros, normais, ultimos) -> list[int]:
    origem = 0
    ordem = []
    for grupo in (primeiros, normais, ultimos):
        if not grupo:
            continue
        if len(grupo) <= 16:
            parte = _ordenar_dp_desde(matriz, list(grupo), origem)
        else:
            parte = _ordenar_guloso(matriz, list(grupo), origem)
        ordem.extend(parte)
        origem = parte[-1]
    return ordem


def ordenar_paradas(matriz_tempo, matriz_dist, posicoes: list[str]) -> tuple[list[int], float]:
    """Ordem aberta das paradas. Índices retornados são posições em `posicoes`."""
    n = len(posicoes)
    if n == 0:
        return [], 0.0

    primeiros, normais, ultimos = [], [], []
    for i, pos in enumerate(posicoes):
        node = i + 1
        texto = str(pos or "Normal").upper().strip()
        if texto == "PRIMEIRO":
            primeiros.append(node)
        elif texto in ("ÚLTIMO", "ULTIMO"):
            ultimos.append(node)
        else:
            normais.append(node)

    nos = list(range(1, n + 1))
    if primeiros or ultimos:
        if n <= 9:
            ordem_nodes = _ordenar_brute(matriz_tempo, primeiros, normais, ultimos)
        else:
            ordem_nodes = _ordenar_ortools(matriz_tempo, n, primeiros, normais, ultimos)
            if not ordem_nodes or not _respeita(ordem_nodes, primeiros, normais, ultimos):
                ordem_nodes = _cadeia_blocos(matriz_tempo, primeiros, normais, ultimos)
    elif n <= 16:
        ordem_nodes = _ordenar_dp_desde(matriz_tempo, nos, 0)
    else:
        ordem_nodes = _ordenar_ortools(matriz_tempo, n, [], nos, []) or _ordenar_guloso(matriz_tempo, nos, 0)

    km = 0.0
    ant = 0
    for node in ordem_nodes:
        km += _custo(matriz_dist, ant, node)
        ant = node
    return [node - 1 for node in ordem_nodes], round(km / 1000.0, 1)


def atribuir_paradas(matriz_tempo, cotas: list[int], segundos: int = 3):
    """Reparte as paradas entre as cotas. None se o solver não achar solução.

    O índice 0 da matriz é a partida. O retorno lista, por veículo, os índices
    das paradas (0 = primeira parada da matriz).
    """
    n = len(matriz_tempo) - 1
    n_veh = len(cotas)
    if n <= 0:
        return [[] for _ in cotas]
    if n_veh <= 1:
        return [list(range(n))]
    if n > sum(int(c) for c in cotas):
        return None

    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        return None

    manager = pywrapcp.RoutingIndexManager(n + 1, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index, to_index):
        origem = manager.IndexToNode(from_index)
        destino = manager.IndexToNode(to_index)
        if destino == 0 and origem != 0:
            return 0
        return int(min(10**8, round(_custo(matriz_tempo, origem, destino))))

    callback = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(callback)

    def demanda(from_index):
        return 0 if manager.IndexToNode(from_index) == 0 else 1

    dem_cb = routing.RegisterUnaryTransitCallback(demanda)
    routing.AddDimensionWithVehicleCapacity(
        dem_cb,
        0,
        [int(c) for c in cotas],
        True,
        "Cota",
    )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(int(segundos))
    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    grupos = []
    for v in range(n_veh):
        index = routing.Start(v)
        seq = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                seq.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        grupos.append(seq)

    if sorted(i for g in grupos for i in g) != list(range(n)):
        return None
    for grupo, cota in zip(grupos, cotas):
        if len(grupo) > int(cota):
            return None
    return grupos


def _atribuir_por_angulo(coords, cotas: list[int]):
    n = len(coords) - 1
    depot = coords[0]
    ordem = sorted(
        range(n),
        key=lambda i: math.atan2(coords[i + 1][0] - depot[0], coords[i + 1][1] - depot[1]),
    )
    grupos = [[] for _ in cotas]
    cursor = 0
    for v, cota in enumerate(cotas):
        for _ in range(max(0, int(cota))):
            if cursor >= n:
                break
            grupos[v].append(ordem[cursor])
            cursor += 1
    while cursor < n and grupos:
        grupos[-1].append(ordem[cursor])
        cursor += 1
    return grupos


def _submatriz(matriz, indices_matriz: list[int]):
    m = len(indices_matriz)
    sub = [[0.0] * m for _ in range(m)]
    for a in range(m):
        for b in range(m):
            sub[a][b] = _custo(matriz, indices_matriz[a], indices_matriz[b])
    return sub


def _ordenar_grupo(df, indices, lat, lon, mat_t, mat_d, nos_matriz):
    if not indices:
        return [], 0.0
    posicoes = [_posicao(df.loc[i]) for i in indices]
    sub_t = _submatriz(mat_t, nos_matriz)
    sub_d = _submatriz(mat_d, nos_matriz)
    ordem_local, km = ordenar_paradas(sub_t, sub_d, posicoes)
    return [indices[i] for i in ordem_local], km


def _geometria(df, lat, lon, indices):
    pontos = [(float(lat), float(lon))]
    for i in indices:
        if _tem_coord(df.loc[i]):
            pontos.append((float(df.at[i, "Lat"]), float(df.at[i, "Lon"])))
    if len(pontos) < 2:
        return [[p[0], p[1]] for p in pontos], True
    geom = obter_geometria_osrm(pontos)
    if geom:
        return geom, True
    return [[p[0], p[1]] for p in pontos], False


def _montar_saida(df, nomes, listas):
    linhas = []
    for nome, indices in zip(nomes, listas):
        for n, idx in enumerate(indices, start=1):
            row = df.loc[idx].copy()
            row["Rota"] = nome
            row["Ordem"] = f"{n}º"
            linhas.append(row)
    if not linhas:
        return df.iloc[0:0].copy()
    return pd.DataFrame(linhas).reset_index(drop=True)


def gerar_rotas(df: pd.DataFrame, nomes: list, cotas: list, lat: float, lon: float, matriz=None, buscar_geometria: bool = True):
    """Divide pelas cotas e ordena cada rota até o último cliente."""
    avisos = []
    base = df.copy().reset_index(drop=True)
    if base.empty:
        return base, {n: 0.0 for n in nomes}, (lat, lon), {}, avisos

    validos = [i for i in base.index if _tem_coord(base.loc[i])]
    faltantes = [i for i in base.index if i not in set(validos)]

    if not validos:
        avisos.append("Nenhum endereço tem coordenada. A divisão seguiu só a quantidade de cada rota.")
        listas = [[] for _ in nomes]
        cursor = 0
        for v, cota in enumerate(cotas):
            for _ in range(int(cota)):
                if cursor >= len(faltantes):
                    break
                listas[v].append(faltantes[cursor])
                cursor += 1
        while cursor < len(faltantes) and listas:
            listas[-1].append(faltantes[cursor])
            cursor += 1
        return _montar_saida(base, nomes, listas), {n: 0.0 for n in nomes}, (lat, lon), {}, avisos

    pontos = [(float(lat), float(lon))] + [
        (float(base.at[i, "Lat"]), float(base.at[i, "Lon"])) for i in validos
    ]
    if matriz is None:
        mat_t, mat_d, fonte = obter_matriz_osrm(pontos)
    else:
        mat_t, mat_d = matriz
        fonte = "informada"
    if fonte == "estimada":
        avisos.append("O mapa de ruas não respondeu. A ordem usou distância estimada, sem considerar a via.")
    elif fonte == "osrm-parcial":
        avisos.append("Parte do caminho foi estimada porque o mapa de ruas não conhecia algum trecho.")

    grupos = None
    if len(validos) <= sum(int(c) for c in cotas):
        grupos = atribuir_paradas(mat_t, cotas)
    if grupos is None:
        avisos.append("A divisão geográfica usou os setores em volta da partida para fechar a cota.")
        grupos = _atribuir_por_angulo(pontos, cotas)

    listas = []
    resumo = {}
    geometrias = {}
    geometria_ok = True
    folga = []
    for v, grupo in enumerate(grupos):
        df_idx = [validos[i] for i in grupo]
        nos = [0] + [i + 1 for i in grupo]
        ordenados, km = _ordenar_grupo(base, df_idx, lat, lon, mat_t, mat_d, nos)
        listas.append(ordenados)
        resumo[nomes[v]] = km
        folga.append(max(0, int(cotas[v]) - len(ordenados)))

    for idx_falt in faltantes:
        destino = next((v for v, qtd in enumerate(folga) if qtd > 0), len(listas) - 1)
        listas[destino].append(idx_falt)
        if folga[destino] > 0:
            folga[destino] -= 1

    if faltantes:
        amostra = ", ".join(str(base.at[i, "Cliente"]) for i in faltantes[:8])
        avisos.append(
            f"{len(faltantes)} entrega(s) sem coordenada foram para o fim da rota: {amostra}"
        )

    if buscar_geometria:
        for v, nome in enumerate(nomes):
            geom, ok = _geometria(base, lat, lon, listas[v])
            geometrias[nome] = geom
            geometria_ok = geometria_ok and ok
        if not geometria_ok:
            avisos.append("O traçado da rua não carregou em alguma rota. O mapa liga as paradas em linha reta.")

    return _montar_saida(base, nomes, listas), resumo, (lat, lon), geometrias, avisos


def medir_rotas_na_ordem(df_com_rotas: pd.DataFrame, ordem_nomes_rotas: list, lat_s: float, lon_s: float):
    """Km e traçado da ordem atual. Não troca a sequência nem o endereço."""
    avisos = []
    resumo = {}
    geometrias = {}
    alguma_reta = False
    base = df_com_rotas.copy().reset_index(drop=True)

    for nome in ordem_nomes_rotas:
        indices = [i for i in base.index if str(base.at[i, "Rota"]) == nome and _tem_coord(base.loc[i])]
        pontos = [(float(lat_s), float(lon_s))]
        for i in indices:
            pontos.append((float(base.at[i, "Lat"]), float(base.at[i, "Lon"])))
        if len(pontos) < 2:
            resumo[nome] = 0.0
            geometrias[nome] = [[p[0], p[1]] for p in pontos]
            continue
        geom, metros = obter_trajeto_osrm(pontos)
        if geom and metros is not None:
            geometrias[nome] = geom
            resumo[nome] = round(metros / 1000.0, 1)
            continue
        alguma_reta = True
        geometrias[nome] = [[p[0], p[1]] for p in pontos]
        km = 0.0
        for a in range(len(pontos) - 1):
            km += distancia_km(pontos[a][0], pontos[a][1], pontos[a + 1][0], pontos[a + 1][1]) * 1.35
        resumo[nome] = round(km, 1)

    if alguma_reta:
        avisos.append("O traçado da rua não carregou em alguma rota. O mapa liga as paradas em linha reta.")
    return resumo, geometrias, avisos


def recalcular_todas_as_rotas(df_com_rotas: pd.DataFrame, ordem_nomes_rotas: list, lat_s: float, lon_s: float, buscar_geometria: bool = True):
    """Reordena cada rota já atribuída. Não mexe na quantidade de cada entregador."""
    avisos = []
    base = df_com_rotas.copy().reset_index(drop=True)
    if base.empty:
        return base, {n: 0.0 for n in ordem_nomes_rotas}, (lat_s, lon_s), {}, avisos

    listas = []
    resumo = {}
    geometrias = {}
    fonte_ruim = False
    geometria_ok = True

    for nome in ordem_nomes_rotas:
        indices = [i for i in base.index if str(base.at[i, "Rota"]) == nome]
        geocod = [i for i in indices if _tem_coord(base.loc[i])]
        sem = [i for i in indices if i not in set(geocod)]
        if not geocod:
            listas.append(indices)
            resumo[nome] = 0.0
            geometrias[nome] = []
            continue
        pontos = [(float(lat_s), float(lon_s))] + [
            (float(base.at[i, "Lat"]), float(base.at[i, "Lon"])) for i in geocod
        ]
        mat_t, mat_d, fonte = obter_matriz_osrm(pontos)
        if fonte != "osrm":
            fonte_ruim = True
        nos = list(range(len(pontos)))
        ordenados, km = _ordenar_grupo(base, geocod, lat_s, lon_s, mat_t, mat_d, nos)
        listas.append(ordenados + sem)
        resumo[nome] = km
        if buscar_geometria:
            geom, ok = _geometria(base, lat_s, lon_s, ordenados)
            geometrias[nome] = geom
            geometria_ok = geometria_ok and ok

    if fonte_ruim:
        avisos.append("O mapa de ruas não respondeu. A ordem usou distância estimada, sem considerar a via.")
    if buscar_geometria and not geometria_ok:
        avisos.append("O traçado da rua não carregou em alguma rota. O mapa liga as paradas em linha reta.")

    conhecidos = set(ordem_nomes_rotas)
    resto = [i for i in base.index if str(base.at[i, "Rota"]) not in conhecidos]
    nomes_saida = list(ordem_nomes_rotas)
    listas_saida = listas
    if resto:
        nomes_saida = nomes_saida + ["FORA DA LISTA"]
        listas_saida = listas_saida + [resto]

    return _montar_saida(base, nomes_saida, listas_saida), resumo, (lat_s, lon_s), geometrias, avisos
