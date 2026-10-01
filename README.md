# EtPilot

Pipeline de pesquisa em Python para simulação de mobilidade cotidiana,
roteamento multimodal e análise de segregação socioespacial em Porto Alegre.

O branch `EtPilot_v01` está sendo organizado como um pipeline modular,
reprodutível e executável por região.

---

## Ambiente

Crie o ambiente virtual:

```powershell
python -m venv .venv
```

Ative no Windows:

```powershell
.venv\Scripts\activate
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

---

# Execução recomendada — fluxo completo

O ponto de entrada principal agora é:

```powershell
python scripts/run_pipeline.py
```

Esse comando chama, na ordem correta:

```text
preparação das redes
        ↓
preparação da região
        ↓
simulação dos agentes
        ↓
roteamento multimodal
        ↓
uso das arestas
        ↓
plots e outputs
```

A configuração pode ser alterada diretamente pelo terminal sem modificar o
código. Exemplos:

Somente classe de baixa renda:

```powershell
python scripts/run_pipeline.py --income low
```

Duas classes sociais:

```powershell
python scripts/run_pipeline.py --income low middle
```

Todas as classes, período de 3 dias:

```powershell
python scripts/run_pipeline.py --income low middle high --period-value 3 --period-unit days
```

Período de 8 horas:

```powershell
python scripts/run_pipeline.py --period-value 8 --period-unit hours
```

Configuração completa:

```powershell
python scripts/run_pipeline.py --region city --region-mode analysis --income low middle high --period-value 24 --period-unit hours --n-agents 100 --seed 42 --scenario differentiated
```

Para reutilizar redes e cache regional já preparados:

```powershell
python scripts/run_pipeline.py --skip-network-preparation --skip-region-preparation
```

Para limpar outputs antes da rodada:

```powershell
python scripts/run_pipeline.py --clear-outputs
```

As opções territoriais agora seguem as **17 regiões oficiais do Orçamento
Participativo de Porto Alegre**, além de `city` para representar o município
inteiro. A configuração está centralizada em `config/regions.json` e inclui
número da região, rótulo, bairros e referência da fonte oficial.

Chaves disponíveis:

```text
city
humaita_navegantes
noroeste
leste
lomba_do_pinheiro
norte
nordeste
partenon
restinga
gloria
cruzeiro
cristal
centro_sul
extremo_sul
eixo_baltazar
sul
centro
ilhas
```

A regionalização utilizada é a do Orçamento Participativo/ObservaPOA da
Prefeitura de Porto Alegre, cuja espacialização foi alinhada aos bairros
oficiais. A fonte territorial e a observação metodológica ficam registradas
no próprio `regions.json`.

A janela temporal é representada por `SimulationPeriod`. Cada agente recebe
um horário de partida dentro do período configurado; assim, o mesmo modelo
pode trabalhar com janelas em horas ou em dias.

A configuração é armazenada em `PilotRunConfig`, separada da interface.
Por isso o pipeline possui agora **duas inicializações equivalentes**:

### Inicialização 1 — terminal

```powershell
python scripts/run_pipeline.py
```

É a opção mais adequada para execuções reproduzíveis, automação e registro
dos parâmetros usados.

### Inicialização 2 — interface gráfica

```powershell
python scripts/run_pipeline_gui.py
```

A interface usa Tkinter e monta o mesmo `PilotRunConfig` do terminal. Nela
podem ser selecionados região, modo de uso da região, classes sociais,
período, número de agentes, seed, cenário e opções de preparação. A interface
não substitui o terminal; as duas formas continuam disponíveis e executam a
mesma lógica do pipeline.


### Interface gráfica

A GUI usa uma estética inspirada no Windows 95: elementos quadrados, fundo
cinza, barra de título azul-marinho, campos com efeito rebaixado (`sunken`),
botões com relevo e tipografia clássica. A interface possui duas abas:
`Configuração` e `Mapas`, ambas alimentando o mesmo `PilotRunConfig`.



### Aba "Mapas" da interface gráfica

A interface gráfica possui uma segunda aba chamada **Mapas**. Nela aparecem
somente os produtos cartográficos e gráficos aprovados para o piloto. **Apenas
os itens marcados são gerados**. Alguns checkboxes representam um grupo de
arquivos, como um mapa por classe social.

Opções disponíveis:

```text
Rotas OSM dos agentes
Rotas de transporte coletivo
Uso geral das redes
Trechos por modo de viagem
Trechos por classe social
Trechos por modo + classe social
```

Os botões **Selecionar todos** e **Limpar seleção** facilitam a escolha. A
seleção fica registrada em `run_config.json` através do campo
`selected_plots`.

Quando o pipeline é iniciado pelo terminal, todos os mapas continuam
selecionados por padrão.


### Origem e destino em amostras pequenas

Quando a execução possui **menos de 20 agentes**, os mapas de rotas mostram
também os pontos individuais de origem e destino:

```text
X  → origem do agente
○  → destino do agente
```

Os marcadores usam a mesma cor associada à classe de renda do agente. Para
20 agentes ou mais, esses símbolos são omitidos automaticamente para evitar
poluição visual. Essa regra se aplica aos mapas de rotas OSM e de transporte
coletivo.

### Convenção visual dos mapas

Os mapas opcionais de uso da rede seguem uma convenção própria para permitir
leitura simultânea de classe social e modo de deslocamento. Os mapas
obrigatórios possuem regras adicionais descritas na seção específica.

**Cor = classe social**

```text
Baixa renda   → Lavender Gray  #CABAD7
Média renda   → Eggplant       #4F364B
Alta renda    → Cinnabar       #DB3E1D
Fundo         → branco puro      #FFFFFF
```

**Tipo de linha = modo efetivamente utilizado no trecho**

```text
Walk          → linha pontilhada
Bike          → linha tracejada
Carro         → linha contínua
Ônibus        → linha contínua com seta de direção
```

Para viagens de transporte coletivo, os trechos de acesso e egresso a pé são
representados como `walk` e portanto aparecem pontilhados; somente o trecho
em veículo coletivo é representado com linha contínua e seta.

A espessura da linha continua representando a intensidade de uso do trecho
(número relativo de travessias dentro do mapa/painel).


---

# Ordem de execução no terminal

Execute os comandos abaixo a partir da raiz do repositório.

## 1. Atualizar o branch

```powershell
git pull
```

## 2. Verificar os insumos

```powershell
python scripts/check_setup.py
```

Esse comando verifica, entre outros:

- malha de bairros;
- origens;
- destinos;
- produtos GTFS;
- disponibilidade dos GraphML multimodais.

## 3. Preparar as redes OSM da cidade

Na primeira execução, ou quando os GraphML ainda não existirem:

```powershell
python scripts/prepare_city_networks.py
```

São preparadas três redes independentes:

```text
data/graph/rede-poa-car.graphml
data/graph/rede-poa-walk.graphml
data/graph/rede-poa-bike.graphml
```

Para forçar novo download:

```powershell
python scripts/prepare_city_networks.py --force
```

Não é necessário executar novamente esse passo em todas as simulações.

## 4. Limpar outputs anteriores

Opcional, mas recomendado antes de uma nova rodada completa:

```powershell
python scripts/clear_outputs.py
```

O script remove os arquivos de `outputs/`, preservando a estrutura de
diretórios.

## 5. Preparar a região

Para executar inicialmente com todo o município:

```powershell
python scripts/prepare_region.py --region city
```

Essa etapa:

1. constrói a `StudyArea`;
2. filtra origens e destinos;
3. recorta as redes de caminhada, bicicleta e carro;
4. calcula `node_walk`, `node_bike` e `node_car`;
5. filtra os dados GTFS para a mesma região;
6. cria o cache regional;
7. gera plots de diagnóstico.

O cache é salvo em:

```text
cache/regions/<region>/
```

A mesma etapa pode ser executada diretamente para qualquer região do
Orçamento Participativo, por exemplo:

```powershell
python scripts/prepare_region.py --region centro
python scripts/prepare_region.py --region noroeste
python scripts/prepare_region.py --region sul
python scripts/prepare_region.py --region extremo_sul
```

## 6. Executar o piloto multimodal

Execução padrão:

```powershell
python -m src.simulation.run_pilot --region city
```

Execução explícita:

```powershell
python -m src.simulation.run_pilot --region city --n-agents 100 --seed 42 --scenario differentiated
```

Cenários aceitos:

```text
baseline
differentiated
```

O piloto atual executa:

```text
população sintética
        ↓
origem regional
        ↓
propósito da viagem
        ↓
destino regional
        ↓
escolha modal
        ↓
walk / bike / car / transit
        ↓
roteamento
        ↓
diagnósticos e outputs
```

Para `walk`, `bike` e `car`, o caminho é calculado nas redes OSM
específicas de cada modo.

Para `transit`, o pipeline combina:

```text
origem
  ↓
acesso pela rede walk
  ↓
parada GTFS
  ↓
conexões temporais de ônibus
  ↓
parada GTFS
  ↓
egresso pela rede walk
  ↓
destino
```

A data de serviço utilizada pelo piloto é selecionada automaticamente entre
as datas disponíveis no cache GTFS regional, priorizando a data com maior
número de conexões programadas.

---



### Regiões exibidas na interface gráfica

A interface gráfica lê diretamente `config/regions.json`. Atualmente ela
exibe a cidade inteira e as 17 regiões do Orçamento Participativo, na ordem
oficial. O nome mostrado ao usuário vem do próprio catálogo territorial, de
modo que a interface e o terminal usam exatamente as mesmas definições.

## Dois modos de uso da região

A região pode atuar de duas formas diferentes. Essa escolha altera a
interpretação científica da execução e fica registrada em
`run_config.json`.

### 1. `analysis` — região como universo da análise

```powershell
python scripts/run_pipeline.py --region sul --region-mode analysis
```

Nesse caso, a região realmente restringe o piloto:

```text
origens               → somente dentro da região
destinos              → somente dentro da região
agentes               → atribuídos a essas origens regionais
redes car/walk/bike   → recortadas para a região
GTFS                   → filtrado para a região
rotas                  → calculadas usando o recorte regional
mapas                  → mostram esse mesmo universo regional
```

Portanto, selecionar `sul` em `analysis` não significa apenas ampliar ou
recortar a figura. O conjunto de agentes, O/D e infraestrutura disponível na
simulação muda.

### 2. `plot_only` — região apenas como janela espacial

```powershell
python scripts/run_pipeline.py --region sul --region-mode plot_only
```

Nesse caso, a simulação continua municipal:

```text
origens               → Porto Alegre inteira
destinos              → Porto Alegre inteira
agentes               → cidade inteira
redes car/walk/bike   → cidade inteira
GTFS                   → cidade inteira
rotas                  → podem começar, terminar ou passar fora da região
mapas                  → enquadrados somente na região selecionada
```

Esse modo permite responder perguntas como: **quais fluxos da cidade inteira
passam pela região Sul?** Uma rota pode ter origem no Centro, destino na Zona
Norte e ainda aparecer no mapa da Zona Sul se atravessar a janela mostrada.

### Modos de viagem e classes sociais em cada trecho

Nos dois modos regionais o pipeline registra, para cada aresta modal
efetivamente percorrida:

- agente;
- classe social (`low`, `middle`, `high`);
- modo de viagem (`walk`, `bike`, `car`, `transit`);
- tipo de trecho da viagem;
- número de travessias;
- número de agentes distintos.

Além dos CSVs, são produzidos automaticamente dois mapas analíticos:

```text
edge_usage_by_mode.png
edge_usage_by_income.png
edge_usage_by_mode_income.png
```

`edge_usage_by_mode.png` possui painéis separados por modo de viagem e mostra
quais trechos foram utilizados por caminhada, bicicleta, carro e transporte
coletivo. A espessura das linhas cresce com o número de travessias.

`edge_usage_by_income.png` possui painéis separados por classe social e mostra
quais trechos foram utilizados pelos grupos de baixa, média e alta renda,
também com espessura proporcional ao número de travessias.

`edge_usage_by_mode_income.png` cruza as duas dimensões. Cada painel representa
uma combinação entre modo de viagem e classe social, por exemplo
`car | high`, `transit | low` ou `walk | middle`. Esse mapa é o mais
direto para observar quais grupos sociais, usando quais modos, aparecem em
cada trecho da rede.

O arquivo:

```text
edge_composition.csv
```

resume, para cada aresta modal, quais modos de viagem e quais classes sociais
foram observados, além do número de categorias, travessias e agentes.

**Importante:** nesta etapa, "trecho" ainda significa a aresta da rede modal
correspondente. Carro, caminhada, bicicleta e transporte coletivo ainda não
foram consolidados em uma única geometria física comum de rua. Essa
normalização para um segmento físico comum será feita antes do cálculo de
`H_soc`. Portanto, os mapas atuais permitem comparar quem usa os trechos de
cada rede, mas ainda não devem ser interpretados como uma fusão perfeita de
todos os modos sobre a mesma unidade física.

Os outputs dos dois modos regionais são separados:

```text
outputs/pilot/<region>/<region_mode>/<scenario>/seed_<seed>/
```

Tanto `analysis` quanto `plot_only` usam exatamente a mesma geometria
territorial do Orçamento Participativo. A diferença está somente em como esse
recorte entra no experimento: como universo da simulação ou apenas como janela
de visualização.

---

## Sequência cotidiana resumida

Depois que as redes urbanas já estiverem disponíveis, a rotina normal pode ser reduzida a:

```powershell
git pull
python scripts/run_pipeline.py --skip-network-preparation
```

Ou, reutilizando também o cache regional:

```powershell
git pull
python scripts/run_pipeline.py --skip-network-preparation --skip-region-preparation
```

Se as redes `car/walk/bike` ainda não existirem, insira antes do
`prepare_region.py`:

```powershell
python scripts/prepare_city_networks.py
```

---


## Plots selecionáveis

A execução gera **somente** os plots selecionados na aba `Mapas` da GUI
(ou todos eles por padrão quando a execução é iniciada pelo terminal).

As opções são:

1. um mapa para cada modo de viagem, com todas as classes sociais;
2. um mapa por classe social para bike;
3. um mapa por classe social para walk;
4. um mapa por classe social para car;
5. um mapa por classe social para transporte público;
6. setores censitários da região em gradiente de renda;
7. setores censitários + todos os modos, com linhas contínuas e classe por cor;
8. todas as redes de mobilidade em cinza forte;
9. trajetória individual dos agentes, uma cor por agente, somente se `n < 40`;
10. gráfico de barras da frequência de cada modo de viagem por classe social.

Os arquivos selecionados ficam em:

```text
outputs/pilot/<region>/<region_mode>/<scenario>/seed_<seed>/plots/
```

Regras visuais:

- fundo branco puro (`#FFFFFF`);
- redes de base em cinza fraco, exceto no mapa 8;
- baixa renda: `#CABAD7`;
- média renda: `#4F364B`;
- alta renda: `#DB3E1D`;
- quando um mapa mostra apenas um modo, as linhas são contínuas;
- no mapa 7, todos os modos também são contínuos;
- classes sobrepostas podem receber pequeno deslocamento lateral apenas visual;
- a espessura das linhas representa intensidade relativa de travessias;
- com menos de 20 agentes, `X` indica origem e `○` indica destino.

### Workbook das configurações

Toda rodada também gera automaticamente:

```text
configurations_used.xlsx
```

O workbook registra os parâmetros efetivamente usados e os arquivos JSON da
pasta `config/`, cada fonte em uma aba separada:

```text
run_config
config
config_agents
regions
road_classification
resumo_classes
```

As estruturas aninhadas são exportadas como `caminho da configuração ->
valor`. Assim ficam explícitos, entre outros, pesos de propósito, pesos de
escolha modal por classe, decaimento de distância, faixas/participações de
renda, parâmetros de roteamento e definições territoriais.

A aba `resumo_classes` reorganiza os principais parâmetros sociais em uma
tabela comparativa: faixa de renda, participação, pesos de propósito, pesos de
modo nos cenários baseline/differentiated e decaimentos de distância por
propósito.


## Principais outputs

Diagnósticos da preparação regional:

```text
outputs/diagnostics/<region>/
├── 01_regional_data.png
├── 02_origin_snapping.png
└── 03_transit.png
```

Resultados do piloto:

```text
outputs/pilot/<region>/<region_mode>/<scenario>/seed_<seed>/
├── run_config.json
├── agent_choices.csv
├── routing_summary.csv
├── edge_usage.csv
├── edge_usage_summary.csv
├── edge_composition.csv
├── routes_osm.png
├── routes_transit.png
├── edge_usage.png
├── edge_usage_by_mode.png
├── edge_usage_by_income.png
└── edge_usage_by_mode_income.png
```

---

## Estrutura modular atual

```text
src/
├── core/
│   └── config.py
├── domain/
│   ├── agent.py
│   └── enums.py
├── network/
│   └── multimodal.py
├── routing/
│   ├── multimodal_router.py
│   └── pilot_router.py
├── simulation/
│   └── run_pilot.py
├── spatial/
│   ├── filtering.py
│   ├── network_clip.py
│   ├── regional_cache.py
│   ├── regional_data.py
│   ├── regions.py
│   ├── study_area.py
│   └── transit_filter.py
├── transit/
│   ├── data.py
│   ├── regional.py
│   └── router.py
├── trajectory/
│   └── edge_usage.py
└── plot.py
```

A separação segue o princípio de responsabilidade única:

- `spatial`: recortes territoriais;
- `network`: redes modais e snapping;
- `transit`: dados e roteamento temporal GTFS;
- `routing`: orquestração das rotas;
- `simulation`: comportamento dos agentes;
- `trajectory`: transformação das rotas em registros de uso das redes;
- `plot.py`: diagnósticos visuais do estado atual do pipeline.

---

## Diagnósticos visuais

A regra de desenvolvimento deste branch é adicionar uma função ao
`src/plot.py` sempre que uma nova etapa espacial relevante for incorporada.

Atualmente estão disponíveis diagnósticos para:

- área de estudo;
- origens e destinos;
- redes regionais;
- snapping modal;
- transporte coletivo regional;
- rotas OSM dos agentes;
- rotas de transporte coletivo;
- intensidade de uso das arestas;
- uso dos trechos separado por modo de viagem;
- uso dos trechos separado por classe social;
- uso dos trechos cruzando modo de viagem e classe social.

---

## Dados de transporte coletivo

Os produtos GTFS processados utilizados pelo pipeline estão em:

```text
data/gtfs/
```

Entre eles estão paradas, conexões temporais, conectores com a rede de
caminhada, arestas físicas do transporte coletivo e datas de serviço.

O pipeline regional não reprocessa o GTFS a cada execução. Ele filtra os
produtos existentes e salva apenas o subconjunto necessário em
`cache/regions/<region>/`.

---

## Objetivo de pesquisa

O EtPilot serve como base computacional para investigar como padrões de
mobilidade cotidiana e diferenças socioeconômicas se manifestam ao longo da
rede urbana, permitindo posteriormente calcular indicadores espaciais e
espaço-temporais de segregação e diversidade socioeconômica.


---

## Arquivos mantidos no branch

O branch operacional foi limpo para evitar duplicação entre notebooks,
artefatos intermediários e o pipeline em Python. Permanecem versionados os
insumos efetivamente consumidos pela execução atual e pequenos arquivos de
proveniência do GTFS.

Antes da limpeza foi criado o branch de segurança:

```text
EtPilot_v01_pre_prune_20260930
```

Ele preserva o estado anterior caso algum artefato legado precise ser
consultado posteriormente.
