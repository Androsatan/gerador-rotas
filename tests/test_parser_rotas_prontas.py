import unittest

from gerador_rotas.dominio.parser_rotas_prontas import (
    acrescentar_paradas,
    extrair_paradas_de_rotas_prontas,
    separar_linha_cliente,
)

TEXTO_DUAS_ROTAS = """
ROTA FP — 10 entregas | 13 pacotes | ~37.0 km

Rua Carlindo Costa Ferreira, 56, Eymard, Belo Horizonte, 31930-625
CAROLINE [TR] (2PCT)

Rua Tereza Cristina, 7, Alvorada, Sabará, 34700-010
LUCAS PEDERSOLI [2K]

ROTA HG

Avenida Amazonas, 1044, Centro, Belo Horizonte, 30180-006
GEORGE [TR]

Rua dos Guajajaras, 718, Centro, Belo Horizonte, 30180-106
VINICIUS GUSS [2K] (PORTARIA)
"""


class ParserRotasProntasTest(unittest.TestCase):
    def test_separa_sigla_pacotes_e_observacao(self):
        nome, vend, pct, obs = separar_linha_cliente("CAROLINE [TR] (2PCT)")
        self.assertEqual((nome, vend, pct, obs), ("CAROLINE", "TR", 2, ""))
        nome, vend, pct, obs = separar_linha_cliente("VINICIUS GUSS [2K] (PORTARIA)")
        self.assertEqual((nome, vend, pct, obs), ("VINICIUS GUSS", "2K", 1, "PORTARIA"))

    def test_extrai_rotas_e_preserva_o_endereco_escrito(self):
        df, nomes = extrair_paradas_de_rotas_prontas(TEXTO_DUAS_ROTAS)
        self.assertEqual(nomes, ["ROTA FP", "ROTA HG"])
        self.assertEqual(len(df), 4)
        self.assertEqual(list(df["Cliente"]), ["CAROLINE", "LUCAS PEDERSOLI", "GEORGE", "VINICIUS GUSS"])
        self.assertEqual(list(df["Vendedor"]), ["TR", "2K", "TR", "2K"])
        self.assertEqual(list(df["Pacotes"]), [2, 1, 1, 1])
        self.assertEqual(df.iloc[3]["Observacao"], "PORTARIA")
        self.assertEqual(list(df["Ordem"]), ["1º", "2º", "1º", "2º"])
        george = df.iloc[2]["Endereco"]
        self.assertEqual(
            george,
            "Avenida Amazonas, 1044, Centro, Belo Horizonte, 30180-006",
        )
        self.assertNotIn("Beco", george)
        self.assertNotIn("Contagem", george)

    def test_aceita_o_cliente_antes_do_endereco(self):
        texto = "ROTA LE\n\nMARLON [GD]\nRua dos Timbiras, 2889, Barro Preto, Belo Horizonte, 30140-062\n"
        df, nomes = extrair_paradas_de_rotas_prontas(texto)
        self.assertEqual(nomes, ["ROTA LE"])
        self.assertEqual(df.iloc[0]["Cliente"], "MARLON")
        self.assertIn("Timbiras", df.iloc[0]["Endereco"])

    def test_endereco_sozinho_vira_cliente_generico(self):
        df, _ = extrair_paradas_de_rotas_prontas(
            "ROTA 3\n\nRua Cambuí, 330, Cruzeiro, Belo Horizonte, 30310-180\n"
        )
        self.assertEqual(df.iloc[0]["Cliente"], "CLIENTE")
        self.assertEqual(df.iloc[0]["Rota"], "ROTA 3")

    def test_endereco_que_comeca_com_rota_nao_vira_titulo(self):
        texto = (
            "ROTA FP\n\n"
            "Rota do Sol, 10, Centro, Belo Horizonte, 30180-006\n"
            "ANA [TR]\n"
        )
        df, nomes = extrair_paradas_de_rotas_prontas(texto)
        self.assertEqual(nomes, ["ROTA FP"])
        self.assertEqual(df.iloc[0]["Cliente"], "ANA")
        self.assertTrue(str(df.iloc[0]["Endereco"]).lower().startswith("rota do sol"))

    def test_segunda_rota_entra_sem_apagar_a_primeira(self):
        primeira, _ = extrair_paradas_de_rotas_prontas(
            "ROTA FP\n\n"
            "Rua Carlindo Costa Ferreira, 56, Eymard, Belo Horizonte, 31930-625\n"
            "CAROLINE [TR] (2PCT)\n"
        )
        segunda, _ = extrair_paradas_de_rotas_prontas(
            "ROTA HG\n\n"
            "Avenida Amazonas, 1044, Centro, Belo Horizonte, 30180-006\n"
            "GEORGE [TR]\n"
        )
        df, nomes, pulados = acrescentar_paradas(primeira, ["ROTA FP"], segunda)
        self.assertEqual(nomes, ["ROTA FP", "ROTA HG"])
        self.assertEqual(list(df["Cliente"]), ["CAROLINE", "GEORGE"])
        self.assertEqual(pulados, [])
        self.assertIn("Avenida Amazonas, 1044", df.iloc[1]["Endereco"])

    def test_clientes_novos_entram_no_fim_da_rota_que_ja_existe(self):
        primeira, _ = extrair_paradas_de_rotas_prontas(
            "ROTA FP\n\nRua A, 1, Centro, Belo Horizonte, 30180-006\nCAROLINE [TR]\n"
        )
        mais, _ = extrair_paradas_de_rotas_prontas(
            "ROTA FP\n\nRua B, 2, Centro, Belo Horizonte, 30180-106\nLUCAS [2K]\n"
        )
        df, nomes, _ = acrescentar_paradas(primeira, ["ROTA FP"], mais)
        self.assertEqual(nomes, ["ROTA FP"])
        self.assertEqual(list(df["Cliente"]), ["CAROLINE", "LUCAS"])
        self.assertEqual(list(df["Ordem"]), ["1º", "2º"])

    def test_parada_repetida_nao_entra_de_novo(self):
        primeira, _ = extrair_paradas_de_rotas_prontas(
            "ROTA FP\n\nRua A, 1, Centro, Belo Horizonte, 30180-006\nCAROLINE [TR]\n"
        )
        df, nomes, pulados = acrescentar_paradas(primeira, ["ROTA FP"], primeira)
        self.assertEqual(len(df), 1)
        self.assertEqual(nomes, ["ROTA FP"])
        self.assertEqual(pulados, ["CAROLINE"])

    def test_texto_vazio_nao_gera_parada(self):
        df, nomes = extrair_paradas_de_rotas_prontas("   \n")
        self.assertTrue(df.empty)
        self.assertEqual(nomes, [])


if __name__ == "__main__":
    unittest.main()
