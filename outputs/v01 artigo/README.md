# v01 artigo

Esta pasta é o destino único do pacote analítico final do artigo.

Ela é gerada automaticamente por:

```bash
python -m src.analysis.article_v01
```

Estrutura esperada após a execução:

```text
outputs/v01 artigo/
├── 00_manifesto_analise.json
├── 01_bases/
│   ├── base01_agentes_pareados.csv
│   ├── base01_agentes_pareados.parquet
│   ├── base02_segmentos_pareados.parquet
│   ├── base02_segmentos_pareados.gpkg
│   ├── base03_realizacoes.csv
│   └── base03_realizacoes.parquet
├── 02_estatisticas/
│   ├── resposta_pergunta_artigo.csv
│   ├── resultado_principal_bootstrap.csv
│   ├── bootstrap_hierarquico_distribuicao.parquet
│   ├── resultado_espacial_segmentos.csv
│   ├── resultado_espacial_resumo.csv
│   ├── mecanismos_comportamentais_por_seed_renda.csv
│   ├── mecanismos_transicoes_modais.csv
│   ├── mecanismo_decomposicao_modo.csv
│   └── sensibilidade_parametros_artigo.csv
├── 03_tabelas/
│   ├── tabela01_resultado_principal.csv
│   ├── tabela02_mecanismos.csv
│   ├── tabela03_robustez.csv
│   └── tabelas_artigo.xlsx
├── 04_figuras/
│   ├── fig01_mapa_H_soc_baseline.png
│   ├── fig02_mapa_H_soc_differentiated.png
│   ├── fig03_mapa_delta_H_soc.png
│   ├── fig04_H_soc_pareado_por_seed.png
│   ├── fig05_delta_H_soc_seeds_bootstrap.png
│   ├── fig06_extensao_espacial_delta.png
│   ├── fig07_contribuicoes_entropia_renda.png
│   ├── fig08_mecanismos_comportamentais_renda.png
│   ├── fig09_sobreposicao_trajetorias_renda.png
│   ├── fig10_decomposicao_comportamental.png
│   ├── fig11_sensibilidade_parametros.png
│   └── figuras_manifesto.csv
├── 05_mapas/
│   └── mapa_consenso_delta_H_soc.gpkg
└── 06_relatorio/
    └── resultados_v01_artigo.md
```

## Regra estatística

Os segmentos viários são unidades espaciais descritivas e **não** são tratados
como observações estatísticas independentes.

A incerteza do resultado principal é estimada por bootstrap hierárquico:

1. reamostragem das realizações/seeds;
2. dentro de cada seed, reamostragem pareada dos agentes;
3. todas as passagens do agente reamostrado são preservadas conjuntamente,
   mantendo sua trajetória completa como cluster.

O resultado espacial é representado por consenso entre seeds e não por
testes independentes segmento a segmento.

## Reprodução

Para executar simulações e reconstruir todo o pacote:

```bash
python -m src.analysis.article_v01
```

Para reconstruir somente as análises quando as simulações já existem:

```bash
python -m src.analysis.article_v01 --skip-simulations
```
