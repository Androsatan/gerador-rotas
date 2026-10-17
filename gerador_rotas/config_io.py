import json
import os

from gerador_rotas.dominio.constantes import ARQUIVO_CONFIG

def carregar_config():
    padrao = {
        "ponto_partida": "Bairro Maria Goretti, Belo Horizonte, MG",
        "local_1": "skunk, orange, amnesia, silver, wolf, super sheep, og kush, indoor, zowahh",
        "local_2": "ice, pak, dry, pod, colombia gold, uva",
        "local_3": "@, md, lsd, pacote gd",
        "local_4": "pren"
    }
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
                padrao.update(dados)
        except Exception:
            pass
    return padrao


def salvar_config(dados: dict):
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
