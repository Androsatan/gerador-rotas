# Arquitetura do gerador de rotas

Aplicação Streamlit para a região metropolitana de Belo Horizonte. O utilizador cola pedidos, o sistema localiza os endereços, divide as entregas em rotas com cota fixa e gera etiquetas 10×15 cm.

O `app.py` na raiz só abre a tela. Regra de negócio, mapas e PDF ficam no pacote `gerador_rotas/`.

## 1. Árvore

```text
gerador-rotas/
  app.py                         # entrada Streamlit
  requirements.txt               # streamlit, pandas, requests, pypdf, reportlab, ortools
  config_rotas.json              # ponto de partida e produtos dos 4 locais (criado ao salvar)
  ARQUITETURA.md
  README.md
  gerador_rotas/
    config_io.py                 # lê e grava config_rotas.json
    estado.py                    # session_state e listas de pedidos/etiquetas
    dominio/
      constantes.py              # cidades da RMBH, prefixos de rua, stopwords, cores
      similaridade.py            # acentos e comparação de rua, bairro e produto
      endereco_texto.py          # separar rua, número, bairro e cidade; classificar linhas
      produtos.py                # item do pedido -> Local 1–4 e quantidade de pacotes
      parser_pedidos.py          # texto colado -> um pedido por endereço; vários nomes ficam no primeiro
    geo/
      cep.py                     # ViaCEP, BrasilAPI e OpenCEP
      bairro.py                  # achar o bairro pelo nome, sem coordenada gravada
      geocodificadores.py        # ArcGIS, Photon, Nominatim e cache da partida
      resolver_endereco.py       # orquestra a busca do endereço do cliente
      partida.py                 # valida bairro, rua ou CEP de saída
    rotas/
      matriz.py                  # duração e distância (OSRM ou estimativa)
      planejador.py              # OR-Tools: cota fixa, rota aberta, PRIMEIRO/ÚLTIMO
    etiquetas/
      parser.py                  # texto da rota ou tabela calculada -> linhas de etiqueta
      pdf.py                     # PDF único 10×15 cm sobre Etiqueta.pdf
    ui/
      tema.py                    # CSS
      auth.py                    # senha de acesso
      sidebar.py                 # partida (ícone ou aviso), locais de produto e gravação do JSON
      mapa.py                    # Leaflet com o traçado da rua
      pagina_rotas.py            # passos 1 a 4 do gerador
      pagina_etiquetas.py        # seleção e download do PDF
  tests/
    test_bairro.py               # bairro certo, rua homónima e falha parcial das fontes
    test_parser_pedidos.py       # vários nomes no mesmo endereço viram um pedido
    test_etiquetas_endereco.py   # etiqueta usa o endereço completo quando a busca confirma
    test_planejador.py           # cota, ordem aberta, PRIMEIRO e ÚLTIMO
```

`__pycache__/` é gerado pelo Python e não faz parte do desenho.

## 2. Responsabilidade de cada pasta

### `ui/`

Só desenha e reage a cliques. Não decide ordem de entrega nem escolhe coordenada.

| Ficheiro | Função |
|---|---|
| `tema.py` | CSS dos botões. Em ecrã estreito, as colunas da área principal empilham; as da sidebar não, para o ícone da partida ficar ao lado do campo |
| `auth.py` | `exigir_login()`: bloqueia a app até a senha |
| `sidebar.py` | Campo de partida, quatro locais de produto e gravação do JSON. Com o texto igual ao JSON, só mostra ✅ ou ❌ ao lado do campo. A frase completa de partida localizada ou não localizada aparece só depois de o texto mudar, e nesse caso o ícone sai |
| `pagina_rotas.py` | Colar pedidos, conferir, definir cotas, gerar, ajustar rota e copiar o texto |
| `pagina_etiquetas.py` | Marcar, editar e baixar o PDF |
| `mapa.py` | Pinos numerados e a linha colorida de cada rota |

### `dominio/`

Texto e regras que não dependem de internet nem de Streamlit, salvo o parser, que chama a geocodificação.

| Ficheiro | Função |
|---|---|
| `constantes.py` | Lista de cidades, mapa de bairros da RMBH, prefixos de via, palavras que não são endereço |
| `similaridade.py` | Normaliza acento e mede se duas ruas, dois bairros ou dois produtos são o mesmo |
| `endereco_texto.py` | Decide se uma linha é endereço, produto, complemento ou nome. Separa rua, número, bairro e cidade. `dentro_perimetro_rmbh` limita o resultado a BH e arredores |
| `produtos.py` | Compara os itens colados com os produtos cadastrados e devolve quais locais (1 a 4) entram no pedido. Isso só muda a contagem de pacotes |
| `parser_pedidos.py` | Parte o texto colado em pedidos, resolve os endereços em paralelo e monta a linha `NOME [VENDEDOR] (NPCT)`. Vários nomes no mesmo endereço viram um pedido só, com o primeiro nome e todos os itens |

### `geo/`

Tudo o que transforma texto de lugar em latitude e longitude.

| Ficheiro | Função |
|---|---|
| `cep.py` | Consulta CEP direto e busca de logradouro no ViaCEP com tolerância de grafia |
| `bairro.py` | Consulta ArcGIS, Photon e Nominatim em paralelo. Aceita o candidato só se o nome bater e o tipo for bairro, não rua. «Não encontrado» só vale quando as três fontes responderam |
| `geocodificadores.py` | Cache do bairro, geocodificação simples de uma rua e lista de candidatos de várias fontes |
| `resolver_endereco.py` | Junta ViaCEP e as outras fontes até devolver endereço padronizado, status, lat, lon e bairros ambíguos |
| `partida.py` | Entrada da sidebar: CEP, rua com número, ou nome de bairro |

Não existe tabela de coordenadas fixas. Se nenhuma fonte confirmar o lugar, a função devolve `None`. O centro de Belo Horizonte não é usado como substituto.

### `rotas/`

| Ficheiro | Função |
|---|---|
| `matriz.py` | Pede ao OSRM público a matriz de duração e distância de carro. Se o serviço falhar, estima com haversine × 1,35. Também pede a geometria da rua |
| `planejador.py` | Divide as paradas pelas cotas e ordena cada rota até o último cliente |

`gerar_rotas` faz a divisão e a ordem. `recalcular_todas_as_rotas` só reordena: o utilizador mudou a coluna Rota ou Posição, ou mudou o ponto de partida. Essa segunda função não redistribui a quantidade entre entregadores.

### `etiquetas/`

| Ficheiro | Função |
|---|---|
| `parser.py` | Converte a tabela de rotas, ou um texto colado no mesmo formato, em linhas de etiqueta. Rua sem CEP é marcada para a mesma busca de endereço completo das rotas |
| `pdf.py` | Procura `Etiqueta.pdf` na raiz do repositório e desenha nome e endereço em cada página 10×15 cm |

### Ficheiros ao lado do pacote

| Ficheiro | Função |
|---|---|
| `app.py` | `set_page_config`, tema, login, estado, sidebar e o botão que troca entre Rotas e Etiquetas |
| `config_io.py` | `carregar_config` / `salvar_config` |
| `estado.py` | Cria as chaves do `st.session_state` e impede pedido duplicado (mesmo cliente e mesma rua/número) |

## 3. Fluxo, do clique até o PDF

A geocodificação do cliente acontece antes do botão de gerar. O botão usa latitude e longitude que já estão na tabela.

### Antes do clique

1. `app.py` chama `exigir_login`, `iniciar_estado` e `render_sidebar`.
2. A sidebar lê `config_rotas.json` e chama `validar_e_geocodificar_partida`.
   - CEP de 8 dígitos vai a `cep.py` e depois a `geocodificar_endereco_rua`.
   - Texto com prefixo de rua ou número vai a `buscar_endereco_completo`.
   - Nome de bairro vai a `buscar_coordenada_bairro` → `localizar_bairro`.
   - O campo fica na chave `campo_ponto_partida`. Se o texto for o do JSON, a sidebar desenha só ✅ ou ❌. Se o utilizador alterar o texto, o ícone some e entra o aviso com o nome encontrado ou o motivo da falha.
3. O utilizador cola o texto e carrega em **Adicionar à Lista**.
4. `listar_pre_pedidos` parte o texto em blocos. Sem cabeçalho de WhatsApp, um endereço no topo seguido de nomes e itens é um bloco só: a continuação sem endereço volta para o bloco do endereço. Dentro do bloco, o cliente é o primeiro nome; os nomes seguintes não abrem pedido novo e os itens deles entram no mesmo pedido. Dois endereços diferentes continuam dois pedidos. `extrair_pedidos_brutos` geocodifica essa lista.
5. `identificar_locais_dos_itens` marca os locais de produto e a quantidade de pacotes. Esses locais não viram parada.
6. `resolver_enderecos_em_paralelo` chama `buscar_endereco_completo` para cada endereço único (até 12 em paralelo).
7. Cada linha da tabela fica com `Endereco`, `Status`, `Lat`, `Lon` e, se a rua existir em mais de um bairro, `Opcoes_Endereco`.
8. Endereço sem coordenada confiável permanece na lista com aviso. Não recebe o centro da cidade.

### Clique em Gerar e Otimizar Rotas

O botão está em `ui/pagina_rotas.py`. Só habilita se a soma das cotas for igual ao número de pedidos e a partida tiver coordenada.

1. A página chama `gerar_rotas(df, nomes, cotas, lat_partida, lon_partida)` em `rotas/planejador.py`.
2. Pedidos sem `Lat`/`Lon` ficam de fora da matriz. No fim são encaixados nas rotas que ainda têm vaga e aparecem no final da sequência, com um aviso.
3. `matriz.obter_matriz_osrm` monta a tabela de segundos e metros entre a partida e as paradas geocodificadas.
   - Serviço: `http://router.project-osrm.org`, perfil `driving`.
   - Falha total: aviso na tela e matriz estimada.
   - Falha de um trecho: esse trecho é estimado (`fonte` `osrm-parcial`).
4. `atribuir_paradas` entrega a matriz ao OR-Tools.
   - Um veículo por rota. A capacidade do veículo é a cota digitada (número de endereços).
   - Cada parada tem demanda 1.
   - A volta à partida custa 0, então o solver comporta-se como rota aberta: o último ponto é um cliente.
   - Se o solver não fechar, o plano B reparte os pontos por ângulo em volta da partida e a tela avisa.
5. Cada grupo passa por `ordenar_paradas`, de novo com rota aberta:
   - Até 16 paradas sem PRIMEIRO/ÚLTIMO: caminho exato (Held-Karp) a partir da partida.
   - Com PRIMEIRO ou ÚLTIMO e até 9 paradas: testa as permutações que respeitam a ordem.
   - Grupos maiores: OR-Tools com as mesmas restrições. Se falhar, ordena os blocos em cadeia (primeiro, normal, último).
6. `obter_geometria_osrm` pede o desenho da rua (`/route`, GeoJSON). Se não vier, o mapa liga os pinos em linha reta e a tela avisa.
7. O resultado volta para o `session_state`:
   - `df_rotas_calculadas` / `df_rotas_editadas`: colunas `Rota` e `Ordem`
   - `resumo_km_rotas`
   - `geometrias_rotas`
   - `avisos_rotas`
   - `coord_partida_atual`

### Depois de gerar

- Mudar **Rota** ou **Posição** na tabela chama `recalcular_todas_as_rotas`. A quantidade de cada entregador fica como o utilizador deixou. Só a ordem e o traçado são refeitos.
- Mudar o ponto de partida na sidebar, com rotas já calculadas, também só reordena.
- `ui/mapa.py` desenha a casa na coordenada da partida, os pinos na ordem e a polilinha de `geometrias_rotas`.

### Do texto da rota ao PDF

1. **Gerar Etiquetas das Rotas Criadas** chama `importar_etiquetas_das_rotas_calculadas`.
2. `estado.atualizar_base_etiquetas` guarda a tabela e `app.py` muda para o módulo de etiquetas.
3. Também dá para colar o texto exportado: `extrair_etiquetas_de_texto_rota` lê pares de endereço e nome debaixo de um título `ROTA ...`. Endereço sem CEP passa por `buscar_endereco_completo`, a mesma função das rotas, para a etiqueta não ficar só com a rua.
4. **Adicionar Cliente Avulso** também chama `buscar_endereco_completo`. Se a busca confirmar, a tabela guarda o endereço padronizado (rua, número, bairro, cidade e CEP). Se falhar, entra o texto digitado. Se a rua existir em mais de um bairro, a etiqueta guarda `Opcoes_Endereco` e a tela avisa, com a mesma escolha de bairro das rotas. Confirmar grava o endereço escolhido e tira o aviso.
5. `gerar_pdf_etiquetas_10x15` abre `Etiqueta.pdf` na raiz, escreve destinatário e endereço e devolve um único PDF para download.

## 4. O que é fundamental para mexer no projeto

### Contrato do planejador

Quem alterar a tela deve continuar a chamar estas duas funções:

```python
gerar_rotas(df, nomes, cotas, lat, lon) -> (df, km_por_rota, coord, geometrias, avisos)
recalcular_todas_as_rotas(df, nomes, lat, lon) -> (df, km_por_rota, coord, geometrias, avisos)
```

`gerar_rotas` obedece a cota. `recalcular_todas_as_rotas` não mexe na distribuição, só na sequência.

A rota é aberta: o custo de voltar à partida é zero de propósito, e a ordem devolvida não inclui o regresso. O último elemento de cada rota é um cliente.

### O que a cota é

A cota é o número de endereços de cada entregador, escolhido na tela (1 a 4 rotas, com o número editável). A soma tem de fechar com o total de pedidos. O otimizador não reequilibra essa escolha para encurtar quilómetros.

### O que os locais de produto são

Local 1 a 4 classificam itens e contam pacotes. A moto sai só do ponto de partida e visita clientes. Não há parada de coleta nesses locais.

### Coordenadas

- Bairro de partida: `geo/bairro.py`. Rejeita rua homónima (por exemplo a Rua Santa Maria Goretti, no Barreiro) e exige que o nome devolvido corresponda ao texto digitado. Se alguma das três fontes não responder, o resultado é falha de rede, não «bairro inexistente».
- Endereço de cliente: `geo/resolver_endereco.py`.
- Perímetro aceite: latitude de -20,40 a -19,40 e longitude de -44,60 a -43,40.
- Falha de geocodificação: `lat`/`lon` ficam vazios e o status deixa de ser `✅ OK`. Não usar `-19.9167, -43.9345` como fallback.
- Maria Goretti, quando o texto é o bairro, fica em torno de `-19.863, -43.909`, na regional Nordeste. Um pino perto de Cidade Nova (`-19.881, -43.918`) significa que a coordenada fixa antiga voltou.

### Serviços externos

| Uso | Serviço |
|---|---|
| CEP e logradouro | BrasilAPI, OpenCEP, ViaCEP |
| Bairro e rua | ArcGIS, Photon, Nominatim |
| Tempo, distância e traçado | OSRM público, perfil `driving` |

As funções de rede em `geo/` usam `@st.cache_data` (em geral 24 h). Na busca de bairro, falha de rede e consulta incompleta não ficam em cache. «Não encontrado» só é gravado quando ArcGIS, Photon e Nominatim responderam e nenhum nome bateu. A primeira consulta de um bairro pode levar alguns segundos.

O OSRM público é demonstração: pode limitar ou cair. A tela tem de continuar a mostrar o aviso quando a fonte da matriz não for `osrm`.

### Estado da sessão

Chaves principais em `estado.py`: `df_pedidos`, `df_pedidos_editados`, `df_rotas_calculadas`, `df_rotas_editadas`, `nomes_rotas_ativas`, `resumo_km_rotas`, `geometrias_rotas`, `avisos_rotas`, `coord_partida_atual`, `df_etiquetas`. A sidebar também guarda `campo_ponto_partida`. Tudo vive na memória do processo Streamlit. Reiniciar o servidor limpa as listas; o JSON só guarda partida e produtos.

### Onde não colocar código novo

- Cálculo de rota, HTTP e leitura de pedido não voltam para `app.py`.
- A UI não importa detalhes do OR-Tools. Ela chama `gerar_rotas` e `recalcular_todas_as_rotas`.
- Testes de ordem, de bairro e de leitura de pedido não precisam de Streamlit nem de rede: `tests/test_planejador.py`, `tests/test_bairro.py` e `tests/test_parser_pedidos.py`. O parser é coberto por `listar_pre_pedidos`, antes da geocodificação.

```text
python -m unittest tests.test_planejador tests.test_bairro tests.test_parser_pedidos tests.test_etiquetas_endereco
```

### Dependências de sentido único

`ui` → `rotas`, `geo`, `dominio`, `etiquetas`, `estado`  
`rotas` → `matriz` (e OR-Tools / pandas)  
`geo` → `dominio`  
`dominio/parser_pedidos.py` → `geo` (é o único ponto do domínio que sai à rede)  
`etiquetas` → `dominio`

Evitar o caminho inverso. Em particular, `geo` e `rotas` não importam `ui`.
