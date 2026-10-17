import re

from gerador_rotas.dominio.constantes import STOPWORDS_PRODUTOS
from gerador_rotas.dominio.similaridade import (
    extrair_palavras_item,
    remover_acentos,
    similaridade_palavras,
)

def identificar_locais_dos_itens(itens_pedido: list, locais_dict: dict):
    locais_acionados = set()

    vocab_locais = {}
    for nome_local, lista_prods in locais_dict.items():
        frases_e_palavras = []
        for prod in lista_prods:
            prod_norm = remover_acentos(prod.strip().lower())
            if not prod_norm:
                continue
            palavras_prod = [
                p for p in re.findall(r"[a-z0-9@]+", prod_norm)
                if p not in STOPWORDS_PRODUTOS
            ]
            colado = "".join(palavras_prod)
            if colado and colado not in palavras_prod:
                palavras_prod.append(colado)
            frases_e_palavras.append((prod_norm, palavras_prod))
        vocab_locais[nome_local] = frases_e_palavras

    sub_itens = []
    for linha in itens_pedido:
        partes_plus = re.split(r"[+;]", linha)
        for p in partes_plus:
            if p.strip():
                sub_itens.append(p.strip())

    for item_str in sub_itens:
        linha_norm = remover_acentos(item_str.lower()).strip(" ()[]")
        if not linha_norm:
            continue

        for nome_local, lista_fp in vocab_locais.items():
            for frase_completa, _ in lista_fp:
                frase_sem_espaco = frase_completa.replace(" ", "")
                if frase_completa in ("@", "md", "lsd") and re.search(rf"(?:^|\d|\s|#){re.escape(frase_completa)}(?:$|\s)", linha_norm):
                    locais_acionados.add(nome_local)
                elif len(frase_completa) >= 3 and (
                    re.search(rf"\b{re.escape(frase_completa)}\b", linha_norm)
                    or (len(frase_sem_espaco) >= 5 and frase_sem_espaco in linha_norm)
                ):
                    locais_acionados.add(nome_local)

        palavras_cliente = extrair_palavras_item(linha_norm)
        for pal_cli in palavras_cliente:
            melhor_local_palavra = None
            maior_nota_palavra = 0.0

            for nome_local, lista_fp in vocab_locais.items():
                for _, palavras_prod in lista_fp:
                    for pal_cad in palavras_prod:
                        nota = similaridade_palavras(pal_cli, pal_cad)
                        if nota > maior_nota_palavra:
                            maior_nota_palavra = nota
                            melhor_local_palavra = nome_local

            if maior_nota_palavra >= 0.76 and melhor_local_palavra:
                locais_acionados.add(melhor_local_palavra)

    lista_locais_ordenada = sorted(list(locais_acionados))
    qtd_pacotes = max(1, len(lista_locais_ordenada))
    return qtd_pacotes, lista_locais_ordenada
