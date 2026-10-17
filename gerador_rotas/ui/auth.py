import streamlit as st


def exigir_login():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if not st.session_state["autenticado"]:
        st.title("🔒 Acesso Restrito - Rotas & Etiquetas")
        st.markdown("Digite a senha de acesso para entrar no sistema.")

        with st.form("form_login"):
            senha_digitada = st.text_input("Senha:", type="password", placeholder="Digite a senha...")
            btn_entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if btn_entrar:
                if senha_digitada.strip() == "2k12345":
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta. Tente novamente.")

        st.stop()
