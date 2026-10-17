import json
import os

import pandas as pd
import streamlit as st

from gerador_rotas.dominio.parser_pedidos import resolver_enderecos_em_paralelo
from gerador_rotas.estado import atualizar_base_etiquetas
from gerador_rotas.etiquetas.parser import (
    endereco_de_etiqueta_resolvido,
    endereco_etiqueta_precisa_busca,
    extrair_etiquetas_de_texto_rota,
    formatar_endereco_para_etiqueta,
    importar_etiquetas_das_rotas_calculadas,
    limpar_nome_para_etiqueta,
)
from gerador_rotas.geo.resolver_endereco import buscar_endereco_completo
from gerador_rotas.etiquetas.pdf import (
    gerar_pdf_etiquetas_10x15,
    localizar_modelo_pdf_no_repositorio,
)


def _opcoes_bairro(opcoes) -> list:
    if not isinstance(opcoes, list) or len(opcoes) < 2:
        return []
    return [str(op).strip() for op in opcoes if str(op).strip()]


def _completar_enderecos_das_etiquetas(df):
    if df.empty or "Endereco Original" not in df.columns:
        return df
    if "Opcoes_Endereco" not in df.columns:
        df["Opcoes_Endereco"] = "[]"
    pendentes = [
        str(end).strip()
        for end in df["Endereco Original"]
        if endereco_etiqueta_precisa_busca(end)
    ]
    if not pendentes:
        return df
    mapa = resolver_enderecos_em_paralelo(pendentes)
    for idx, row in df.iterrows():
        bruto = str(row["Endereco Original"]).strip()
        if bruto not in mapa:
            continue
        end_form, status, _, _, opcoes = mapa[bruto]
        df.at[idx, "Endereco Etiqueta"] = endereco_de_etiqueta_resolvido(bruto, end_form, status)
        if str(end_form or "").strip() and not str(status).startswith("❌"):
            df.at[idx, "Endereco Original"] = end_form
        df.at[idx, "Opcoes_Endereco"] = json.dumps(_opcoes_bairro(opcoes), ensure_ascii=False)
    return df


def render_pagina_etiquetas():
    st.title("🏷️ Gerador de Etiquetas (10x15 cm)")

    caminho_modelo_repo = localizar_modelo_pdf_no_repositorio()
    arquivo_modelo_upload = None

    if caminho_modelo_repo:
        st.success(f"✅ Modelo de etiqueta carregado automaticamente do repositório (`{os.path.basename(caminho_modelo_repo)}`).")
    else:
        st.warning("⚠️ O arquivo `Etiqueta.pdf` não foi encontrado na pasta do GitHub. Faça o upload dele abaixo ou adicione `Etiqueta.pdf` ao repositório.")
        arquivo_modelo_upload = st.file_uploader("Subir modelo Etiqueta.pdf", type="pdf")

    if not st.session_state["df_rotas_calculadas"].empty:
        df_rotas_disp = st.session_state.get("df_rotas_editadas", st.session_state["df_rotas_calculadas"])
        if st.button(f"📥 Puxar Automaticamente as {len(df_rotas_disp)} Entregas das Rotas Calculadas", use_container_width=True):
            df_imp = importar_etiquetas_das_rotas_calculadas(df_rotas_disp)
            atualizar_base_etiquetas(df_imp)
            st.rerun()

    # --- 1) COLAR LISTA DE NOMES E ENDEREÇOS ---
    st.subheader("1️⃣ Colar Lista de Nomes e Endereços")
    texto_lista_etiquetas = st.text_area(
        "Cole abaixo a lista de entregas (no mesmo formato gerado pelo Gerador de Rotas):",
        height=200,
        key=f"texto_etiquetas_{st.session_state['contador_form_etiquetas']}",
        placeholder=(
            "ROTA FP\n\n"
            "Rua Marrocos, 47, Vila Jardim Leblon, Belo Horizonte, 31575-230\n"
            "AXEL [2T] (2PCT)\n\n"
            "Rua São Vicente, 250, Granja Werneck, Belo Horizonte, 31840-410\n"
            "JOÃO SILVA [VG]"
        )
    )

    if st.button("➕ Extrair e Adicionar Etiquetas da Lista", type="primary", use_container_width=True):
        if texto_lista_etiquetas.strip():
            with st.spinner("Localizando endereços completos..."):
                df_novas_etiq = _completar_enderecos_das_etiquetas(
                    extrair_etiquetas_de_texto_rota(texto_lista_etiquetas)
                )
            if not df_novas_etiq.empty:
                df_atual_etiq = st.session_state.get("df_etiquetas_editadas", st.session_state["df_etiquetas"])
                if df_atual_etiq.empty:
                    df_comb = df_novas_etiq
                else:
                    df_comb = pd.concat([df_atual_etiq, df_novas_etiq], ignore_index=True)
                atualizar_base_etiquetas(df_comb)
                st.session_state["contador_form_etiquetas"] += 1
                st.rerun()
            else:
                st.warning("⚠️ Não foi possível identificar pares de endereço e cliente no texto colado.")
        else:
            st.warning("Cole a lista de entregas antes de clicar no botão.")

    with st.expander("➕ Adicionar um Cliente Individualmente"):
        col_m1, col_m2, col_m3 = st.columns([2, 3, 1])
        with col_m1:
            m_nome = st.text_input("Nome do Cliente (ex: AXEL [2T] (2PCT)):")
        with col_m2:
            m_end = st.text_input("Endereço Completo (ex: Rua Marrocos, 47, Vila Jardim Leblon, Belo Horizonte, 31575-230):")
        with col_m3:
            m_rota = st.text_input("Rota:", value="AVULSO")

        if st.button("Adicionar Cliente Avulso", use_container_width=True):
            if m_nome.strip() and m_end.strip():
                with st.spinner("Localizando endereço completo..."):
                    end_form, status, _, _, opcoes = buscar_endereco_completo(m_end.strip())
                endereco_final = endereco_de_etiqueta_resolvido(m_end, end_form, status)
                if str(status).startswith("❌"):
                    st.toast("Não foi possível completar esse endereço. Ele entrou como foi digitado.")
                df_atual_etiq = st.session_state.get("df_etiquetas_editadas", st.session_state["df_etiquetas"])
                nova_linha = pd.DataFrame([{
                    "Imprimir": True,
                    "Rota": m_rota.strip().upper() or "AVULSO",
                    "Ordem": f"{len(df_atual_etiq) + 1}º",
                    "Nome Etiqueta": limpar_nome_para_etiqueta(m_nome),
                    "Endereco Etiqueta": endereco_final,
                    "Nome Original": m_nome.strip().upper(),
                    "Endereco Original": end_form.strip() if end_form and not str(status).startswith("❌") else m_end.strip(),
                    "Opcoes_Endereco": json.dumps(_opcoes_bairro(opcoes), ensure_ascii=False),
                }])
                df_comb = pd.concat([df_atual_etiq, nova_linha], ignore_index=True) if not df_atual_etiq.empty else nova_linha
                atualizar_base_etiquetas(df_comb)
                st.rerun()
            else:
                st.warning("Preencha o Nome e o Endereço.")

    # --- 2) SELEÇÃO, EDIÇÃO E DOWNLOAD DO PDF 10x15 ---
    if not st.session_state["df_etiquetas"].empty:
        st.divider()
        st.subheader("2️⃣ Selecionar e Baixar Etiquetas em PDF Único (10x15 cm)")

        @st.fragment
        def render_tabela_etiquetas():
            df_base_e = st.session_state["df_etiquetas"]
            if "Imprimir" not in df_base_e.columns:
                df_base_e.insert(0, "Imprimir", True)
            if "Opcoes_Endereco" not in df_base_e.columns:
                df_base_e["Opcoes_Endereco"] = "[]"

            linhas_ambiguas = []
            for idx_amb, row_amb in df_base_e.iterrows():
                try:
                    opcoes_lista = json.loads(row_amb.get("Opcoes_Endereco", "[]") or "[]")
                except Exception:
                    opcoes_lista = []
                if len(opcoes_lista) > 1:
                    linhas_ambiguas.append((idx_amb, row_amb.get("Nome Etiqueta") or row_amb.get("Nome Original"), opcoes_lista))

            if linhas_ambiguas:
                st.warning(
                    f"🏘️ **Atenção: {len(linhas_ambiguas)} etiqueta(s) possuem rua que existe em mais de um bairro!** "
                    "Escolha abaixo qual é o bairro correto:"
                )
                for idx_amb, nome_cli_amb, opcoes_lista in linhas_ambiguas:
                    col_sel, col_btn_amb = st.columns([3, 1])
                    with col_sel:
                        escolha_end = st.selectbox(
                            f"Escolha o bairro/endereço correto para **{nome_cli_amb}**:",
                            options=opcoes_lista,
                            key=f"sel_amb_etiq_{idx_amb}",
                        )
                    with col_btn_amb:
                        st.write("")
                        if st.button(f"✅ Confirmar ({nome_cli_amb})", key=f"btn_amb_etiq_{idx_amb}", use_container_width=True):
                            df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                            df_sync.at[idx_amb, "Endereco Etiqueta"] = formatar_endereco_para_etiqueta(escolha_end)
                            df_sync.at[idx_amb, "Endereco Original"] = escolha_end
                            df_sync.at[idx_amb, "Opcoes_Endereco"] = "[]"
                            atualizar_base_etiquetas(df_sync)
                            st.rerun()

            rotas_presentes = sorted(list(df_base_e["Rota"].dropna().unique()))

            c_sel1, c_sel2, c_sel3, c_sel4 = st.columns(4)
            with c_sel1:
                if st.button("☑️ Marcar Todas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_sync["Imprimir"] = True
                    atualizar_base_etiquetas(df_sync)
                    st.rerun()
            with c_sel2:
                if st.button("🔲 Desmarcar Todas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_sync["Imprimir"] = False
                    atualizar_base_etiquetas(df_sync)
                    st.rerun()
            with c_sel3:
                if st.button("🗑️ Excluir Desmarcadas", use_container_width=True):
                    df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                    df_rest = df_sync[df_sync["Imprimir"]].copy()
                    atualizar_base_etiquetas(df_rest)
                    st.rerun()
            with c_sel4:
                if st.button("🧹 Limpar Lista de Etiquetas", use_container_width=True):
                    atualizar_base_etiquetas(pd.DataFrame())
                    st.rerun()

            if len(rotas_presentes) > 1:
                st.caption("Filtrar seleção rápida por Rota:")
                cols_f = st.columns(len(rotas_presentes))
                for idx_f, r_nome in enumerate(rotas_presentes):
                    with cols_f[idx_f]:
                        if st.button(f"🎯 Só {r_nome}", key=f"btn_filtro_etiq_{idx_f}", use_container_width=True):
                            df_sync = st.session_state.get("df_etiquetas_editadas", df_base_e).copy()
                            df_sync["Imprimir"] = df_sync["Rota"] == r_nome
                            atualizar_base_etiquetas(df_sync)
                            st.rerun()

            df_etiq_edit = st.data_editor(
                df_base_e,
                use_container_width=True,
                hide_index=True,
                column_order=["Imprimir", "Rota", "Ordem", "Nome Etiqueta", "Endereco Etiqueta"],
                column_config={
                    "Imprimir": st.column_config.CheckboxColumn("🖨️ Imprimir", width="small", default=True),
                    "Rota": st.column_config.TextColumn("Rota", width="small"),
                    "Ordem": st.column_config.TextColumn("Ordem", width="small"),
                    "Nome Etiqueta": st.column_config.TextColumn("Destinatário na Etiqueta (Editável)", width="medium"),
                    "Endereco Etiqueta": st.column_config.TextColumn("Endereço na Etiqueta (Editável)", width="large"),
                },
                key=f"editor_tabela_etiquetas_{st.session_state['versao_editor_etiquetas']}"
            )

            df_etiq_edit["Nome Etiqueta"] = df_etiq_edit["Nome Etiqueta"].astype(str).str.upper()
            for coluna_oculta in ("Opcoes_Endereco", "Endereco Original", "Nome Original"):
                if coluna_oculta not in df_etiq_edit.columns and coluna_oculta in df_base_e.columns:
                    df_etiq_edit[coluna_oculta] = df_base_e[coluna_oculta].values
            st.session_state["df_etiquetas_editadas"] = df_etiq_edit

            df_selecionadas = df_etiq_edit[df_etiq_edit["Imprimir"]].copy()
            qtd_selecionadas = len(df_selecionadas)

            st.markdown(f"**Etiquetas selecionadas para o PDF:** `{qtd_selecionadas}` de `{len(df_etiq_edit)}`")

            fonte_pdf = caminho_modelo_repo if caminho_modelo_repo else arquivo_modelo_upload

            if not fonte_pdf:
                st.error("⚠️ Adicione o arquivo `Etiqueta.pdf` no seu repositório GitHub ou faça upload acima para liberar o download.")
            elif qtd_selecionadas == 0:
                st.warning("⚠️ Marque pelo menos uma etiqueta na coluna '🖨️ Imprimir' para gerar o PDF.")
            else:
                pdf_bytes = gerar_pdf_etiquetas_10x15(df_selecionadas, fonte_pdf)
                st.download_button(
                    label=f"📥 BAIXAR PDF ÚNICO 10x15 ({qtd_selecionadas} ETIQUETAS SELECIONADAS)",
                    data=pdf_bytes,
                    file_name="etiquetas_10x15.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

        render_tabela_etiquetas()
