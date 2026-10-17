import unittest

from gerador_rotas.etiquetas.parser import (
    endereco_de_etiqueta_resolvido,
    endereco_etiqueta_precisa_busca,
)


class EnderecoEtiquetaTest(unittest.TestCase):
    def test_rua_solta_precisa_da_busca(self):
        self.assertTrue(endereco_etiqueta_precisa_busca("RUA ITU 856"))

    def test_endereco_com_cep_nao_busca_de_novo(self):
        completo = "Rua Itu, 856, Renascença, Belo Horizonte, 31130-570"
        self.assertFalse(endereco_etiqueta_precisa_busca(completo))

    def test_usa_o_endereco_completo_quando_a_busca_confirma(self):
        resolvido = endereco_de_etiqueta_resolvido(
            "RUA ITU 856",
            "Rua Itu, 856, Renascença, Belo Horizonte, 31130-570",
            "✅ OK",
        )
        self.assertIn("Renascença", resolvido)
        self.assertIn("31130-570", resolvido)

    def test_falha_de_busca_mantem_o_texto_digitado(self):
        resolvido = endereco_de_etiqueta_resolvido(
            "RUA ITU 856",
            "Rua Itu, 856, Belo Horizonte",
            "❌ RUA NÃO CONFIRMADA - CONFERIR",
        )
        self.assertEqual(resolvido, "RUA ITU 856")


if __name__ == "__main__":
    unittest.main()
