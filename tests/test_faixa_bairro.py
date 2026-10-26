import unittest
from unittest.mock import patch

from gerador_rotas.dominio.endereco_texto import (
    cidades_rmbh_para_busca,
    detectar_cidade_rmbh,
    eh_complemento_pos_endereco,
    eh_nome_de_cidade,
    escolher_registro_viacep,
    numero_cabe_na_faixa_viacep,
    separar_componentes_endereco,
)
from gerador_rotas.geo.resolver_endereco import buscar_endereco_completo
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

    def test_avenida_nao_e_o_mesmo_que_beco(self):
        self.assertEqual(similaridade_ruas("Avenida Amazonas", "Beco Amazonas"), 0.0)
        self.assertEqual(similaridade_ruas("Av. Amazonas", "Beco Amazonas"), 0.0)
        self.assertGreater(similaridade_ruas("Av. Amazonas", "Avenida Amazonas"), 0.90)
        self.assertGreater(similaridade_ruas("Amazonas", "Avenida Amazonas"), 0.90)

    def test_nome_da_rua_nao_muda_a_cidade(self):
        rua, numero, bairro, cidade = separar_componentes_endereco(
            "Avenida Amazonas 1044 centro"
        )
        self.assertEqual(numero, "1044")
        self.assertIn("avenida", rua.lower())
        self.assertIn("amazonas", rua.lower())
        self.assertEqual(bairro.lower(), "centro")
        self.assertEqual(cidade, "Belo Horizonte")

    def test_bairro_homonimo_continua_escolhendo_a_cidade(self):
        _, _, bairro, cidade = separar_componentes_endereco(
            "Rua das Flores 10, Amazonas"
        )
        self.assertEqual(bairro.lower(), "amazonas")
        self.assertEqual(cidade, "Contagem")
        _, _, _, cidade_eldorado = separar_componentes_endereco("Rua X 20, Eldorado")
        self.assertEqual(cidade_eldorado, "Contagem")
        self.assertEqual(detectar_cidade_rmbh("Eldorado"), "Contagem")

    def test_bairro_na_linha_seguinte_entra_no_endereco(self):
        rua, numero, bairro, _cidade = separar_componentes_endereco(
            "Rua Bernardo Guimarães 1581, Lourdes"
        )
        self.assertIn("1581", numero)
        self.assertEqual(bairro.lower(), "lourdes")
        self.assertIn("bernardo", rua.lower())

    def test_bairro_escrito_nao_some_quando_e_regional(self):
        _, _, bairro, _ = separar_componentes_endereco(
            "Rua Barão de Coromandel, 830, Barreiro"
        )
        self.assertEqual(bairro.lower(), "barreiro")

    def test_par_e_impar_usam_o_lado_certo_da_faixa(self):
        self.assertTrue(numero_cabe_na_faixa_viacep("390", "até 389/390"))
        self.assertFalse(numero_cabe_na_faixa_viacep("392", "até 389/390"))
        self.assertTrue(numero_cabe_na_faixa_viacep("700", "de 391/392 a 699/700"))
        self.assertFalse(numero_cabe_na_faixa_viacep("390", "de 391/392 a 699/700"))
        self.assertTrue(numero_cabe_na_faixa_viacep("1010", "até 1009/1010"))
        self.assertFalse(numero_cabe_na_faixa_viacep("1012", "até 1009/1010"))
        self.assertTrue(numero_cabe_na_faixa_viacep("1012", "de 1011/1012 ao fim"))
        self.assertFalse(numero_cabe_na_faixa_viacep("1010", "de 1011/1012 ao fim"))

    def test_entregar_na_nao_entra_no_nome_da_rua(self):
        frases = [
            "ENTREGAR NA CONSELHEIRO LAFAIETE 766",
            "Favor entregar na Conselheiro Lafaiete 766",
            "Pode deixar no Conselheiro Lafaiete 766",
            "Endereço: Conselheiro Lafaiete 766",
            "Endereço de entrega: Conselheiro Lafaiete, 766",
        ]
        for frase in frases:
            rua, numero, _, _ = separar_componentes_endereco(frase)
            self.assertEqual(numero, "766", frase)
            self.assertIn("conselheiro", rua.lower(), frase)
            self.assertIn("lafaiete", rua.lower(), frase)
            self.assertNotIn("entreg", rua.lower(), frase)
            self.assertNotRegex(rua.lower(), r"(^|\s)na(\s|$)", frase)

    def test_palavra_entrega_no_meio_do_nome_da_rua_permanece(self):
        rua, numero, bairro, _ = separar_componentes_endereco(
            "Rua da Entrega, 100, Centro"
        )
        self.assertEqual(numero, "100")
        self.assertIn("entrega", rua.lower())
        self.assertEqual(bairro.lower(), "centro")

    def test_avenida_nao_perde_a_primeira_letra(self):
        rua, numero, _, _ = separar_componentes_endereco(
            "Entregar avenida Amazonas 500"
        )
        self.assertEqual(numero, "500")
        self.assertIn("avenida", rua.lower())
        self.assertIn("amazonas", rua.lower())

    def test_cidade_pedida_vem_na_frente_e_o_resto_da_rmbh_entra(self):
        cidades = cidades_rmbh_para_busca("Contagem")
        self.assertEqual(cidades[0], "Contagem")
        self.assertIn("Ibirité", cidades)
        self.assertIn("Vespasiano", cidades)
        self.assertEqual(len(cidades), len(set(cidades)))

    def test_tipo_de_lugar_continua_complemento_e_nome_avulso_nao(self):
        self.assertTrue(eh_complemento_pos_endereco("Jardim Canadá"))
        self.assertTrue(eh_complemento_pos_endereco("ap 202"))
        self.assertFalse(eh_complemento_pos_endereco("Serra"))
        self.assertFalse(eh_complemento_pos_endereco("Camargos"))

    def test_bairro_especifico_ganha_da_regional(self):
        _, _, bairro, _ = separar_componentes_endereco(
            "Rua Águia 381, Miramar, Barreiro"
        )
        self.assertEqual(bairro.lower(), "miramar")


TAUNAY = [
    {"logradouro": "Rua Visconde de Taunay", "bairro": "Santa Mônica", "complemento": "de 1011/1012 ao fim", "cep": "31520-370", "localidade": "Belo Horizonte"},
    {"logradouro": "Rua Visconde de Taunay", "bairro": "São Lucas", "complemento": "", "cep": "30240-300", "localidade": "Belo Horizonte"},
    {"logradouro": "Rua Visconde de Taunay", "bairro": "Santa Mônica", "complemento": "até 1009/1010", "cep": "31525-020", "localidade": "Belo Horizonte"},
]

COROMANDEL = [
    {"logradouro": "Rua Barão de Coromandel", "bairro": "Barreiro", "complemento": "", "cep": "30640-060", "localidade": "Belo Horizonte"},
    {"logradouro": "Rua Barão de Coromandel", "bairro": "São Tomáz", "complemento": "", "cep": "31741-085", "localidade": "Belo Horizonte"},
    {"logradouro": "Rua Barão de Coromandel", "bairro": "Caiçaras", "complemento": "", "cep": "30775-560", "localidade": "Belo Horizonte"},
]


class EscolhaDeBairroViaCepTest(unittest.TestCase):
    def test_bairro_escrito_ganha_mesmo_sem_faixa(self):
        decisao = escolher_registro_viacep(TAUNAY, "260", "São lucas")
        self.assertTrue(decisao["bairro_travado"])
        self.assertEqual(decisao["escolhido"]["bairro"], "São Lucas")
        self.assertEqual(decisao["escolhido"]["cep"], "30240-300")
        self.assertEqual(decisao["opcoes"], [])

    def test_sem_dica_mostra_os_dois_bairros_e_descarta_faixa_que_nao_contem(self):
        decisao = escolher_registro_viacep(TAUNAY, "260", "")
        nomes = [item["bairro"] for item in decisao["opcoes"]]
        self.assertIsNone(decisao["escolhido"])
        self.assertIn("São Lucas", nomes)
        self.assertIn("Santa Mônica", nomes)
        self.assertEqual(len(nomes), 2)

    def test_barreiro_entra_na_lista_quando_a_rua_tem_varios_bairros(self):
        decisao = escolher_registro_viacep(COROMANDEL, "830", "")
        nomes = [item["bairro"] for item in decisao["opcoes"]]
        self.assertIn("Barreiro", nomes)
        self.assertIn("Caiçaras", nomes)
        self.assertIn("São Tomáz", nomes)

    def test_bairro_escrito_na_faixa_que_contem_o_numero_trava(self):
        decisao = escolher_registro_viacep(TAUNAY, "260", "Santa Mônica")
        self.assertTrue(decisao["bairro_travado"])
        self.assertEqual(decisao["escolhido"]["cep"], "31525-020")

    def test_bairro_escrito_fora_de_toda_faixa_nao_trava_outro_cep(self):
        registros = [
            {"logradouro": "Rua Visconde de Taunay", "bairro": "Santa Mônica", "complemento": "de 1000/1001 ao fim", "cep": "31520-370", "localidade": "Belo Horizonte"},
            {"logradouro": "Rua Visconde de Taunay", "bairro": "São Lucas", "complemento": "até 999/1000", "cep": "30240-300", "localidade": "Belo Horizonte"},
        ]
        decisao = escolher_registro_viacep(registros, "260", "Santa Mônica")
        self.assertFalse(decisao["bairro_travado"])
        self.assertIsNone(decisao["escolhido"])
        nomes = [item["bairro"] for item in decisao["opcoes"]]
        self.assertIn("Santa Mônica", nomes)
        self.assertIn("São Lucas", nomes)

    def test_um_bairro_so_mesmo_sendo_regional_e_o_escolhido(self):
        registros = [{
            "logradouro": "Rua Carmelita Índia do Brasil",
            "bairro": "Barreiro",
            "complemento": "",
            "cep": "30640-540",
            "localidade": "Belo Horizonte",
        }]
        decisao = escolher_registro_viacep(registros, "400", "")
        self.assertEqual(decisao["escolhido"]["cep"], "30640-540")
        self.assertEqual(decisao["opcoes"], [])


class AvenidaAmazonasTest(unittest.TestCase):
    def setUp(self):
        buscar_endereco_completo.clear()

    def test_1044_centro_permanece_avenida_em_belo_horizonte(self):
        def via(_rua, _sem, cidade):
            if cidade == "Contagem":
                return [{
                    "logradouro": "Beco Amazonas",
                    "bairro": "Jardim Marrocos",
                    "cep": "32040-207",
                    "localidade": "Contagem",
                    "complemento": "",
                }]
            if cidade == "Belo Horizonte":
                return [
                    {
                        "logradouro": "Avenida Amazonas",
                        "bairro": "Centro",
                        "cep": "30180-006",
                        "localidade": "Belo Horizonte",
                        "complemento": "de 562 a 1200 - lado par",
                    },
                    {
                        "logradouro": "Avenida Amazonas",
                        "bairro": "Barro Preto",
                        "cep": "30180-003",
                        "localidade": "Belo Horizonte",
                        "complemento": "de 1202 a 1780 - lado par",
                    },
                ]
            return []

        def cep(numero):
            digitos = "".join(ch for ch in str(numero) if ch.isdigit())
            if digitos == "30180006":
                return {
                    "logradouro": "Avenida Amazonas",
                    "bairro": "Centro",
                    "localidade": "Belo Horizonte",
                    "cep": "30180-006",
                }
            return {}

        with patch("gerador_rotas.geo.resolver_endereco.consultar_viacep_com_tolerancia", side_effect=via), \
             patch("gerador_rotas.geo.resolver_endereco.buscar_candidatos_multifonte", return_value=[]), \
             patch("gerador_rotas.geo.resolver_endereco.consultar_cep_direto", side_effect=cep), \
             patch("gerador_rotas.geo.resolver_endereco.geocodificar_endereco_rua", return_value=(-19.92, -43.94)):
            endereco, status, _lat, _lon, _opcoes = buscar_endereco_completo(
                "Avenida Amazonas 1044 centro"
            )

        self.assertIn("Avenida Amazonas", endereco)
        self.assertIn("1044", endereco)
        self.assertIn("Centro", endereco)
        self.assertIn("Belo Horizonte", endereco)
        self.assertIn("30180-006", endereco)
        self.assertNotIn("Beco", endereco)
        self.assertNotIn("Contagem", endereco)
        self.assertNotIn("Marrocos", endereco)
        self.assertTrue(status.startswith("✅"), status)

    def test_bairro_escrito_nao_vira_o_unico_bairro_de_outra_cidade(self):
        def via(_rua, _sem, cidade):
            if cidade == "Contagem":
                return [{
                    "logradouro": "Avenida Amazonas",
                    "bairro": "Jardim Marrocos",
                    "cep": "32040-207",
                    "localidade": "Contagem",
                    "complemento": "",
                }]
            return []

        with patch("gerador_rotas.geo.resolver_endereco.consultar_viacep_com_tolerancia", side_effect=via), \
             patch("gerador_rotas.geo.resolver_endereco.buscar_candidatos_multifonte", return_value=[]), \
             patch("gerador_rotas.geo.resolver_endereco.consultar_cep_direto", return_value={}), \
             patch("gerador_rotas.geo.resolver_endereco.geocodificar_endereco_rua", return_value=(None, None)), \
             patch("gerador_rotas.geo.resolver_endereco.buscar_coordenada_bairro", return_value=(False, "", None, None)):
            endereco, _status, _lat, _lon, _opcoes = buscar_endereco_completo(
                "Avenida Amazonas 1044, Centro"
            )

        self.assertIn("Centro", endereco)
        self.assertIn("Avenida", endereco)
        self.assertNotIn("Marrocos", endereco)
        self.assertNotIn("Contagem", endereco)


if __name__ == "__main__":
    unittest.main()
