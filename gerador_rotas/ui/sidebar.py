import streamlit as st

from gerador_rotas.config_io import salvar_config
from gerador_rotas.geo.partida import validar_e_geocodificar_partida


def render_sidebar(config_salva):
    with st.sidebar:
        st.header("📍 Ponto de Partida")
        valor_salvo = str(config_salva.get("ponto_partida", "Bairro Maria Goretti, Belo Horizonte, MG"))
        chave_partida = "campo_ponto_partida"
        if chave_partida not in st.session_state:
            st.session_state[chave_partida] = valor_salvo
        partida_alterada = st.session_state[chave_partida].strip() != valor_salvo.strip()
        ajuda_partida = "Pode digitar apenas o bairro (ex: 'Bairro Maria Goretti' ou 'Savassi'), uma rua com número ou um CEP."

        if partida_alterada:
            ponto_partida = st.text_input(
                "Bairro, Rua+Nº ou CEP de saída:",
                key=chave_partida,
                help=ajuda_partida,
            )
        else:
            col_campo, col_status = st.columns([0.86, 0.14], vertical_alignment="bottom")
            with col_campo:
                ponto_partida = st.text_input(
                    "Bairro, Rua+Nº ou CEP de saída:",
                    key=chave_partida,
                    help=ajuda_partida,
                )

        partida_ok, desc_partida_validada, lat_partida, lon_partida = validar_e_geocodificar_partida(ponto_partida)
        if partida_alterada:
            if partida_ok:
                st.success(f"**Partida localizada:**\n{desc_partida_validada}")
            else:
                st.error(desc_partida_validada)
        else:
            with col_status:
                marca = "✅" if partida_ok else "❌"
                st.markdown(
                    f"<div style='text-align:center;font-size:1.35rem;line-height:2.5rem'>{marca}</div>",
                    unsafe_allow_html=True,
                )

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
