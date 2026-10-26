from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from gerador_rotas.dominio.parser_pedidos import montar_linha_cliente
from gerador_rotas.dominio.parser_rotas_prontas import (
    acrescentar_paradas,
    extrair_paradas_de_rotas_prontas,
)
from gerador_rotas.estado import atualizar_base_etiquetas
from gerador_rotas.etiquetas.parser import importar_etiquetas_das_rotas_calculadas
from gerador_rotas.geo.geocodificadores import geocodificar_endereco_rua
from gerador_rotas.rotas.planejador import medir_rotas_na_ordem, recalcular_todas_as_rotas
from gerador_rotas.ui.mapa import renderizar_mapa_rotas


def _coordenadas_dos_enderecos(enderecos: list) -> dict:
    unicos = list(dict.fromkeys(e for e in enderecos if str(e).strip()))
    achados = {}
    if not unicos:
        return achados
    with ThreadPoolExecutor(max_workers=min(8, len(unicos))) as pool:
        futuros = {pool.submit(geocodificar_endereco_rua, end): end for end in unicos}
        for futuro in as_completed(futuros):
            end = futuros[futuro]
            try:
                achados[end] = futuro.result()
            except Exception:
                achados[end] = (None, None)
    return achados


def _preencher_coordenadas(df: pd.DataFrame) -> pd.DataFrame:
    saida = df.copy()
    mapa = _coordenadas_dos_enderecos([str(e) for e in saida["Endereco"]])
    for idx, row in saida.iterrows():
        lat, lon = mapa.get(str(row["Endereco"]), (None, None))
        saida.at[idx, "Lat"] = lat
        saida.at[idx, "Lon"] = lon
    return saida


def _garantir_estado():
    if "df_otimizador" not in st.session_state:
        st.session_state["df_otimizador"] = pd.DataFrame()
    if "df_otimizador_editado" not in st.session_state:
        st.session_state["df_otimizador_editado"] = pd.DataFrame()
    if "versao_editor_otimizador" not in st.session_state:
        st.session_state["versao_editor_otimizador"] = 0
    if "nomes_rotas_otimizador" not in st.session_state:
        st.session_state["nomes_rotas_otimizador"] = []
    if "resumo_km_otimizador" not in st.session_state:
        st.session_state["resumo_km_otimizador"] = {}
    if "coord_partida_otimizador" not in st.session_state:
        st.session_state["coord_partida_otimizador"] = None
    if "geometrias_otimizador" not in st.session_state:
        st.session_state["geometrias_otimizador"] = {}
    if "avisos_otimizador" not in st.session_state:
        st.session_state["avisos_otimizador"] = []
    if "contador_form_otimizador" not in st.session_state:
        st.session_state["contador_form_otimizador"] = 0


def _limpar_rotas_montadas():
    st.session_state["df_otimizador"] = pd.DataFrame()
    st.session_state["df_otimizador_editado"] = pd.DataFrame()
    st.session_state["versao_editor_otimizador"] = st.session_state.get("versao_editor_otimizador", 0) + 1
    st.session_state["nomes_rotas_otimizador"] = []
    st.session_state["resumo_km_otimizador"] = {}
    st.session_state["coord_partida_otimizador"] = None
    st.session_state["geometrias_otimizador"] = {}
    st.session_state["avisos_otimizador"] = []
    st.session_state["contador_form_otimizador"] = st.session_state.get("contador_form_otimizador", 0) + 1


def _gravar_rotas(df, nomes, resumo, coord, geometrias, avisos):
    st.session_state["df_otimizador"] = df
    st.session_state["df_otimizador_editado"] = df.copy()
    st.session_state["versao_editor_otimizador"] += 1
    st.session_state["nomes_rotas_otimizador"] = list(nomes)
    st.session_state["resumo_km_otimizador"] = resumo
    st.session_state["coord_partida_otimizador"] = coord
    st.session_state["geometrias_otimizador"] = geometrias
    st.session_state["avisos_otimizador"] = avisos


def render_pagina_otimizador(partida_ok, desc_partida_validada, lat_partida, lon_partida):
    _garantir_estado()
    st.title("🧭 Otimizador de Rotas")
    st.caption(
        "Cole rotas que já estão prontas, no mesmo texto do WhatsApp. "
        "Cada colagem soma às rotas que já estão no mapa. "
        "O endereço escrito permanece, e os pontos entram no mapa para a ordem ser recalculada."
    )

    df_atual = st.session_state["df_otimizador"]
    if (
        partida_ok
        and not df_atual.empty
        and st.session_state["coord_partida_otimizador"] != (lat_partida, lon_partida)
    ):
        nomes = st.session_state["nomes_rotas_otimizador"]
        base = st.session_state.get("df_otimizador_editado", df_atual)
        resumo, geometrias, avisos = medir_rotas_na_ordem(base, nomes, lat_partida, lon_partida)
        st.session_state["resumo_km_otimizador"] = resumo
        st.session_state["geometrias_otimizador"] = geometrias
        st.session_state["avisos_otimizador"] = avisos
        st.session_state["coord_partida_otimizador"] = (lat_partida, lon_partida)

    texto = st.text_area(
        "Cole as rotas prontas:",
        height=220,
        key=f"texto_otimizador_{st.session_state['contador_form_otimizador']}",
        placeholder=(
            "ROTA FP\n\n"
            "Rua Carlindo Costa Ferreira, 56, Eymard, Belo Horizonte, 31930-625\n"
            "CAROLINE [TR] (2PCT)\n\n"
            "Avenida Amazonas, 1044, Centro, Belo Horizonte, 30180-006\n"
            "GEORGE [TR]"
        ),
    )

    if st.button("📍 Adicionar rotas no mapa", type="primary", use_container_width=True):
        if not texto.strip():
            st.warning("Cole pelo menos uma rota antes de adicionar.")
        elif not partida_ok:
            st.error("Corrija o ponto de partida na barra lateral antes de adicionar as rotas.")
        else:
            df_lido, _ = extrair_paradas_de_rotas_prontas(texto)
            if df_lido.empty:
                st.warning("Não encontrei pares de endereço e cliente nesse texto.")
            else:
                with st.spinner("Localizando os pontos e desenhando o caminho..."):
                    df_geo = _preencher_coordenadas(df_lido)
                    base = st.session_state.get("df_otimizador_editado", df_atual)
                    if base is None or base.empty:
                        base = df_atual
                    df_junto, nomes, pulados = acrescentar_paradas(
                        base,
                        st.session_state["nomes_rotas_otimizador"],
                        df_geo,
                    )
                    resumo, geometrias, avisos = medir_rotas_na_ordem(
                        df_junto, nomes, lat_partida, lon_partida
                    )
                if pulados:
                    citados = ", ".join(pulados[:8])
                    avisos = list(avisos) + [
                        f"{len(pulados)} parada(s) já estavam no mapa e não foram repetidas: {citados}"
                    ]
                if len(df_junto) == len(base) and not base.empty:
                    st.warning("Essas paradas já estavam no mapa.")
                else:
                    _gravar_rotas(
                        df_junto, nomes, resumo, (lat_partida, lon_partida), geometrias, avisos
                    )
                    st.session_state["contador_form_otimizador"] += 1
                    st.rerun()

    if st.session_state["df_otimizador"].empty:
        return

    st.divider()
    st.subheader("Rotas no mapa e ajuste entre rotas")

    @st.fragment
    def render_painel():
        df_base = st.session_state["df_otimizador"]
        nomes = st.session_state["nomes_rotas_otimizador"]
        resumo = st.session_state["resumo_km_otimizador"]

        sem_ponto = df_base[df_base["Lat"].isna() | df_base["Lon"].isna()]
        if not sem_ponto.empty:
            citados = ", ".join(str(n) for n in sem_ponto["Cliente"].tolist()[:8])
            st.warning(
                f"{len(sem_ponto)} parada(s) ficaram sem ponto no mapa e entram no fim se a ordem for otimizada: {citados}"
            )

        if st.button(
            "✨ Otimizar a ordem de cada rota",
            type="primary",
            use_container_width=True,
            disabled=not partida_ok,
        ):
            with st.spinner("Recalculando a sequência a partir do ponto de partida..."):
                base = st.session_state.get("df_otimizador_editado", df_base)
                df_novo, novo_km, coord, geometrias, avisos = recalcular_todas_as_rotas(
                    base, nomes, lat_partida, lon_partida
                )
                _gravar_rotas(df_novo, nomes, novo_km, coord, geometrias, avisos)
                st.rerun()

        st.caption(
            "A otimização mantém cada cliente na rota em que foi colado. "
            "Para passar um pedido de uma rota para outra ou mudar quem é o PRIMEIRO/ÚLTIMO, "
            "altere a coluna Rota ou Posição: a sequência é recalculada."
        )

        df_edit = st.data_editor(
            df_base,
            use_container_width=True,
            hide_index=True,
            column_order=["Rota", "Ordem", "Posicao", "Cliente", "Vendedor", "Pacotes", "Observacao", "Endereco"],
            column_config={
                "Rota": st.column_config.SelectboxColumn(
                    "🔄 Rota (Trocar)",
                    options=nomes,
                    required=True,
                    width="medium",
                ),
                "Ordem": st.column_config.TextColumn("Ordem", disabled=True, width="small"),
                "Posicao": st.column_config.SelectboxColumn(
                    "Posição",
                    options=["Normal", "PRIMEIRO", "ÚLTIMO"],
                    required=True,
                    width="small",
                ),
                "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
                "Vendedor": st.column_config.TextColumn("Vend. [ ]", width="small"),
                "Pacotes": st.column_config.NumberColumn("PCT", min_value=1, max_value=10, step=1, width="small"),
                "Observacao": st.column_config.TextColumn("Obs ( )", width="small"),
                "Endereco": st.column_config.TextColumn("Endereço", width="large"),
            },
            key=f"editor_otimizador_{st.session_state['versao_editor_otimizador']}",
        )
        df_edit["Cliente"] = df_edit["Cliente"].astype(str).str.upper()
        st.session_state["df_otimizador_editado"] = df_edit

        mudou = (
            not df_edit["Rota"].equals(df_base["Rota"])
            or not df_edit["Posicao"].equals(df_base["Posicao"])
        )
        if mudou and partida_ok:
            with st.spinner("Recalculando a melhor sequência das rotas após a alteração..."):
                df_novo, novo_km, coord, geometrias, avisos = recalcular_todas_as_rotas(
                    df_edit, nomes, lat_partida, lon_partida
                )
                _gravar_rotas(df_novo, nomes, novo_km, coord, geometrias, avisos)
                st.rerun()

        df_exibicao = st.session_state.get("df_otimizador_editado", df_base)
        for aviso in st.session_state.get("avisos_otimizador", []):
            st.warning(aviso)

        with st.expander("🗺️ Ver Mapa das Rotas (Pinos Numerados por Ordem de Entrega)", expanded=True):
            renderizar_mapa_rotas(
                df_exibicao,
                nomes,
                st.session_state["coord_partida_otimizador"],
                desc_partida_validada,
                st.session_state.get("geometrias_otimizador", {}),
            )

        st.markdown("### 📋 Textos Prontos para Copiar (WhatsApp / Telegram)")
        st.caption("Clique no ícone de copiar no canto superior direito de cada caixa preta abaixo:")

        cols_texto = st.columns(min(len(nomes), 2) or 1)
        for idx_r, nome_r in enumerate(nomes):
            sub = df_exibicao[df_exibicao["Rota"] == nome_r]
            with cols_texto[idx_r % len(cols_texto)]:
                qtd = len(sub)
                total_pct = int(sub["Pacotes"].sum()) if not sub.empty else 0
                km = resumo.get(nome_r, 0.0)
                txt_entregas = "entrega" if qtd == 1 else "entregas"
                txt_pacotes = "pacote" if total_pct == 1 else "pacotes"
                st.markdown(
                    f"**{nome_r}** — `{qtd} {txt_entregas}` | `{total_pct} {txt_pacotes}` | `~{km} km`"
                )
                blocos = [nome_r]
                for _, row_p in sub.iterrows():
                    blocos.append(f"{row_p['Endereco']}\n{montar_linha_cliente(row_p)}")
                st.code("\n\n".join(blocos), language="text", wrap_lines=True)

        st.divider()
        st.markdown("### 🏷️ Gerar Etiquetas 10x15 das Rotas")
        st.caption("Envia as rotas acima para o Gerador de Etiquetas:")
        col_etiq, col_limpar = st.columns(2)
        with col_etiq:
            if st.button("🏷️ Gerar Etiquetas das Rotas", type="primary", use_container_width=True):
                atualizar_base_etiquetas(importar_etiquetas_das_rotas_calculadas(df_exibicao))
                st.session_state["modulo_ativo"] = "etiquetas"
                st.rerun()
        with col_limpar:
            if st.button("🧹 Limpar rotas montadas", use_container_width=True):
                _limpar_rotas_montadas()
                st.rerun()

    render_painel()
