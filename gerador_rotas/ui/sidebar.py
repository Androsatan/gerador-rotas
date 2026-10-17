import streamlit as st

from gerador_rotas.config_io import salvar_config
from gerador_rotas.geo.partida import validar_e_geocodificar_partida


def render_sidebar(config_salva):
    with st.sidebar:
        st.header("📍 Ponto de Partida")
        ponto_partida = st.text_input(
            "Bairro, Rua+Nº ou CEP de saída:",
            value=config_salva.get("ponto_partida", "Bairro Maria Goretti, Belo Horizonte, MG"),
            help="Pode digitar apenas o bairro (ex: 'Bairro Maria Goretti' ou 'Savassi'), uma rua com número ou um CEP."
        )

        partida_ok, desc_partida_validada, lat_partida, lon_partida = validar_e_geocodificar_partida(ponto_partida)
        if partida_ok:
            st.success(f"✅ **Partida localizada:**\n{desc_partida_validada}")
        else:
            st.error(desc_partida_validada)

        st.divider()
        st.header("📦 Locais (Pacotes)")
        st.caption("Separe os produtos por vírgula e clique em Salvar abaixo.")

        local_1 = st.text_area("Local de Saída 1:", value=config_salva.get("local_1", ""), height=70)
        local_2 = st.text_area("Local de Saída 2:", value=config_salva.get("local_2", ""), height=70)
        local_3 = st.text_area("Local de Saída 3:", value=config_salva.get("local_3", ""), height=70)
        local_4 = st.text_area("Local de Saída 4:", value=config_salva.get("local_4", ""), height=70)

        if st.button("💾 Salvar Produtos/Partida", type="primary", use_container_width=True):
            salvar_config({
                "ponto_partida": ponto_partida,
                "local_1": local_1,
                "local_2": local_2,
                "local_3": local_3,
                "local_4": local_4
            })
            st.success("✅ Produtos/Partida salvos com sucesso!")

        st.divider()
        if st.button("🔒 Sair / Bloquear Acesso", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

        locais_config = {
            "Local 1": [p for p in local_1.split(",") if p.strip()],
            "Local 2": [p for p in local_2.split(",") if p.strip()],
            "Local 3": [p for p in local_3.split(",") if p.strip()],
            "Local 4": [p for p in local_4.split(",") if p.strip()],
        }
    return locais_config, partida_ok, desc_partida_validada, lat_partida, lon_partida
