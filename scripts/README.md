# Ordem de execução — EtPilot_v01

## Preparação inicial

Execute os comandos a partir da raiz do repositório.

1. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

2. Verifique os insumos disponíveis:

   ```bash
   python scripts/check_setup.py
   ```

3. Limpe resultados de execuções anteriores, quando necessário:

   ```bash
   python scripts/clear_outputs.py
   ```

4. Prepare as três redes OSM da cidade:

   ```bash
   python scripts/prepare_city_networks.py
   ```

   São produzidas ou reutilizadas:

   - `data/graph/rede-poa-car.graphml`
   - `data/graph/rede-poa-walk.graphml`
   - `data/graph/rede-poa-bike.graphml`

   Use `--force` somente para baixar novamente:

   ```bash
   python scripts/prepare_city_networks.py --force
   ```

5. Prepare a região escolhida:

   ```bash
   python scripts/prepare_region.py --region city
   ```

   Quando as listas de bairros forem preenchidas e habilitadas em
   `config/regions.json`, também será possível executar:

   ```bash
   python scripts/prepare_region.py --region center
   python scripts/prepare_region.py --region north
   python scripts/prepare_region.py --region south
   python scripts/prepare_region.py --region east
   ```

   Esta etapa:

   - constrói a `StudyArea`;
   - filtra origens e destinos;
   - recorta as redes car/walk/bike;
   - calcula `node_car`, `node_walk` e `node_bike`;
   - filtra o transporte coletivo;
   - salva o cache regional;
   - gera plots de diagnóstico.

6. Execute o piloto regional:

   ```bash
   python -m src.simulation.run_pilot --region city
   ```

   O piloto agora consome diretamente o cache criado por
   `prepare_region.py`, preserva `node_walk`, `node_bike` e `node_car`
   e já calcula rotas OSM para caminhada, bicicleta e carro.

   Também é possível controlar população, seed e cenário:

   ```bash
   python -m src.simulation.run_pilot --region city --n-agents 100 --seed 42 --scenario differentiated
   ```

   O modo transit participa da escolha modal e já usa roteamento temporal
   GTFS com acesso e egresso pela rede de caminhada. A data representativa de
   serviço é selecionada automaticamente a partir do cache regional.

## Execução cotidiana

Depois que os dados básicos e as redes da cidade já existem, a sequência
normal deve ser:

```bash
python scripts/clear_outputs.py
python scripts/check_setup.py
python scripts/prepare_region.py --region city
python -m src.simulation.run_pilot --region city
```

Não é necessário baixar novamente as redes OSM nem reprocessar o GTFS em
todas as execuções.

## Transporte coletivo

Os produtos GTFS processados já estão em `data/gtfs/`. Portanto, neste
branch, `prepare_region.py` apenas carrega, valida e filtra esses produtos
para a região escolhida.

## Diagnósticos visuais

Os plots são gerados por funções de `src/plot.py`. A regra do projeto é
adicionar uma nova função de diagnóstico visual sempre que uma nova etapa
espacial relevante for incorporada ao pipeline.

Atualmente existem visualizações para:

- área de estudo;
- origens e destinos;
- redes modais;
- estado regional integrado;
- snapping modal;
- transporte coletivo.
