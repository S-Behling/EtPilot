# Bateria final de sensibilidade do piloto

## Configuração operacional

- Agentes por realização: 100
- Seeds nominais: 11, 23, 42, 73, 101
- Seed de referência para perturbações: 42
- Limiar principal de suporte: n_agents >= 5
- Limiar >= 10 é diagnóstico e não requisito para N=100

N=100 é uma escolha operacional do piloto por custo computacional, não uma evidência de convergência populacional.

## Bateria

- Execuções planejadas: 5
- Execuções consolidadas: 5
- Sensibilidade de destino: multiplicadores 0,75 e 1,25
- Sensibilidade modal à distância: multiplicadores 0,75 e 1,25
- Decomposição: modo homogenizado no cenário differentiated

## Produtos

- final_sensitivity_plan.csv
- final_sensitivity_runs.csv
- final_sensitivity_seed_stability.csv
- final_sensitivity_parameter_comparison.csv

A configuração comportamental só deve ser marcada como final após a inspeção dos resultados entre seeds e das perturbações locais.
