import unittest

from gerador_rotas.dominio.parser_pedidos import listar_pre_pedidos

TEXTO_VARIOS_NOMES = """
Rua Serra do rola moça 381

Vinicius
2 g md
6 balas BYD

Ryan
3 g pak mountain A+
2 g Silver haze

Ana Clara
1 g ice melt A+
"""

TEXTO_COM_CABECALHO = """
[17/10/2026 14:00] - Vendedor: Rua Serra do rola moca 381
Vinicius
2 g md
6 balas BYD
Ryan
3 g pak mountain A+
2 g Silver haze
Ana Clara
1 g ice melt A+
"""

TEXTO_DOIS_PEDIDOS = """
Fulano
2 g md
Rua Sao Vicente 250

Ciclano
3 g haze
Rua Serra do rola moca 381
"""


class VariosNomesMesmoEnderecoTest(unittest.TestCase):
    def test_endereco_no_topo_fica_um_pedido_com_o_primeiro_nome(self):
        pedidos = listar_pre_pedidos(TEXTO_VARIOS_NOMES, {})
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["Cliente"], "VINICIUS")
        self.assertIn("2 g md", pedidos[0]["Itens_Lidos"])
        self.assertIn("6 balas BYD", pedidos[0]["Itens_Lidos"])
        self.assertIn("3 g pak mountain A+", pedidos[0]["Itens_Lidos"])
        self.assertIn("1 g ice melt A+", pedidos[0]["Itens_Lidos"])
        self.assertNotIn("RYAN", pedidos[0]["Itens_Lidos"].upper())
        self.assertNotIn("ANA CLARA", pedidos[0]["Itens_Lidos"].upper())
        self.assertIn("381", pedidos[0]["Endereco_Bruto"])

    def test_mensagem_de_whatsapp_tambem_fica_um_pedido(self):
        pedidos = listar_pre_pedidos(TEXTO_COM_CABECALHO, {})
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["Cliente"], "VINICIUS")

    def test_dois_enderecos_continuam_dois_pedidos(self):
        pedidos = listar_pre_pedidos(TEXTO_DOIS_PEDIDOS, {})
        self.assertEqual(len(pedidos), 2)
        self.assertEqual(pedidos[0]["Cliente"], "FULANO")
        self.assertEqual(pedidos[1]["Cliente"], "CICLANO")
        self.assertIn("250", pedidos[0]["Endereco_Bruto"])
        self.assertIn("381", pedidos[1]["Endereco_Bruto"])


if __name__ == "__main__":
    unittest.main()
