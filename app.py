import streamlit as st

from gerador_rotas.config_io import carregar_config
from gerador_rotas.estado import iniciar_estado
from gerador_rotas.ui.auth import exigir_login
from gerador_rotas.ui.pagina_etiquetas import render_pagina_etiquetas
from gerador_rotas.ui.pagina_otimizador import render_pagina_otimizador
from gerador_rotas.ui.pagina_rotas import render_pagina_rotas
from gerador_rotas.ui.sidebar import render_sidebar
from gerador_rotas.ui.tema import aplicar_tema

st.set_page_config(page_title="Sistema de Rotas e Etiquetas", page_icon="🛵", layout="wide")
aplicar_tema()
exigir_login()
iniciar_estado()

config_salva = carregar_config()
locais_config, partida_ok, desc_partida_validada, lat_partida, lon_partida = render_sidebar(config_salva)

col_nav1, col_nav2, col_nav3 = st.columns(3)
with col_nav1:
    tipo_btn_rotas = "primary" if st.session_state["modulo_ativo"] == "rotas" else "secondary"
    if st.button("🛵 Gerador de Rotas", type=tipo_btn_rotas, use_container_width=True):
        st.session_state["modulo_ativo"] = "rotas"
        st.rerun()

with col_nav2:
    qtd_etiq_badge = len(st.session_state["df_etiquetas"])
    texto_btn_etiq = f"🏷️ Gerador de Etiquetas ({qtd_etiq_badge})" if qtd_etiq_badge > 0 else "🏷️ Gerador de Etiquetas"
    tipo_btn_etiq = "primary" if st.session_state["modulo_ativo"] == "etiquetas" else "secondary"
    if st.button(texto_btn_etiq, type=tipo_btn_etiq, use_container_width=True):
        st.session_state["modulo_ativo"] = "etiquetas"
        st.rerun()

with col_nav3:
    tipo_btn_otim = "primary" if st.session_state["modulo_ativo"] == "otimizador" else "secondary"
    if st.button("🧭 Otimizador de Rotas", type=tipo_btn_otim, use_container_width=True):
        st.session_state["modulo_ativo"] = "otimizador"
        st.rerun()

st.divider()

if st.session_state["modulo_ativo"] == "rotas":
    render_pagina_rotas(partida_ok, desc_partida_validada, lat_partida, lon_partida, locais_config)
elif st.session_state["modulo_ativo"] == "otimizador":
    render_pagina_otimizador(partida_ok, desc_partida_validada, lat_partida, lon_partida)
else:
    render_pagina_etiquetas()
