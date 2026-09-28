# Article v02

A versão v02 preserva a análise anterior e acrescenta um pacote visual focado
em trajetórias, classes sociais e modos de transporte.

A v01 continua disponível em:

```text
src/analysis/article_v01.py
outputs/v01 artigo/
```

A v02 é gerada por:

```bash
python -m src.analysis.article_v02
```

O comando **não reroda as simulações por padrão**. Ele usa todas as realizações
nominais já disponíveis em `outputs/pilot/final_sensitivity/`.

Se ainda não houver resultados nominais, ou se você quiser completar o núcleo
de cinco seeds antes de gerar as figuras:

```bash
python -m src.analysis.article_v02 --run-core-if-missing --min-nominal-seeds 5
```

Para produzir imagens imediatamente com as realizações que já existem:

```bash
python -m src.analysis.article_v02 --min-nominal-seeds 1
```

## Estrutura

```text
outputs/v02 artigo/
├── 00_manifesto_v02.json
├── 01_bases/
│   ├── base04_fluxo_segmento_classe.csv
│   ├── base04_fluxo_segmento_classe.gpkg
│   ├── base05_fluxo_segmento_classe_modo.csv
│   ├── base05_fluxo_segmento_classe_modo.gpkg
│   ├── base06_mudanca_comportamental_agente.csv
│   └── base07_segmentos_rotas_seed_referencia.gpkg
├── 02_estatisticas/
│   ├── participacao_modal_observada_por_classe.csv
│   └── mudancas_comportamentais_por_seed_classe.csv
├── 03_figuras/
│   ├── rotas_por_classe/
│   │   ├── v02_rotas_low_proxy_diaria.png
│   │   ├── v02_rotas_middle_proxy_diaria.png
│   │   └── v02_rotas_high_proxy_diaria.png
│   ├── atlas_modo_classe/
│   │   └── 12 mapas classe × modo
│   ├── v02_rotas_todas_classes_proxy_diaria.png
│   ├── v02_fluxo_low_proxy_diaria.png
│   ├── v02_fluxo_middle_proxy_diaria.png
│   ├── v02_fluxo_high_proxy_diaria.png
│   ├── v02_mapa_dominancia_classe.png
│   ├── v02_comportamento_modal_baseline_vs_classe.png
│   ├── v02_taxa_mudanca_comportamental_por_classe.png
│   ├── v02_sobreposicao_rotas_por_classe.png
│   ├── v02_painel_modo_x_classe.png
│   └── manifesto_figuras_v02.csv
├── 04_mapas/
│   └── v02_dominancia_classe.gpkg
└── 05_relatorio/
    └── leitura_visual_v02.md
```

## O que os mapas mostram

Os mapas de trajetórias individuais usam uma realização de referência,
preferencialmente a seed 42, para evitar que a sobreposição de populações
Monte Carlo diferentes torne a figura ilegível.

Os mapas de fluxo agregado e o painel modo × classe utilizam todas as
realizações nominais disponíveis. O peso visual é baseado no número médio de
agentes por seed que usa cada segmento. Assim, cinco seeds não são tratadas
como se fossem uma única população N=500.

## Aviso temporal

A versão atual do piloto gera **uma viagem por agente por realização**. Apenas
o roteamento de transporte coletivo possui horário de partida explícito, hoje
configurado no piloto.

Por isso, "proxy diária agregada" significa **todo o conjunto de viagens
simuladas agregado em um único mapa**. Não significa que o modelo já represente
uma agenda completa de 24 horas ou mudanças hora a hora.

Uma análise temporal intradiária real exigirá uma etapa posterior com agenda
de atividades/horários para cada agente.
