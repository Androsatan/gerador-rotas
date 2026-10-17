import os
from io import BytesIO

import pandas as pd
from pypdf import PageObject, PdfReader, PdfWriter
from reportlab.lib.pagesizes import portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from gerador_rotas.dominio.constantes import NOMES_ARQUIVO_MODELO

def localizar_modelo_pdf_no_repositorio():
    aqui = os.path.dirname(os.path.abspath(__file__))
    pasta_repositorio = os.path.abspath(os.path.join(aqui, os.pardir, os.pardir))
    for nome_arq in NOMES_ARQUIVO_MODELO:
        for pasta in (pasta_repositorio, os.getcwd(), aqui):
            caminho_tentativa = os.path.join(pasta, nome_arq)
            if os.path.exists(caminho_tentativa):
                return caminho_tentativa
    return None

def quebrar_endereco_duas_linhas(endereco: str, limite_chars: int = 50):
    end = endereco.strip()
    if "MG," in end:
        partes = end.split("MG,", 1)
        return partes[0].strip() + " MG", partes[1].strip()

    if len(end) <= limite_chars:
        return end, ""

    corte = end.rfind(",", 0, limite_chars)
    if corte == -1:
        corte = end.rfind(" ", 0, limite_chars)
    if corte == -1:
        return end[:limite_chars], end[limite_chars:].strip()

    linha1 = end[:corte].strip(" ,")
    linha2 = end[corte:].strip(" ,")
    return linha1, linha2


def gerar_pdf_etiquetas_10x15(df_selecionadas: pd.DataFrame, fonte_modelo_pdf) -> bytes:
    largura, altura = 100 * mm, 150 * mm
    pdf_final_writer = PdfWriter()

    for _, row in df_selecionadas.iterrows():
        modelo_reader = PdfReader(fonte_modelo_pdf)
        modelo_pagina = modelo_reader.pages[0]

        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=portrait((largura, altura)))

        can.setFont("Helvetica-Bold", 9)
        can.drawString(38 * mm, 200, str(row.get("Nome Etiqueta", "")).strip())

        can.setFont("Helvetica", 8)
        end_str = str(row.get("Endereco Etiqueta", "")).strip()
        linha_end_1, linha_end_2 = quebrar_endereco_duas_linhas(end_str, limite_chars=50)

        if linha_end_2:
            can.drawString(9 * mm, 184, linha_end_1)
            can.drawString(9 * mm, 175, linha_end_2)
        else:
            can.drawString(9 * mm, 182, linha_end_1)

        can.save()
        packet.seek(0)

        overlay = PdfReader(packet).pages[0]
        saida_pag = PageObject.create_blank_page(width=largura, height=altura)
        saida_pag.merge_page(modelo_pagina)
        saida_pag.merge_page(overlay)
        pdf_final_writer.add_page(saida_pag)

    pdf_saida = BytesIO()
    pdf_final_writer.write(pdf_saida)
    return pdf_saida.getvalue()
