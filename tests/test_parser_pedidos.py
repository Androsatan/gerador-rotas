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

TEXTO_BAIRRO_DEPOIS_DA_RUA = """
Guilherme Xavier

5g de silver haze

Rua Bernardo Guimarães 1581
Lourdes
"""


TEXTO_ENCAMINHADO = """
[23/10/2026 12:38] 2K:
Encaminhado de Loirin DP
Jão DC
26g  ice melt
Rua Delson renault 38
[23/10/2026 14:09] 2K:
Encaminhado de Tr
GABRIEL
75G PREN (25/25/25)
Rua Pedro José Moreira 14 são Lucas
[23/10/2026 14:30] 2K:
Encaminhado de 2K
nicolas
10g silver
Rua Padre Faustino, 387 - Carvalho de Brito
[23/10/2026 14:55] 2K:
Encaminhado de MCL
Pedro Esp
25 gold
Rua padre correa de almeida 203
[23/10/2026 15:51] 2K:
Encaminhado de Gd
Vinicius
15 g skunk orange
Rua Pedro Sigaud, 385/903 - Grajaú
[23/10/2026 15:51] 2K:
Encaminhado de Chucky
Persia
5g colombia
Rua Custodio Carreira, 35 - Prado
[23/10/2026 16:21] 2K:
Encaminhado de Surfista 2L
Tiago
25g de pren
Rua dos ferreiros, 113, são gabriel
[23/10/2026 16:22] 2K:
Encaminhado de TRUST
Nome: Raphael
Mercadoria: 5g Uva
Endereço: Praça Ellen Gould White, 43 - Solar do Barreiro
[23/10/2026 16:40] 2K:
Encaminhado de GAARA BG
LP
5g uva
Rua Flor da romã 91 jardim alvorada
[23/10/2026 15:56] 2K:
Encaminhado de GB
Daniel
3 byd
Rua Castelo Setubal, 644
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

    def test_bairro_depois_da_rua_nao_vira_outro_cliente(self):
        pedidos = listar_pre_pedidos(TEXTO_BAIRRO_DEPOIS_DA_RUA, {})
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["Cliente"], "GUILHERME XAVIER")
        self.assertIn("1581", pedidos[0]["Endereco_Bruto"])
        self.assertIn("Lourdes", pedidos[0]["Endereco_Bruto"])
        self.assertIn("silver haze", pedidos[0]["Itens_Lidos"].lower())
        self.assertNotIn("LOURDES", pedidos[0]["Cliente"])

    def test_bairro_na_linha_de_baixo_continua_no_endereco(self):
        texto = """
[22/10/2026 16:02] 2K:
Encaminhado de Surfista 2L
João Murilo
2 g indoor
Rua visconde de taunay 260
São lucas
"""
        pedidos = listar_pre_pedidos(texto, {})
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["Cliente"], "JOÃO MURILO")
        self.assertEqual(pedidos[0]["Vendedor"], "2L")
        self.assertIn("260", pedidos[0]["Endereco_Bruto"])
        self.assertIn("São lucas", pedidos[0]["Endereco_Bruto"])

    def test_nome_curto_seguido_de_produto_nao_vira_bairro(self):
        texto = """
JOAO
Rua das Flores 10
Serra
2g hax
"""
        pedidos = listar_pre_pedidos(texto, {})
        self.assertEqual(pedidos[0]["Cliente"], "JOAO")
        self.assertNotIn("serra", pedidos[0]["Endereco_Bruto"].lower())

    def test_qualquer_bairro_curto_na_linha_de_baixo_entra_no_endereco(self):
        texto = """
FERNANDA
10g hax
Rua Conselheiro Lafaiete 766
Camargos
"""
        pedidos = listar_pre_pedidos(texto, {})
        self.assertEqual(pedidos[0]["Cliente"], "FERNANDA")
        self.assertIn("Camargos", pedidos[0]["Endereco_Bruto"])

    def test_entregar_na_continua_sendo_o_endereco_do_cliente(self):
        texto = """
FERNANDA

10G Hax Uva

ENTREGAR NA CONSELHEIRO LAFAIETE 766
"""
        pedidos = listar_pre_pedidos(texto, {})
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["Cliente"], "FERNANDA")
        self.assertIn("766", pedidos[0]["Endereco_Bruto"])
        self.assertIn("lafaiete", pedidos[0]["Endereco_Bruto"].lower())

    def test_encaminhado_vira_sigla_e_nao_vira_cliente(self):
        pedidos = listar_pre_pedidos(TEXTO_ENCAMINHADO, {}, vendedor_padrao="ZZ")
        self.assertEqual(
            [(p["Cliente"], p["Vendedor"]) for p in pedidos],
            [
                ("JÃO DC", "DP"),
                ("GABRIEL", "TR"),
                ("NICOLAS", "2K"),
                ("PEDRO ESP", "MC"),
                ("VINICIUS", "GD"),
                ("PERSIA", "CK"),
                ("TIAGO", "2L"),
                ("RAPHAEL", "TR"),
                ("LP", "BG"),
                ("DANIEL", "GB"),
            ],
        )
        self.assertNotIn("ENCAMINHADO", pedidos[0]["Cliente"])
        self.assertNotIn("ENCAMINHADO", pedidos[0]["Endereco_Bruto"].upper())
        self.assertIn("38", pedidos[0]["Endereco_Bruto"])
        self.assertIn("ice melt", pedidos[0]["Itens_Lidos"].lower())
        self.assertIn("43", pedidos[7]["Endereco_Bruto"])
        self.assertIn("uva", pedidos[7]["Itens_Lidos"].lower())


if __name__ == "__main__":
    unittest.main()
