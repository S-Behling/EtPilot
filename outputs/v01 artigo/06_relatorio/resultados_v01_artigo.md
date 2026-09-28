# Resultados v01 do artigo

## Pergunta operacional

Em que medida regras de mobilidade socioeconomicamente diferenciadas alteram a diversidade socioeconomica observada nas trajetorias ao longo da rede urbana, em comparacao com um cenario comportamental homogeneo?

## Resultado principal

Mediana entre seeds = 0.102; IC95% bootstrap hierárquico [-0.095, 0.153].

A inferência não usa segmentos como observações independentes. O intervalo é obtido por bootstrap hierárquico: reamostragem de seeds e, dentro de cada seed, reamostragem pareada de agentes preservando toda a trajetória de cada agente.

## Dimensão espacial

- decrease_diversity: 8.3% do comprimento elegível.
- stable: 5.6% do comprimento elegível.
- increase_diversity: 86.2% do comprimento elegível.

## Mecanismos

A decomposição modal não está disponível.

A contribuição de cada grupo de renda para ΔH_soc também é calculada exatamente pela diferença entre os termos -p log(p) de baseline e differentiated; as contribuições somam o ΔH_soc do segmento.

## Robustez

Sensibilidades paramétricas ainda não disponíveis.

## Bases analíticas finais

- base01_agentes_pareados
- base02_segmentos_pareados
- base03_realizacoes

## Observação interpretativa

ΔH_soc descreve aumento ou redução da diversidade socioeconômica observada nas trajetórias. O sinal não é tratado como melhora ou piora.
