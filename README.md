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
python scripts/run_pipeline.py --region city --income low middle high --period-value 24 --period-unit hours --n-agents 100 --seed 42 --scenario differentiated
```

Para reutilizar redes e cache regional já preparados:

```powershell
python scripts/run_pipeline.py --skip-network-preparation --skip-region-preparation
```

Para limpar outputs antes da rodada:

```powershell
python scripts/run_pipeline.py --clear-outputs
```

As opções territoriais previstas são:

```text
city
center
north
south
east
```

No estado atual, `center`, `north`, `south` e `east` só podem ser
executadas depois que os respectivos bairros forem definidos e habilitados em
`config/regions.json`. O pipeline falha explicitamente caso uma região ainda
não esteja configurada, evitando inventar uma divisão territorial.

A janela temporal é representada por `SimulationPeriod`. Cada agente recebe
um horário de partida dentro do período configurado; assim, o mesmo modelo
pode trabalhar com janelas em horas ou em dias.

A configuração é armazenada em `PilotRunConfig`, separada da interface.
Isso permite que futuramente uma janela gráfica com seletores, caixas de
marcação e menus suspensos monte a mesma configuração sem alterar a lógica do
pipeline.

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

Quando `config/regions.json` estiver preenchido e as regiões estiverem
habilitadas, a mesma etapa poderá ser executada com:

```powershell
python scripts/prepare_region.py --region center
python scripts/prepare_region.py --region north
python scripts/prepare_region.py --region south
python scripts/prepare_region.py --region east
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
outputs/pilot/<region>/<scenario>/seed_<seed>/
├── agent_choices.csv
├── routing_summary.csv
├── edge_usage.csv
├── edge_usage_summary.csv
├── routes_osm.png
├── routes_transit.png
└── edge_usage.png
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
- intensidade de uso das arestas.

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
