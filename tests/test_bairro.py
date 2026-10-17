import unittest
from pathlib import Path

from gerador_rotas.geo.bairro import escolher_candidato_bairro


class EscolhaDeBairroTest(unittest.TestCase):
    def test_maria_goretti_nao_cai_em_cidade_nova_nem_na_rua_do_barreiro(self):
        candidatos = [
            {"nome": "Cidade Nova", "lat": -19.890, "lon": -43.920, "tipo": "suburb"},
            {"nome": "Rua Santa Maria Goretti", "lat": -19.980, "lon": -44.015, "tipo": "highway"},
            {"nome": "Santa Maria Goretti", "lat": -19.863, "lon": -43.909, "tipo": "suburb"},
        ]
        escolhido = escolher_candidato_bairro("Maria Goretti", candidatos)
        self.assertIsNotNone(escolhido)
        self.assertEqual(escolhido["nome"], "Santa Maria Goretti")
        self.assertGreater(escolhido["lat"], -19.875)
        self.assertLess(escolhido["lat"], -19.84)

    def test_rua_homonima_nao_serve_como_bairro(self):
        candidatos = [
            {"nome": "Rua Santa Maria Goretti", "lat": -19.980, "lon": -44.015, "tipo": "streetaddress"},
        ]
        self.assertIsNone(escolher_candidato_bairro("Maria Goretti", candidatos))

    def test_codigo_nao_grava_o_ponto_errado(self):
        raiz = Path(__file__).resolve().parents[1] / "gerador_rotas"
        texto = "\n".join(p.read_text(encoding="utf-8") for p in raiz.rglob("*.py"))
        self.assertNotIn("-19.8808", texto)
        self.assertNotIn("COORDENADAS_BAIRROS_FIXOS", texto)


if __name__ == "__main__":
    unittest.main()
