import re
from urllib.parse import quote

import requests
import streamlit as st

from gerador_rotas.dominio.endereco_texto import (
    dentro_perimetro_rmbh,
    eh_regional_bh,
    formatar_via_com_prefixo,
)
from gerador_rotas.dominio.similaridade import similaridade_ruas
from gerador_rotas.geo.bairro import localizar_bairro


@st.cache_data(ttl=86400, show_spinner=False)
def _bairro_cacheado(nome_bairro_limpo: str, cidade: str):
    status, desc, lat, lon = localizar_bairro(nome_bairro_limpo, cidade)
    if status == "rede":
        raise ConnectionError("rede")
    if status != "ok":
        return False, "❌ Bairro não localizado em BH/Região. Confira a grafia ou digite uma rua/CEP.", None, None
    return True, desc, lat, lon


def buscar_coordenada_bairro(nome_bairro_limpo: str, cidade: str):
    try:
        return _bairro_cacheado(nome_bairro_limpo, cidade)
    except ConnectionError:
        return False, "❌ Não foi possível consultar o mapa agora. Tente de novo em instantes.", None, None


@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar_endereco_rua(endereco_completo_texto: str):
    headers = {"User-Agent": "GeradorRotasRMBH/3.0"}
    try:
        q_geo = f"{endereco_completo_texto}, Minas Gerais, Brasil"
        url_arcgis = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_geo)}&searchExtent=-44.50,-20.30,-43.50,-19.50&maxLocations=1&f=json"
        )
        resp = requests.get(url_arcgis, headers=headers, timeout=3.5)
        if resp.status_code == 200:
            cands = resp.json().get("candidates", [])
            if cands:
                lat = float(cands[0]["location"]["y"])
                lon = float(cands[0]["location"]["x"])
                if dentro_perimetro_rmbh(lat, lon):
                    return lat, lon
    except Exception:
        pass

    try:
        url_ph = f"https://photon.komoot.io/api/?q={quote(endereco_completo_texto + ' MG')}&bbox=-44.60,-20.40,-43.40,-19.40&limit=1"
        resp_p = requests.get(url_ph, headers=headers, timeout=3.5)
        if resp_p.status_code == 200:
            feats = resp_p.json().get("features", [])
            if feats:
                coords = feats[0].get("geometry", {}).get("coordinates", [])
                if len(coords) == 2 and dentro_perimetro_rmbh(float(coords[1]), float(coords[0])):
                    return float(coords[1]), float(coords[0])
    except Exception:
        pass

    return None, None

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_candidatos_multifonte(rua: str, numero: str, bairro_dica: str, cidade: str):
    headers = {"User-Agent": "GeradorRotasRMBH/3.0 (contato@geradorrotas.app)"}
    candidatos = []
    rua_Com_pref = formatar_via_com_prefixo(rua, rua)

    try:
        q_arc = f"{rua_Com_pref}, {numero}, {bairro_dica}, {cidade}, Minas Gerais, Brasil".replace(", ,", ",")
        url_arc = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            f"?SingleLine={quote(q_arc)}&searchExtent=-44.50,-20.30,-43.50,-19.50"
            f"&outFields=StPreType,StName,StType,AddNum,Nbrhd,District,City,Postal,Match_addr&maxLocations=10&f=json"
        )
        r_arc = requests.get(url_arc, headers=headers, timeout=3.0)
        if r_arc.status_code == 200:
            for c in r_arc.json().get("candidates", []):
                if c.get("score", 0) < 72:
                    continue
                lat_c = float(c["location"]["y"])
                lon_c = float(c["location"]["x"])
                if not dentro_perimetro_rmbh(lat_c, lon_c):
                    continue
                at = c.get("attributes", {})
                pre = at.get("StPreType", "").strip()
                nm = at.get("StName", "").strip()
                suf = at.get("StType", "").strip()
                partes_v = [p for p in (pre, nm, suf) if p]
                via_arc = " ".join(partes_v).strip()
                if not via_arc:
                    continue
                if similaridade_ruas(rua, via_arc) < 0.68:
                    continue

                via_arc = formatar_via_com_prefixo(via_arc, rua)
                nbr = (at.get("Nbrhd") or "").strip()
                dist = (at.get("District") or "").strip()
                bairro_c = nbr if (nbr and not eh_regional_bh(nbr)) else (dist if not eh_regional_bh(dist) else "")
                cid_c = (at.get("City") or cidade).strip()
                cep_raw = re.sub(r"\D", "", str(at.get("Postal", "")))
                cep_c = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""

                candidatos.append({
                    "logradouro": via_arc,
                    "bairro": bairro_c,
                    "cidade": cid_c,
                    "cep": cep_c,
                    "lat": lat_c,
                    "lon": lon_c,
                    "fonte": "arcgis"
                })
    except Exception:
        pass

    try:
        q_ph = f"{rua_Com_pref} {numero} {bairro_dica} {cidade} MG".strip()
        url_ph = f"https://photon.komoot.io/api/?q={quote(q_ph)}&bbox=-44.60,-20.40,-43.40,-19.40&limit=10"
        r_ph = requests.get(url_ph, headers=headers, timeout=3.0)
        if r_ph.status_code == 200:
            for feat in r_ph.json().get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [])
                rua_ph = props.get("street") or props.get("name") or ""
                if len(coords) == 2 and rua_ph and similaridade_ruas(rua, rua_ph) >= 0.68:
                    lon_p, lat_p = float(coords[0]), float(coords[1])
                    if not dentro_perimetro_rmbh(lat_p, lon_p):
                        continue
                    b_ph = props.get("suburb") or props.get("district") or props.get("locality") or ""
                    if eh_regional_bh(b_ph):
                        b_ph = ""
                    cid_ph = props.get("city") or props.get("town") or cidade
                    cep_raw = re.sub(r"\D", "", str(props.get("postcode", "")))
                    cep_ph = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""
                    candidatos.append({
                        "logradouro": formatar_via_com_prefixo(rua_ph, rua),
                        "bairro": b_ph,
                        "cidade": cid_ph,
                        "cep": cep_ph,
                        "lat": lat_p,
                        "lon": lon_p,
                        "fonte": "photon"
                    })
    except Exception:
        pass

    precisa_nominatim = (not bairro_dica) or all(not c.get("bairro") for c in candidatos)
    if precisa_nominatim:
        try:
            q_nom = f"{rua_Com_pref}, {cidade}, Minas Gerais, Brasil"
            url_nom = (
                f"https://nominatim.openstreetmap.org/search"
                f"?q={quote(q_nom)}&format=jsonv2&addressdetails=1&limit=10&countrycodes=br&viewbox=-44.60,-19.40,-43.40,-20.40&bounded=0"
            )
            r_nom = requests.get(url_nom, headers=headers, timeout=3.0)
            if r_nom.status_code == 200:
                for item in r_nom.json():
                    lat_n, lon_n = float(item["lat"]), float(item["lon"])
                    if not dentro_perimetro_rmbh(lat_n, lon_n):
                        continue
                    ed = item.get("address", {})
                    via_n = ed.get("road") or item.get("name") or ""
                    if not via_n or similaridade_ruas(rua, via_n) < 0.68:
                        continue
                    b_n = ed.get("suburb") or ed.get("neighbourhood") or ed.get("quarter") or ""
                    if eh_regional_bh(b_n):
                        b_n = ""
                    cid_n = ed.get("city") or ed.get("town") or ed.get("municipality") or cidade
                    cep_raw = re.sub(r"\D", "", str(ed.get("postcode", "")))
                    cep_n = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else ""
                    candidatos.append({
                        "logradouro": formatar_via_com_prefixo(via_n, rua),
                        "bairro": b_n,
                        "cidade": cid_n,
                        "cep": cep_n,
                        "lat": lat_n,
                        "lon": lon_n,
                        "fonte": "nominatim"
                    })
        except Exception:
            pass

    return candidatos
