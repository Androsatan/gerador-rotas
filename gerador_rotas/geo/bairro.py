"""Localiza um bairro da RMBH pelo nome, sem coordenada gravada no código."""

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from gerador_rotas.dominio.endereco_texto import dentro_perimetro_rmbh
from gerador_rotas.dominio.similaridade import (
    nome_bairro_partida_bate,
    remover_acentos,
    similaridade_bairros,
)

_TIPOS_RUA = {
    "highway", "road", "street", "pedestrian", "service", "residential",
    "streetaddress", "pointaddress", "streetname", "livingstreet",
}
_TIPOS_BAIRRO = {
    "neighborhood", "neighbourhood", "suburb", "quarter", "locality",
    "district", "city_district", "administrative", "hamlet", "borough",
}
_HEADERS = {"User-Agent": "GeradorRotasRMBH/3.0 (contato@geradorrotas.app)"}


def escolher_candidato_bairro(nome_buscado: str, candidatos: list) -> dict | None:
    melhor = None
    melhor_nota = -1.0
    for cand in candidatos:
        nome = str(cand.get("nome") or "").strip()
        lat, lon = cand.get("lat"), cand.get("lon")
        if not nome or lat is None or lon is None:
            continue
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not dentro_perimetro_rmbh(lat_f, lon_f):
            continue
        if not nome_bairro_partida_bate(nome_buscado, nome):
            continue
        tipo = remover_acentos(str(cand.get("tipo") or "").lower()).replace(" ", "")
        if tipo in _TIPOS_RUA:
            continue
        nota = similaridade_bairros(nome_buscado, nome)
        if tipo in _TIPOS_BAIRRO:
            nota += 0.35
        if nota > melhor_nota:
            melhor_nota = nota
            melhor = {**cand, "lat": lat_f, "lon": lon_f, "nome": nome}
    return melhor


def _arcgis(consulta: str, cidade: str):
    url = (
        "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
        f"?SingleLine={quote(consulta)}&category=Neighborhood,Locality,Subregion"
        "&searchExtent=-44.60,-20.40,-43.40,-19.40"
        "&outFields=Addr_type,PlaceName,Nbrhd,City&maxLocations=8&f=json"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=4)
    resp.raise_for_status()
    saida = []
    for c in resp.json().get("candidates", []):
        if c.get("score", 0) < 70:
            continue
        loc = c.get("location") or {}
        if loc.get("y") is None or loc.get("x") is None:
            continue
        atrib = c.get("attributes") or {}
        nome = (atrib.get("PlaceName") or atrib.get("Nbrhd") or "").strip()
        if not nome:
            continue
        saida.append({
            "nome": nome,
            "lat": float(loc["y"]),
            "lon": float(loc["x"]),
            "tipo": atrib.get("Addr_type") or "neighborhood",
            "cidade": (atrib.get("City") or cidade or "").strip(),
        })
    return saida


def _photon(consulta: str, cidade: str):
    url = (
        "https://photon.komoot.io/api/?q="
        + quote(consulta)
        + "&bbox=-44.60,-20.40,-43.40,-19.40&limit=8"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=4)
    resp.raise_for_status()
    saida = []
    for feat in resp.json().get("features", []):
        props = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) != 2:
            continue
        osm_key = props.get("osm_key") or ""
        osm_val = props.get("osm_value") or ""
        tipo = "highway" if osm_key == "highway" else (osm_val or osm_key)
        nome = (props.get("name") or "").strip()
        if not nome:
            continue
        saida.append({
            "nome": nome,
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "tipo": tipo,
            "cidade": (props.get("city") or props.get("town") or cidade or "").strip(),
        })
    return saida


def _nominatim(consulta: str, cidade: str):
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={quote(consulta)}&format=jsonv2&addressdetails=1&limit=8&countrycodes=br"
        "&viewbox=-44.60,-19.40,-43.40,-20.40&bounded=1"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=4)
    resp.raise_for_status()
    saida = []
    for item in resp.json():
        categoria = item.get("category") or ""
        if categoria in ("highway", "amenity", "shop", "tourism", "building"):
            continue
        endereco = item.get("address") or {}
        nome = (
            endereco.get("suburb")
            or endereco.get("neighbourhood")
            or endereco.get("quarter")
            or item.get("name")
            or ""
        ).strip()
        if not nome:
            continue
        saida.append({
            "nome": nome,
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "tipo": item.get("type") or categoria or "suburb",
            "cidade": (
                endereco.get("city")
                or endereco.get("town")
                or endereco.get("municipality")
                or cidade
                or ""
            ).strip(),
        })
    return saida


def _consultar(consulta: str, cidade: str):
    candidatos = []
    fontes_ok = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [pool.submit(fn, consulta, cidade) for fn in (_arcgis, _photon, _nominatim)]
        for fut in futuros:
            try:
                candidatos.extend(fut.result())
                fontes_ok += 1
            except Exception:
                continue
    return candidatos, fontes_ok


def localizar_bairro(nome_bairro_limpo: str, cidade: str):
    """Retorna (status, descricao, lat, lon). status: ok, vazio ou rede."""
    nome = str(nome_bairro_limpo or "").strip()
    cidade = str(cidade or "Belo Horizonte").strip()
    if not nome:
        return "vazio", "", None, None

    consultas = [f"Bairro {nome}, {cidade}, Minas Gerais, Brasil"]
    if not remover_acentos(nome.lower()).startswith("santa "):
        consultas.append(f"Bairro Santa {nome}, {cidade}, Minas Gerais, Brasil")

    alguma_fonte = False
    for consulta in consultas:
        candidatos, fontes_ok = _consultar(consulta, cidade)
        alguma_fonte = alguma_fonte or fontes_ok > 0
        if fontes_ok == 0 and not alguma_fonte:
            continue
        escolhido = escolher_candidato_bairro(nome, candidatos)
        if escolhido:
            cidade_ok = escolhido.get("cidade") or cidade
            desc = f"Bairro {escolhido['nome']}, {cidade_ok}"
            return "ok", desc, escolhido["lat"], escolhido["lon"]

    if not alguma_fonte:
        return "rede", "", None, None
    return "vazio", "", None, None
