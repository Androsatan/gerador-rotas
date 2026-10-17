import json

import pandas as pd
import streamlit as st

from gerador_rotas.dominio.parser_pedidos import (
    extrair_pedidos_brutos,
    montar_linha_cliente,
    resolver_enderecos_em_paralelo,
)
from gerador_rotas.estado import (
    adicionar_pedidos_na_sessao,
    atualizar_base_etiquetas,
    atualizar_base_pedidos,
)
from gerador_rotas.etiquetas.parser import importar_etiquetas_das_rotas_calculadas
from gerador_rotas.geo.geocodificadores import geocodificar_endereco_rua
from gerador_rotas.geo.resolver_endereco import buscar_endereco_completo
from gerador_rotas.rotas.planejador import (
    formatar_titulo_rota,
    gerar_rotas,
    recalcular_todas_as_rotas,
)
from gerador_rotas.ui.mapa import renderizar_mapa_rotas


def render_pagina_rotas(partida_ok, desc_partida_validada, lat_partida, lon_partida, locais_config):
    st.title("🛵 Gerador de Rotas")

    if (
        partida_ok
        and not st.session_state["df_rotas_calculadas"].empty
        and st.session_state["coord_partida_atual"] != (lat_partida, lon_partida)
    ):
        df_reotim, novo_km, nova_coord, novas_geom, novos_avisos = recalcular_todas_as_rotas(
            st.session_state.get("df_rotas_editadas", st.session_state["df_rotas_calculadas"]),
            st.session_state["nomes_rotas_ativas"],
            lat_partida,
            lon_partida,
        )
        st.session_state["df_rotas_calculadas"] = df_reotim
        st.session_state["df_rotas_editadas"] = df_reotim.copy()
        st.session_state["versao_editor_rotas"] += 1
        st.session_state["resumo_km_rotas"] = novo_km
        st.session_state["coord_partida_atual"] = nova_coord
        st.session_state["geometrias_rotas"] = novas_geom
        st.session_state["avisos_rotas"] = novos_avisos

    # --- PASSO 1: ADICIONAR PEDIDOS ---
    st.subheader("1️⃣ Adicionar Pedidos")

    texto_pedidos = st.text_area(
        "Cole os pedidos abaixo:",
        height=200,
        key=f"texto_pedidos_{st.session_state['contador_form']}",
        placeholder=(
            "Exemplo:\n[14/10/2026 13:53]: Fulano\n25g castanha\nRua São Vicente 250\n\n"
        )
    )
    vendedor_lote = st.text_input(
        "Sigla do Vendedor `[ ]` para os pedidos acima:",
        key=f"vendedor_lote_{st.session_state['contador_form']}",
        placeholder="Ex: 2T, VG, NK"
    )

    if st.button("🔍 Adicionar à Lista", type="primary", use_container_width=True):
        if texto_pedidos.strip():
            with st.spinner("Extraindo pedidos, filtrando mensagens e buscando CEPs..."):
                df_extraidos = extrair_pedidos_brutos(texto_pedidos, locais_config, vendedor_lote)
                if not df_extraidos.empty:
                    qtd_add, lista_dups = adicionar_pedidos_na_sessao(df_extraidos)
                    st.session_state["avisos_duplicados"] = lista_dups
                    st.session_state["contador_form"] += 1
                    st.rerun()
                else:
                    st.warning("⚠️ Não foi possível identificar um endereço válido no texto colado.")
        else:
            st.warning("Cole pelo menos um pedido antes de clicar em adicionar.")

    if st.session_state.get("avisos_duplicados"):
        dups_str = "\n".join([f"- **{d}**" for d in st.session_state["avisos_duplicados"]])
        st.warning(
            f"🚫 **{len(st.session_state['avisos_duplicados'])} pedido(s) com mesmo Nome e Endereço já estavam na lista e não foram inseridos duas vezes:**\n{dups_str}"
        )
        if st.button("✖️ Fechar aviso de duplicados"):
            st.session_state["avisos_duplicados"] = []
            st.rerun()

    # --- PASSO 2: TABELA DE CONFERÊNCIA, EDIÇÃO E EXCLUSÃO ---
    if not st.session_state["df_pedidos"].empty:
        st.divider()
        total_pedidos = len(st.session_state["df_pedidos"])
        st.subheader(f"2️⃣ Conferência dos Pedidos ({total_pedidos} na lista)")

        @st.fragment
        def render_passo_2():
            df_base = st.session_state["df_pedidos"]
            if "Excluir" not in df_base.columns:
                df_base.insert(0, "Excluir", False)
            if "Opcoes_Endereco" not in df_base.columns:
                df_base["Opcoes_Endereco"] = "[]"

            linhas_ambiguas = []
            for idx_amb, row_amb in df_base.iterrows():
                try:
                    opcoes_lista = json.loads(row_amb.get("Opcoes_Endereco", "[]") or "[]")
                except Exception:
                    opcoes_lista = []
                if len(opcoes_lista) > 1:
                    linhas_ambiguas.append((idx_amb, row_amb["Cliente"], opcoes_lista))

            if linhas_ambiguas:
                st.warning(
                    f"🏘️ **Atenção: {len(linhas_ambiguas)} pedido(s) possuem rua que existe em mais de um bairro!** "
                    "Escolha abaixo qual é o bairro correto de cada cliente:"
                )
                for idx_amb, nome_cli_amb, opcoes_lista in linhas_ambiguas:
                    col_sel, col_btn_amb = st.columns([3, 1])
                    with col_sel:
                        escolha_end = st.selectbox(
                            f"Escolha o bairro/endereço correto para **{nome_cli_amb}**:",
                            options=opcoes_lista,
                            key=f"sel_amb_{idx_amb}"
                        )
                    with col_btn_amb:
                        st.write("")
                        if st.button(f"✅ Confirmar ({nome_cli_amb})", key=f"btn_amb_{idx_amb}", use_container_width=True):
                            df_sync = st.session_state.get("df_pedidos_editados", df_base).copy()
                            lat_novo, lon_novo = geocodificar_endereco_rua(escolha_end)
                            df_sync.at[idx_amb, "Endereco"] = escolha_end
                            if lat_novo is None or lon_novo is None:
                                df_sync.at[idx_amb, "Status"] = "⚠️ ENDEREÇO ESCOLHIDO SEM COORDENADA"
                                df_sync.at[idx_amb, "Lat"] = None
                                df_sync.at[idx_amb, "Lon"] = None
                            else:
                                df_sync.at[idx_amb, "Status"] = "✅ OK"
                                df_sync.at[idx_amb, "Lat"] = lat_novo
                                df_sync.at[idx_amb, "Lon"] = lon_novo
                            df_sync.at[idx_amb, "Opcoes_Endereco"] = "[]"
                            atualizar_base_pedidos(df_sync)
                            st.rerun()

            problemas = df_base[df_base["Status"] != "✅ OK"]
            if not problemas.empty:
                st.warning(
                    f"⚠️ **{len(problemas)} endereço(s) precisam da sua atenção!** "
                    "Escolha o bairro acima ou corrija o endereço na tabela abaixo e clique em '🔍 Buscar CEP após Editar Tabela'."
                )
            else:
                st.success(f"✅ Todos os {len(df_base)} endereços foram localizados com Bairro e CEP!")

            df_editado = st.data_editor(
                df_base,
                use_container_width=True,
                hide_index=True,
                column_order=["Excluir", "Status", "Cliente", "Vendedor", "Pacotes", "Observacao", "Posicao", "Endereco", "Itens_Lidos"],
                column_config={
                    "Excluir": st.column_config.CheckboxColumn("🗑️", width="small", default=False),
                    "Status": st.column_config.TextColumn("Status", disabled=True, width="medium"),
                    "Cliente": st.column_config.TextColumn("Cliente (CAIXA ALTA)", width="medium"),
                    "Vendedor": st.column_config.TextColumn("Vendedor [ ]", width="small"),
                    "Pacotes": st.column_config.NumberColumn("Pacotes", min_value=1, max_value=10, step=1, width="small"),
                    "Observacao": st.column_config.TextColumn("Obs ( )", width="small"),
                    "Posicao": st.column_config.SelectboxColumn(
                        "Posição",
                        options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                        default="Normal",
                        width="small"
                    ),
                    "Endereco": st.column_config.TextColumn("Endereço Completo (Editável)", width="large"),
                    "Itens_Lidos": st.column_config.TextColumn("Itens e Locais Identificados", disabled=True, width="medium"),
                },
                key=f"editor_tabela_pedidos_{st.session_state['versao_editor_pedidos']}"
            )

            df_editado["Cliente"] = df_editado["Cliente"].astype(str).str.upper()
            st.session_state["df_pedidos_editados"] = df_editado

            col_acao1, col_acao2, col_acao3 = st.columns(3)

            with col_acao1:
                if st.button(
                    "🔍 Buscar CEP após Editar Tabela",
                    use_container_width=True,
                    help="Rebusca rapidamente apenas os endereços que você editou ou que estavam com aviso."
                ):
                    with st.spinner("Atualizando endereços editados/pendentes em paralelo..."):
                        df_atualizados = df_editado.copy()
                        indices_para_buscar = []
                        enderecos_para_buscar = []

                        for idx, row in df_atualizados.iterrows():
                            end_antigo = str(df_base.at[idx, "Endereco"]) if idx in df_base.index else ""
                            end_atual = str(row["Endereco"])
                            status_atual = str(row["Status"])
                            if end_atual != end_antigo or status_atual != "✅ OK":
                                indices_para_buscar.append(idx)
                                enderecos_para_buscar.append(end_atual)

                        if enderecos_para_buscar:
                            mapa_novos = resolver_enderecos_em_paralelo(enderecos_para_buscar)
                            for idx in indices_para_buscar:
                                end_atual = str(df_atualizados.at[idx, "Endereco"])
                                end_novo, novo_status, lat, lon, novas_opcoes = mapa_novos.get(
                                    end_atual,
                                    buscar_endereco_completo(end_atual)
                                )
                                df_atualizados.at[idx, "Endereco"] = end_novo
                                df_atualizados.at[idx, "Status"] = novo_status
                                df_atualizados.at[idx, "Lat"] = lat
                                df_atualizados.at[idx, "Lon"] = lon
                                df_atualizados.at[idx, "Opcoes_Endereco"] = json.dumps(novas_opcoes, ensure_ascii=False)

                        atualizar_base_pedidos(df_atualizados)
                        st.rerun()

            with col_acao2:
                qtd_marcados = int(df_editado["Excluir"].sum()) if "Excluir" in df_editado.columns else 0
                texto_btn_excluir = f"🗑️ Excluir Selecionados ({qtd_marcados})" if qtd_marcados > 0 else "🗑️ Excluir Selecionados"
                if st.button(texto_btn_excluir, use_container_width=True):
                    if qtd_marcados > 0:
                        df_restante = df_editado[~df_editado["Excluir"]].copy()
                        df_restante["Excluir"] = False
                        atualizar_base_pedidos(df_restante)
                        st.session_state["df_rotas_calculadas"] = pd.DataFrame()
                        st.session_state["df_rotas_editadas"] = pd.DataFrame()
                        st.rerun()
                    else:
                        st.toast("Marque a caixinha '🗑️' na tabela ao lado do cliente que deseja remover.")

            with col_acao3:
                if st.button("🧹 Limpar Lista", use_container_width=True):
                    atualizar_base_pedidos(pd.DataFrame())
                    st.session_state["df_rotas_calculadas"] = pd.DataFrame()
                    st.session_state["df_rotas_editadas"] = pd.DataFrame()
                    st.session_state["avisos_duplicados"] = []
                    st.rerun()

            with st.expander("👀 Ver prévia dos pedidos (Nomes e Endereços)", expanded=True):
                linhas_previa = []
                for _, row in df_editado.iterrows():
                    linhas_previa.append(f"{row['Endereco']}\n{montar_linha_cliente(row)}")
                st.code("\n\n".join(linhas_previa), language="text", wrap_lines=True)

        render_passo_2()

        # --- PASSO 3: DIVISÃO E CÁLCULO DAS ROTAS ---
        st.divider()
        st.subheader("3️⃣ Dividir e Calcular Melhores Rotas")

        df_para_calculo = st.session_state.get("df_pedidos_editados", st.session_state["df_pedidos"])
        total_pedidos_atual = len(df_para_calculo)

        qtd_rotas = st.radio(
            "Em quantas rotas deseja dividir os pedidos?",
            options=[1, 2, 3, 4],
            index=1 if total_pedidos_atual >= 2 else 0,
            horizontal=True
        )

        base_por_rota = total_pedidos_atual // qtd_rotas
        sobra = total_pedidos_atual % qtd_rotas
        sugestoes_padrao = [base_por_rota + (1 if i < sobra else 0) for i in range(qtd_rotas)]
        nomes_sugeridos = ["ROTA FP", "ROTA LE", "ROTA 3", "ROTA 4"]

        cols_rotas = st.columns(qtd_rotas)
        nomes_escolhidos = []
        cotas_escolhidas = []

        for i in range(qtd_rotas):
            with cols_rotas[i]:
                nome_r = st.text_input(
                    f"Nome da Rota {i + 1}:",
                    value=nomes_sugeridos[i],
                    key=f"nome_rota_{i}_{qtd_rotas}"
                )
                cota_r = st.number_input(
                    f"Nº de Pedidos ({nome_r}):",
                    min_value=0,
                    max_value=total_pedidos_atual,
                    value=sugestoes_padrao[i],
                    step=1,
                    key=f"cota_rota_{i}_{qtd_rotas}_{total_pedidos_atual}"
                )
                nomes_escolhidos.append(formatar_titulo_rota(nome_r))
                cotas_escolhidas.append(int(cota_r))

        soma_cotas = sum(cotas_escolhidas)
        if soma_cotas != total_pedidos_atual:
            diferenca = total_pedidos_atual - soma_cotas
            if diferenca > 0:
                st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você tem **{total_pedidos_atual}** na lista (faltam distribuir **{diferenca}**).")
            else:
                st.warning(f"⚠️ A soma das rotas está em **{soma_cotas}** pedidos, mas você só tem **{total_pedidos_atual}** na lista (passou **{abs(diferenca)}**).")

        if not partida_ok:
            st.error("⚠️ Corrija o Ponto de Partida na barra lateral esquerda antes de gerar as rotas.")

        if st.button(
            "🚀 Gerar e Otimizar Rotas",
            type="primary",
            use_container_width=True,
            disabled=(soma_cotas != total_pedidos_atual or not partida_ok)
        ):
            with st.spinner("Agrupando regiões e calculando a melhor sequência rua a rua..."):
                df_mais_recente = st.session_state.get("df_pedidos_editados", st.session_state["df_pedidos"]).copy().reset_index(drop=True)
                atualizar_base_pedidos(df_mais_recente)

                nomes_unicos = []
                for idx_n, nm in enumerate(nomes_escolhidos):
                    if nm in nomes_unicos:
                        nm = f"{nm} ({idx_n + 1})"
                    nomes_unicos.append(nm)

                df_otimizado, resumo_km, coord_p, geometrias, avisos = gerar_rotas(
                    df_mais_recente,
                    nomes_unicos,
                    cotas_escolhidas,
                    lat_partida,
                    lon_partida,
                )

                st.session_state["df_rotas_calculadas"] = df_otimizado
                st.session_state["df_rotas_editadas"] = df_otimizado.copy()
                st.session_state["versao_editor_rotas"] += 1
                st.session_state["nomes_rotas_ativas"] = nomes_unicos
                st.session_state["resumo_km_rotas"] = resumo_km
                st.session_state["coord_partida_atual"] = coord_p
                st.session_state["geometrias_rotas"] = geometrias
                st.session_state["avisos_rotas"] = avisos
                st.rerun()

    # --- PASSO 4: ROTAS PRONTAS, TROCA ENTRE ROTAS E BOTÃO DE ETIQUETAS ---
    if not st.session_state["df_rotas_calculadas"].empty:
        st.divider()
        st.subheader("4️⃣ Rotas Otimizadas e Ajuste Entre Rotas")

        @st.fragment
        def render_passo_4():
            df_rotas_base = st.session_state["df_rotas_calculadas"]
            nomes_ativas = st.session_state["nomes_rotas_ativas"]
            resumo_km = st.session_state["resumo_km_rotas"]

            st.caption(
                "💡 **Quer passar um pedido de uma rota para outra ou mudar quem é o PRIMEIRO/ÚLTIMO?** "
                "Basta alterar a coluna **'Rota'** ou **'Posição'** na tabela abaixo que o sistema recalcula a melhor ordem das rotas automaticamente!"
            )

            df_rotas_edit = st.data_editor(
                df_rotas_base,
                use_container_width=True,
                hide_index=True,
                column_order=["Rota", "Ordem", "Posicao", "Cliente", "Vendedor", "Pacotes", "Observacao", "Endereco"],
                column_config={
                    "Rota": st.column_config.SelectboxColumn(
                        "🔄 Rota (Trocar)",
                        options=nomes_ativas,
                        required=True,
                        width="medium"
                    ),
                    "Ordem": st.column_config.TextColumn("Ordem", disabled=True, width="small"),
                    "Posicao": st.column_config.SelectboxColumn(
                        "Posição",
                        options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                        required=True,
                        width="small"
                    ),
                    "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
                    "Vendedor": st.column_config.TextColumn("Vend. [ ]", width="small"),
                    "Pacotes": st.column_config.NumberColumn("PCT", min_value=1, max_value=10, step=1, width="small"),
                    "Observacao": st.column_config.TextColumn("Obs ( )", width="small"),
                    "Endereco": st.column_config.TextColumn("Endereço", width="large"),
                },
                key=f"editor_tabela_rotas_{st.session_state['versao_editor_rotas']}"
            )

            df_rotas_edit["Cliente"] = df_rotas_edit["Cliente"].astype(str).str.upper()
            st.session_state["df_rotas_editadas"] = df_rotas_edit

            mudou_rota_ou_pos = (
                not df_rotas_edit["Rota"].equals(df_rotas_base["Rota"]) or
                not df_rotas_edit["Posicao"].equals(df_rotas_base["Posicao"])
            )

            if mudou_rota_ou_pos and partida_ok:
                with st.spinner("Recalculando a melhor sequência das rotas após a alteração..."):
                    df_reotimizado, novo_km, coord_p, novas_geom, novos_avisos = recalcular_todas_as_rotas(
                        df_rotas_edit,
                        nomes_ativas,
                        lat_partida,
                        lon_partida,
                    )
                    st.session_state["df_rotas_calculadas"] = df_reotimizado
                    st.session_state["df_rotas_editadas"] = df_reotimizado.copy()
                    st.session_state["versao_editor_rotas"] += 1
                    st.session_state["resumo_km_rotas"] = novo_km
                    st.session_state["coord_partida_atual"] = coord_p
                    st.session_state["geometrias_rotas"] = novas_geom
                    st.session_state["avisos_rotas"] = novos_avisos
                    st.rerun()

            df_exibicao = st.session_state.get("df_rotas_editadas", df_rotas_base)

            for aviso_rota in st.session_state.get("avisos_rotas", []):
                st.warning(aviso_rota)

            with st.expander("🗺️ Ver Mapa das Rotas (Pinos Numerados por Ordem de Entrega)", expanded=True):
                renderizar_mapa_rotas(
                    df_exibicao,
                    nomes_ativas,
                    st.session_state["coord_partida_atual"],
                    desc_partida_validada,
                    st.session_state.get("geometrias_rotas", {}),
                )

            st.markdown("### 📋 Textos Prontos para Copiar (WhatsApp / Telegram)")
            st.caption("Clique no ícone de copiar no canto superior direito de cada caixa preta abaixo:")

            cols_texto = st.columns(min(len(nomes_ativas), 2))

            for idx_r, nome_r in enumerate(nomes_ativas):
                sub_rota = df_exibicao[df_exibicao["Rota"] == nome_r]
                col_atual = cols_texto[idx_r % len(cols_texto)]

                with col_atual:
                    qtd_entregas = len(sub_rota)
                    total_pct_rota = int(sub_rota["Pacotes"].sum()) if not sub_rota.empty else 0
                    km_desta_rota = resumo_km.get(nome_r, 0.0)

                    st.markdown(
                        f"**{nome_r}** — `{qtd_entregas} entregas` | `{total_pct_rota} pacotes` | `~{km_desta_rota} km`"
                    )

                    blocos_paradas = [nome_r]
                    for _, row_p in sub_rota.iterrows():
                        blocos_paradas.append(f"{row_p['Endereco']}\n{montar_linha_cliente(row_p)}")

                    texto_final_rota = "\n\n".join(blocos_paradas)
                    st.code(texto_final_rota, language="text", wrap_lines=True)

            st.divider()
            st.markdown("### 🏷️ Gerar Etiquetas 10x15 das Rotas Criadas")
            st.caption("Clique no botão abaixo para enviar todas as rotas acima diretamente para o Gerador de Etiquetas:")
            if st.button("🏷️ Gerar Etiquetas das Rotas Criadas", type="primary", use_container_width=True):
                df_etiq_importadas = importar_etiquetas_das_rotas_calculadas(df_exibicao)
                atualizar_base_etiquetas(df_etiq_importadas)
                st.session_state["modulo_ativo"] = "etiquetas"
                st.rerun()

        render_passo_4()
