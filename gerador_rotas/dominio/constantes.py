import re

ARQUIVO_CONFIG = "config_rotas.json"
NOMES_ARQUIVO_MODELO = ["Etiqueta.pdf", "etiqueta.pdf", "Modelo Etiqueta.pdf", "modelo_etiqueta.pdf"]

CIDADES_RMBH = [
    "belo horizonte", "sabara", "nova lima", "contagem", "betim",
    "santa luzia", "ribeirao das neves", "ibirite", "vespasiano",
    "lagoa santa", "pedro leopoldo", "brumadinho", "caete", "sarzedo",
    "mario campos", "sao jose da lapa", "confins", "esmeraldas", "raposos"
]

MAPA_NOMES_CIDADES = {
    "belo horizonte": "Belo Horizonte",
    "sabara": "Sabará",
    "nova lima": "Nova Lima",
    "contagem": "Contagem",
    "betim": "Betim",
    "santa luzia": "Santa Luzia",
    "ribeirao das neves": "Ribeirão das Neves",
    "ibirite": "Ibirité",
    "vespasiano": "Vespasiano",
    "lagoa santa": "Lagoa Santa",
    "pedro leopoldo": "Pedro Leopoldo",
    "brumadinho": "Brumadinho",
    "caete": "Caeté",
    "sarzedo": "Sarzedo",
    "mario campos": "Mário Campos",
    "sao jose da lapa": "São José da Lapa",
    "confins": "Confins",
    "esmeraldas": "Esmeraldas",
    "raposos": "Raposos"
}

MAPA_BAIRROS_RMBH = {
    "vila da serra": "Nova Lima",
    "vale do sereno": "Nova Lima",
    "jardim canada": "Nova Lima",
    "alphaville": "Nova Lima",
    "vila castela": "Nova Lima",
    "vale dos cristais": "Nova Lima",
    "bosque da ribeira": "Nova Lima",
    "ouro velho": "Nova Lima",
    "eldorado": "Contagem",
    "novo eldorado": "Contagem",
    "parque sao joao": "Contagem",
    "jardim riacho": "Contagem",
    "riacho das pedras": "Contagem",
    "inconfidentes": "Contagem",
    "cidade industrial": "Contagem",
    "jardim industrial": "Contagem",
    "industrial": "Contagem",
    "agua branca": "Contagem",
    "nacional": "Contagem",
    "cabral": "Contagem",
    "kennedy": "Contagem",
    "ressaca": "Contagem",
    "amazonas": "Contagem",
    "alterosas": "Betim",
    "jardim alterosas": "Betim",
    "angola": "Betim",
    "filadelfia": "Betim",
    "ptb": "Betim",
    "citrolandia": "Betim",
    "sao benedito": "Santa Luzia",
    "palmital": "Santa Luzia",
    "conjunto cristina": "Santa Luzia",
    "justinopolis": "Ribeirão das Neves",
    "veneza": "Ribeirão das Neves",
    "sevilha": "Ribeirão das Neves",
    "nacoes unidas": "Sabará",
    "general carneiro": "Sabará",
    "roca grande": "Sabará",
}



REGIONAIS_BH = {
    "centro-sul", "centro sul", "noroeste", "nordeste", "norte",
    "leste", "oeste", "pampulha", "venda nova", "barreiro"
}

PREFIXOS_RUA = (
    "rua ", "r. ", "r.", "r ", "av ", "av. ", "av.", "avenida ", "alameda ", "al. ", "al.",
    "praca ", "praça ", "travessa ", "tv. ", "tv.", "beco ", "rodovia ", "estrada ", "anel "
)

TITULOS_E_STOPWORDS_RUA = {
    "rua", "r", "avenida", "av", "alameda", "al", "praca", "travessa", "tv",
    "beco", "rodovia", "estrada", "anel", "de", "da", "do", "dos", "das", "e",
    "doutor", "dr", "dra", "professor", "prof", "profa", "presidente", "pres",
    "coronel", "cel", "general", "gen", "padre", "pe", "deputado", "dep",
    "senador", "sen", "governador", "gov", "engenheiro", "eng", "desembargador",
    "des", "dom", "dona", "conde", "visconde", "barao", "marques", "prefeito"
}

PALAVRAS_GENERICAS_BAIRRO = {
    "bairro", "vila", "jardim", "parque", "conjunto", "conj", "residencial",
    "condominio", "santa", "santo", "sao", "nossa", "senhora", "de", "da", "do", "dos", "das"
}

PALAVRAS_NAO_ENDERECO = (
    "pacote", "pct", "pedido", "ped", "item", "itens", "kit", "combo",
    "sacola", "parte", "caixa", "obs", "observacao", "total", "valor",
    "frete", "taxa", "troco", "pix", "pagamento", "cliente", "nome"
)

STOPWORDS_PRODUTOS = {"de", "do", "da", "dos", "das", "com", "sem", "e", "ou", "a", "o", "un", "pct", "gr", "kg", "ml", "totais", "total"}

CORES_ROTAS = ["#e63946", "#2a9d8f", "#3a86ff", "#ff9f1c"]

REGEX_CABECALHO_CHAT = re.compile(
    r"^\s*\[?\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*[,\-]?\s*\d{1,2}:\d{2}(?::\d{2})?\]?\s*(?:-\s*)?[^:\n]{1,35}:\s*(.*)$"
)
