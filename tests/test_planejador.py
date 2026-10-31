import unittest
from unittest.mock import patch

import pandas as pd

from gerador_rotas.rotas.planejador import atribuir_paradas, encaixar_na_rota, ordenar_paradas


def matriz_linha(n_stops: int):
    n = n_stops + 1
    return [[abs(i - j) * 100 for j in range(n)] for i in range(n)]


class OrdenacaoAbertaTest(unittest.TestCase):
    def test_linha_termina_no_cliente_mais_longe(self):
        matriz = matriz_linha(4)
        ordem, _km = ordenar_paradas(matriz, matriz, ["Normal"] * 4)
        self.assertEqual(ordem, [0, 1, 2, 3])
        self.assertEqual(ordem[-1], 3)

    def test_primeiro_sai_na_frente_e_a_rota_nao_volta(self):
        matriz = matriz_linha(4)
        ordem, _km = ordenar_paradas(
            matriz,
            matriz,
            ["Normal", "Normal", "Normal", "PRIMEIRO"],
        )
        self.assertEqual(ordem[0], 3)
        self.assertEqual(sorted(ordem), [0, 1, 2, 3])
        self.assertNotIn(-1, ordem)
        self.assertEqual(len(ordem), 4)

    def test_ultimo_fecha_a_rota(self):
        matriz = matriz_linha(4)
        ordem, _km = ordenar_paradas(
            matriz,
            matriz,
            ["ULTIMO", "Normal", "Normal", "Normal"],
        )
        self.assertEqual(ordem[-1], 0)
        self.assertEqual(sorted(ordem), [0, 1, 2, 3])


class CotasTest(unittest.TestCase):
    def test_cotas_4_e_2_na_linha(self):
        matriz = matriz_linha(6)
        grupos = atribuir_paradas(matriz, [4, 2], segundos=5)
        self.assertIsNotNone(grupos)
        self.assertEqual(len(grupos[0]), 4)
        self.assertEqual(len(grupos[1]), 2)
        self.assertEqual(sorted(i for g in grupos for i in g), list(range(6)))

    def test_cotas_iguais_separam_a_linha_em_dois_blocos(self):
        matriz = matriz_linha(6)
        grupos = atribuir_paradas(matriz, [3, 3], segundos=5)
        self.assertIsNotNone(grupos)
        conjuntos = {tuple(sorted(g)) for g in grupos}
        self.assertEqual(conjuntos, {(0, 1, 2), (3, 4, 5)})
        for grupo in grupos:
            ordem, _km = ordenar_paradas(
                _sub(matriz, grupo),
                _sub(matriz, grupo),
                ["Normal"] * len(grupo),
            )
            sequencia = [grupo[i] for i in ordem]
            self.assertEqual(sequencia, sorted(grupo))
            self.assertEqual(sequencia[-1], max(grupo))


class EncaixarNaRotaTest(unittest.TestCase):
    def test_pedido_novo_entra_no_meio_e_a_outra_rota_fica(self):
        df = pd.DataFrame([
            {"Rota": "ROTA FP", "Ordem": "1º", "Posicao": "Normal", "Cliente": "ANA", "Lat": -19.90, "Lon": -43.90},
            {"Rota": "ROTA LE", "Ordem": "1º", "Posicao": "Normal", "Cliente": "PERTO", "Lat": -19.91, "Lon": -43.91},
            {"Rota": "ROTA LE", "Ordem": "2º", "Posicao": "Normal", "Cliente": "LONGE", "Lat": -20.00, "Lon": -44.00},
            {"Rota": "ROTA LE", "Ordem": "3º", "Posicao": "Normal", "Cliente": "NOVO", "Lat": -19.95, "Lon": -43.95},
        ])

        def matriz(pontos):
            n = len(pontos)
            pos = [0, 1, 3, 2] if n == 4 else list(range(n))
            dur = [[abs(pos[i] - pos[j]) * 100 for j in range(n)] for i in range(n)]
            return dur, dur, "osrm"

        with patch("gerador_rotas.rotas.planejador.obter_matriz_osrm", side_effect=matriz), \
             patch("gerador_rotas.rotas.planejador.obter_geometria_osrm", side_effect=lambda pontos: [[p[0], p[1]] for p in pontos]), \
             patch("gerador_rotas.rotas.planejador.obter_trajeto_osrm", side_effect=lambda pontos: ([[p[0], p[1]] for p in pontos], 1000)):
            saida, _resumo, _geom, _avisos = encaixar_na_rota(
                df, ["ROTA FP", "ROTA LE"], "ROTA LE", -19.90, -43.90
            )

        self.assertEqual(saida["Cliente"].tolist(), ["ANA", "PERTO", "NOVO", "LONGE"])
        le = saida[saida["Rota"] == "ROTA LE"]
        self.assertEqual(le["Ordem"].tolist(), ["1º", "2º", "3º"])


def _sub(matriz, grupo):
    idxs = [0] + [i + 1 for i in grupo]
    m = len(idxs)
    sub = [[0] * m for _ in range(m)]
    for a in range(m):
        for b in range(m):
            sub[a][b] = matriz[idxs[a]][idxs[b]]
    return sub


if __name__ == "__main__":
    unittest.main()
