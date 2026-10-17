import json

import streamlit.components.v1 as components

from gerador_rotas.dominio.constantes import CORES_ROTAS
from gerador_rotas.dominio.parser_pedidos import montar_linha_cliente
from gerador_rotas.rotas.planejador import formatar_titulo_rota


def renderizar_mapa_rotas(df_rotas, nomes_rotas, coord_partida, desc_partida, geometrias=None):
    if not coord_partida or coord_partida[0] is None or coord_partida[1] is None:
        return
    geometrias = geometrias or {}
    lat_p, lon_p = float(coord_partida[0]), float(coord_partida[1])
    marcadores_js = []
    linhas_js = []

    end_p_safe = str(desc_partida).replace("'", "").replace('"', "")
    marcadores_js.append(f"""
        L.marker([{lat_p}, {lon_p}], {{
            icon: L.divIcon({{
                className: 'custom-pin',
                html: '<div style="background:#111;color:#fff;border:2px solid #fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:15px;box-shadow:0 2px 5px rgba(0,0,0,0.5);">🏠</div>',
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            }})
        }}).addTo(map).bindPopup('<b>Ponto de Partida</b><br>{end_p_safe}');
    """)

    for r_idx, nome_r in enumerate(nomes_rotas):
        cor = CORES_ROTAS[r_idx % len(CORES_ROTAS)]
        sub = df_rotas[df_rotas["Rota"] == nome_r]
        if sub.empty:
            continue

        pts_paradas = [[lat_p, lon_p]]
        for stop_idx, (_, row) in enumerate(sub.iterrows(), start=1):
            lat, lon = row.get("Lat"), row.get("Lon")
            if lat is None or lon is None:
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                continue
            if lat_f != lat_f or lon_f != lon_f:
                continue
            pts_paradas.append([lat_f, lon_f])
            cliente_safe = montar_linha_cliente(row).replace("'", "").replace('"', "")
            end_safe = str(row.get("Endereco", "")).replace("'", "").replace('"', "")
            rota_safe = formatar_titulo_rota(nome_r).replace("'", "")

            marcadores_js.append(f"""
                L.marker([{lat_f}, {lon_f}], {{
                    icon: L.divIcon({{
                        className: 'custom-pin',
                        html: '<div style="background:{cor};color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;box-shadow:0 2px 4px rgba(0,0,0,0.4);">{stop_idx}</div>',
                        iconSize: [26, 26],
                        iconAnchor: [13, 13]
                    }})
                }}).addTo(map).bindPopup('<b>{rota_safe} - {stop_idx}ª Parada</b><br>{cliente_safe}<br><small>{end_safe}</small>');
            """)

        geom = geometrias.get(nome_r)
        pts_linha = geom if geom and len(geom) >= 2 else pts_paradas
        linhas_js.append(
            f"L.polyline({json.dumps(pts_linha)}, {{color: '{cor}', weight: 5, opacity: 0.85}}).addTo(map);"
        )

    html_mapa = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head>
    <body style="margin:0;padding:0;">
        <div id="map" style="width:100%;height:420px;border-radius:10px;"></div>
        <script>
            var map = L.map('map').setView([{lat_p}, {lon_p}], 12);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap'
            }}).addTo(map);
            {"".join(linhas_js)}
            {"".join(marcadores_js)}
            var grupo = L.featureGroup();
            map.eachLayer(function(layer) {{
                if (layer instanceof L.Marker || layer instanceof L.Polyline) {{
                    grupo.addLayer(layer);
                }}
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_mapa, height=430)
