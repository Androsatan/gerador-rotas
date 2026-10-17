import unittest

from gerador_rotas.dominio.endereco_texto import (
    eh_nome_de_cidade,
    numero_cabe_na_faixa_viacep,
    separar_componentes_endereco,
)
from gerador_rotas.dominio.similaridade import similaridade_ruas


class FaixaViaCepTest(unittest.TestCase):
    def test_numero_1581_so_entra_na_faixa_de_lourdes(self):
        faixas = {
            "de 2881/2882 ao fim": False,
            "911": False,
            "de 701/702 a 949/950": False,
            "de 951/952 a 1399/1400": False,
            "de 2351/2352 a 2879/2880": False,
            "de 1951/1952 a 2349/2350": False,
            "de 1401/1402 a 1949/1950": True,
            "de 391/392 a 699/700": False,
            "até 389/390": False,
            "": False,
        }
        for complemento, esperado in faixas.items():
            self.assertEqual(
                numero_cabe_na_faixa_viacep("1581", complemento),
                esperado,
                complemento,
            )

    def test_cidade_nao_e_bairro(self):
        self.assertTrue(eh_nome_de_cidade("Belo Horizonte"))
        self.assertTrue(eh_nome_de_cidade("Contagem"))
        self.assertFalse(eh_nome_de_cidade("Lourdes"))
        self.assertFalse(eh_nome_de_cidade("Santa Tereza"))

    def test_rua_parecida_com_palavra_a_mais_nao_conta(self):
        self.assertLess(similaridade_ruas("Rua Iriba", "Rua Cova da Iriá"), 0.68)
        self.assertGreater(similaridade_ruas("Rua Iriba", "Rua Iriba"), 0.90)

    def test_bairro_na_linha_seguinte_entra_no_endereco(self):
        rua, numero, bairro, _cidade = separar_componentes_endereco(
            "Rua Bernardo Guimarães 1581, Lourdes"
        )
        self.assertIn("1581", numero)
        self.assertEqual(bairro.lower(), "lourdes")
        self.assertIn("bernardo", rua.lower())


if __name__ == "__main__":
    unittest.main()
