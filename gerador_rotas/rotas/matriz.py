import math

import requests

_BBOX_PHOTON = "-44.60,-20.40,-43.40,-19.40"


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    raio = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * raio * math.asin(math.sqrt(min(1.0, a)))


def _par_estimado(lat1, lon1, lat2, lon2):
    metros = distancia_km(lat1, lon1, lat2, lon2) * 1.35 * 1000.0
    segundos = metros / 8.33
    return segundos, metros


def obter_matriz_osrm(pontos_lat_lon: list):
    """Retorna (duracao_segundos, distancia_metros, fonte).

    fonte é "osrm" ou "estimada". Na estimativa, a rua é ignorada.
    """
    m = len(pontos_lat_lon)
    dur = [[0.0] * m for _ in range(m)]
    dist = [[0.0] * m for _ in range(m)]

    def preencher_estimado():
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                dur[i][j], dist[i][j] = _par_estimado(
                    pontos_lat_lon[i][0], pontos_lat_lon[i][1],
                    pontos_lat_lon[j][0], pontos_lat_lon[j][1],
                )

    if m <= 1:
        return dur, dist, "osrm"

    try:
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in pontos_lat_lon)
        url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and "durations" in data:
                bruta_dur = data["durations"]
                bruta_dist = data.get("distances") or bruta_dur
                completa = True
                for i in range(m):
                    for j in range(m):
                        if i == j:
                            continue
                        d_seg = bruta_dur[i][j]
                        d_m = bruta_dist[i][j]
                        if d_seg is None or d_m is None:
                            dur[i][j], dist[i][j] = _par_estimado(
                                pontos_lat_lon[i][0], pontos_lat_lon[i][1],
                                pontos_lat_lon[j][0], pontos_lat_lon[j][1],
                            )
                            completa = False
                        else:
                            dur[i][j] = float(d_seg)
                            dist[i][j] = float(d_m)
                return dur, dist, "osrm" if completa else "osrm-parcial"
    except Exception:
        pass

    preencher_estimado()
    return dur, dist, "estimada"


def obter_geometria_osrm(pontos_lat_lon: list):
    """Linha da rua em [lat, lon]. None se o serviço não responder."""
    if len(pontos_lat_lon) < 2:
        return [[p[0], p[1]] for p in pontos_lat_lon]
    try:
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in pontos_lat_lon)
        url = (
            "http://router.project-osrm.org/route/v1/driving/"
            f"{coords}?overview=full&geometries=geojson"
        )
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        linha = data["routes"][0]["geometry"]["coordinates"]
        return [[float(c[1]), float(c[0])] for c in linha]
    except Exception:
        return None
