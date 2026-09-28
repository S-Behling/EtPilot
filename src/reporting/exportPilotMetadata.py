"""Exporta a documentação estruturada do piloto em XLSX e HTML

Registra variáveis principais, métodos de análise, estatísticas, métodos de
limpeza, parâmetros de configuração e arquivos gerados pelo pipeline
Mantém todas as descrições em português
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

import pandas as pd


VARIABLES = [
    {
        "nome": "agent_id",
        "grupo": "agente",
        "unidade": "identificador",
        "descricao": "Identificador único do agente sintético",
    },
    {
        "nome": "income_group",
        "grupo": "agente",
        "unidade": "categoria",
        "descricao": "Grupo de renda do agente com categorias low, middle e high",
    },
    {
        "nome": "origin_id",
        "grupo": "agente",
        "unidade": "identificador espacial",
        "descricao": "Identificador da origem residencial atribuída ao agente",
    },
    {
        "nome": "purpose",
        "grupo": "agente",
        "unidade": "categoria",
        "descricao": "Propósito da viagem entre trabalho, educação, saúde, compras e lazer",
    },
    {
        "nome": "destination_id",
        "grupo": "agente",
        "unidade": "identificador espacial",
        "descricao": "Identificador do destino selecionado para a viagem",
    },
    {
        "nome": "destination_weight",
        "grupo": "escolha de destino",
        "unidade": "peso adimensional",
        "descricao": "Peso de atratividade associado ao destino candidato",
    },
    {
        "nome": "od_distance_m",
        "grupo": "viagem",
        "unidade": "m",
        "descricao": "Distância euclidiana entre origem e destino usada antes do roteamento",
    },
    {
        "nome": "mode",
        "grupo": "viagem",
        "unidade": "categoria",
        "descricao": "Modo de viagem selecionado entre caminhada, bicicleta, carro e transporte coletivo",
    },
    {
        "nome": "origin_node",
        "grupo": "roteamento",
        "unidade": "identificador de nó",
        "descricao": "Nó efetivamente usado como origem na rede correspondente ao modo",
    },
    {
        "nome": "destination_node",
        "grupo": "roteamento",
        "unidade": "identificador de nó",
        "descricao": "Nó efetivamente usado como destino na rede correspondente ao modo",
    },
    {
        "nome": "route_status",
        "grupo": "roteamento",
        "unidade": "categoria",
        "descricao": "Estado final do roteamento do agente",
    },
    {
        "nome": "route_edges",
        "grupo": "roteamento",
        "unidade": "sequência de arestas",
        "descricao": "Sequência ordenada de arestas percorridas pelo agente",
    },
    {
        "nome": "n_route_edges",
        "grupo": "roteamento",
        "unidade": "arestas",
        "descricao": "Quantidade de arestas presentes na rota calculada",
    },
    {
        "nome": "travel_distance_m",
        "grupo": "roteamento",
        "unidade": "m",
        "descricao": "Distância total da rota calculada sobre a rede modal",
    },
    {
        "nome": "travel_time",
        "grupo": "roteamento",
        "unidade": "s",
        "descricao": "Tempo total de viagem reservado para os roteamentos que utilizam impedância temporal",
    },
    {
        "nome": "u",
        "grupo": "rede",
        "unidade": "identificador de nó",
        "descricao": "Nó inicial de uma aresta modal",
    },
    {
        "nome": "v",
        "grupo": "rede",
        "unidade": "identificador de nó",
        "descricao": "Nó final de uma aresta modal",
    },
    {
        "nome": "key",
        "grupo": "rede",
        "unidade": "identificador de aresta paralela",
        "descricao": "Chave da aresta em um MultiDiGraph",
    },
    {
        "nome": "modal_edge_id",
        "grupo": "rede",
        "unidade": "identificador",
        "descricao": "Identificador estável de uma aresta dentro de uma rede modal",
    },
    {
        "nome": "edge_length_m",
        "grupo": "rede",
        "unidade": "m",
        "descricao": "Comprimento da aresta modal",
    },
    {
        "nome": "osmid",
        "grupo": "rede",
        "unidade": "identificador OSM",
        "descricao": "Identificador de origem da feição viária no OpenStreetMap",
    },
    {
        "nome": "highway",
        "grupo": "rede",
        "unidade": "categoria OSM",
        "descricao": "Classificação viária fornecida pelo OpenStreetMap",
    },
    {
        "nome": "analysis_segment_id",
        "grupo": "harmonização",
        "unidade": "identificador",
        "descricao": "Identificador comum do segmento físico usado para comparar modos e cenários",
    },
    {
        "nome": "match_method",
        "grupo": "harmonização",
        "unidade": "categoria",
        "descricao": "Método usado para associar uma aresta modal a um segmento físico entre referência, equivalência OSM, sobreposição geométrica e segmento exclusivo",
    },
    {
        "nome": "match_quality",
        "grupo": "harmonização",
        "unidade": "proporção de 0 a 1",
        "descricao": "Qualidade da correspondência geométrica entre a aresta modal e o segmento físico",
    },
    {
        "nome": "n_passages",
        "grupo": "estatística por segmento",
        "unidade": "passagens agente × segmento",
        "descricao": "Quantidade total de registros de passagem pelo segmento físico",
    },
    {
        "nome": "n_agents",
        "grupo": "estatística por segmento",
        "unidade": "agentes distintos",
        "descricao": "Quantidade de agentes distintos observados no segmento físico",
    },
    {
        "nome": "n_low",
        "grupo": "estatística por segmento",
        "unidade": "agentes distintos",
        "descricao": "Quantidade de agentes do grupo de baixa renda observados no segmento",
    },
    {
        "nome": "n_middle",
        "grupo": "estatística por segmento",
        "unidade": "agentes distintos",
        "descricao": "Quantidade de agentes do grupo de renda intermediária observados no segmento",
    },
    {
        "nome": "n_high",
        "grupo": "estatística por segmento",
        "unidade": "agentes distintos",
        "descricao": "Quantidade de agentes do grupo de alta renda observados no segmento",
    },
    {
        "nome": "p_low",
        "grupo": "estatística por segmento",
        "unidade": "proporção de 0 a 1",
        "descricao": "Proporção de agentes de baixa renda entre os agentes distintos do segmento",
    },
    {
        "nome": "p_middle",
        "grupo": "estatística por segmento",
        "unidade": "proporção de 0 a 1",
        "descricao": "Proporção de agentes de renda intermediária entre os agentes distintos do segmento",
    },
    {
        "nome": "p_high",
        "grupo": "estatística por segmento",
        "unidade": "proporção de 0 a 1",
        "descricao": "Proporção de agentes de alta renda entre os agentes distintos do segmento",
    },
    {
        "nome": "income_groups_present",
        "grupo": "estatística por segmento",
        "unidade": "grupos",
        "descricao": "Quantidade de grupos de renda presentes no segmento",
    },
    {
        "nome": "H_soc",
        "grupo": "entropia",
        "unidade": "índice normalizado de 0 a 1",
        "descricao": "Entropia de Shannon normalizada da composição socioeconômica dos agentes que usam o segmento",
    },
    {
        "nome": "sufficient_flow",
        "grupo": "entropia",
        "unidade": "booleano",
        "descricao": "Indica se o segmento atinge o número mínimo de agentes definido para interpretação",
    },
    {
        "nome": "flow_ge_2",
        "grupo": "sensibilidade",
        "unidade": "booleano",
        "descricao": "Indica se o segmento possui pelo menos 2 agentes distintos",
    },
    {
        "nome": "flow_ge_3",
        "grupo": "sensibilidade",
        "unidade": "booleano",
        "descricao": "Indica se o segmento possui pelo menos 3 agentes distintos",
    },
    {
        "nome": "flow_ge_5",
        "grupo": "sensibilidade",
        "unidade": "booleano",
        "descricao": "Indica se o segmento possui pelo menos 5 agentes distintos",
    },
    {
        "nome": "flow_ge_10",
        "grupo": "sensibilidade",
        "unidade": "booleano",
        "descricao": "Indica se o segmento possui pelo menos 10 agentes distintos",
    },
    {
        "nome": "usage_status",
        "grupo": "comparação de cenários",
        "unidade": "categoria",
        "descricao": "Classifica o segmento como usado nos dois cenários, apenas no baseline, apenas no differentiated ou não usado",
    },
    {
        "nome": "comparable_H_soc",
        "grupo": "comparação de cenários",
        "unidade": "booleano",
        "descricao": "Indica se H_soc está observado nos dois cenários para o mesmo segmento",
    },
    {
        "nome": "delta_H_soc",
        "grupo": "comparação de cenários",
        "unidade": "diferença de índice",
        "descricao": "Diferença H_soc do cenário differentiated menos H_soc do cenário baseline no mesmo segmento físico",
    },
    {
        "nome": "delta_n_agents",
        "grupo": "comparação de cenários",
        "unidade": "agentes distintos",
        "descricao": "Diferença no número de agentes distintos entre differentiated e baseline",
    },
    {
        "nome": "delta_n_passages",
        "grupo": "comparação de cenários",
        "unidade": "passagens",
        "descricao": "Diferença no número de passagens entre differentiated e baseline",
    },
    {
        "nome": "sufficient_flow_both",
        "grupo": "comparação de cenários",
        "unidade": "booleano",
        "descricao": "Indica se o fluxo mínimo para interpretação é atingido nos dois cenários",
    },
    {
        "nome": "stop_id",
        "grupo": "GTFS",
        "unidade": "identificador",
        "descricao": "Identificador da parada de transporte coletivo",
    },
    {
        "nome": "route_id",
        "grupo": "GTFS",
        "unidade": "identificador",
        "descricao": "Identificador da rota ou linha no GTFS",
    },
    {
        "nome": "route_type",
        "grupo": "GTFS",
        "unidade": "código GTFS",
        "descricao": "Código do tipo de transporte da rota, sendo 3 correspondente a ônibus no feed atual",
    },
    {
        "nome": "trip_id",
        "grupo": "GTFS",
        "unidade": "identificador",
        "descricao": "Identificador da viagem programada no GTFS",
    },
    {
        "nome": "service_id",
        "grupo": "GTFS",
        "unidade": "identificador",
        "descricao": "Identificador do calendário de serviço associado à viagem",
    },
    {
        "nome": "service_date",
        "grupo": "GTFS",
        "unidade": "data",
        "descricao": "Data em que um service_id está ativo após combinar calendário semanal e exceções",
    },
    {
        "nome": "shape_id",
        "grupo": "GTFS",
        "unidade": "identificador",
        "descricao": "Identificador da geometria programada da viagem",
    },
    {
        "nome": "stop_sequence",
        "grupo": "GTFS",
        "unidade": "posição ordinal",
        "descricao": "Posição da parada dentro da sequência de uma viagem",
    },
    {
        "nome": "arrival_seconds",
        "grupo": "GTFS",
        "unidade": "s desde o início do dia de serviço",
        "descricao": "Horário de chegada convertido para segundos e preservando valores GTFS acima de 24 horas",
    },
    {
        "nome": "departure_seconds",
        "grupo": "GTFS",
        "unidade": "s desde o início do dia de serviço",
        "descricao": "Horário de partida convertido para segundos e preservando valores GTFS acima de 24 horas",
    },
    {
        "nome": "arrival_missing_raw",
        "grupo": "GTFS",
        "unidade": "booleano",
        "descricao": "Indica que o horário de chegada estava ausente no GTFS original",
    },
    {
        "nome": "departure_missing_raw",
        "grupo": "GTFS",
        "unidade": "booleano",
        "descricao": "Indica que o horário de partida estava ausente no GTFS original",
    },
    {
        "nome": "time_interpolated",
        "grupo": "GTFS",
        "unidade": "booleano",
        "descricao": "Indica que o horário da parada foi estimado durante o processamento",
    },
    {
        "nome": "time_interpolation_method",
        "grupo": "GTFS",
        "unidade": "categoria",
        "descricao": "Método usado para estimar o horário entre shape_dist_traveled, geometria do shape ou stop_sequence",
    },
    {
        "nome": "shape_position_m",
        "grupo": "GTFS",
        "unidade": "m ao longo do shape",
        "descricao": "Posição projetada da parada ao longo da geometria do shape",
    },
    {
        "nome": "node_walk",
        "grupo": "transporte coletivo",
        "unidade": "identificador de nó",
        "descricao": "Nó da rede de caminhada associado à parada GTFS",
    },
    {
        "nome": "walk_connector_distance_m",
        "grupo": "transporte coletivo",
        "unidade": "m",
        "descricao": "Distância entre a parada GTFS e o nó mais próximo da rede de caminhada",
    },
    {
        "nome": "walk_connector_time_s",
        "grupo": "transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo estimado para percorrer o conector entre a parada e a rede de caminhada",
    },
    {
        "nome": "connection_id",
        "grupo": "transporte coletivo",
        "unidade": "identificador",
        "descricao": "Identificador de uma conexão temporal entre duas paradas consecutivas de uma viagem",
    },
    {
        "nome": "from_stop_id",
        "grupo": "transporte coletivo",
        "unidade": "identificador",
        "descricao": "Parada de origem da conexão temporal",
    },
    {
        "nome": "to_stop_id",
        "grupo": "transporte coletivo",
        "unidade": "identificador",
        "descricao": "Parada de destino da conexão temporal",
    },
    {
        "nome": "in_vehicle_time_s",
        "grupo": "transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo programado dentro do veículo entre duas paradas consecutivas",
    },
    {
        "nome": "shape_segment_distance_m",
        "grupo": "transporte coletivo",
        "unidade": "m",
        "descricao": "Distância ao longo do shape entre duas paradas consecutivas quando a projeção geométrica é válida",
    },
    {
        "nome": "access_walk_distance_m",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "m",
        "descricao": "Distância total percorrida a pé entre a origem e a parada de embarque",
    },
    {
        "nome": "access_walk_time_s",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo total de caminhada entre a origem e a parada de embarque",
    },
    {
        "nome": "initial_wait_time_s",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo entre a chegada à parada de embarque e a partida do primeiro ônibus",
    },
    {
        "nome": "in_vehicle_time_s",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "s",
        "descricao": "Soma do tempo programado dentro dos veículos usados na viagem",
    },
    {
        "nome": "transfer_and_dwell_time_s",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo acumulado entre conexões que não corresponde ao deslocamento dentro do veículo",
    },
    {
        "nome": "n_boardings",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "embarques",
        "descricao": "Quantidade de viagens GTFS distintas embarcadas ao longo do itinerário",
    },
    {
        "nome": "n_transfers",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "transferências",
        "descricao": "Quantidade de trocas de viagem GTFS ao longo do itinerário",
    },
    {
        "nome": "mean_in_vehicle_time_per_connection_s",
        "grupo": "diagnóstico de transporte coletivo",
        "unidade": "s/conexão",
        "descricao": "Tempo médio dentro do veículo por conexão GTFS usada na rota, empregado como diagnóstico de qualidade temporal",
    },
    {
        "nome": "egress_walk_distance_m",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "m",
        "descricao": "Distância total percorrida a pé entre a parada de desembarque e o destino",
    },
    {
        "nome": "egress_walk_time_s",
        "grupo": "roteamento de transporte coletivo",
        "unidade": "s",
        "descricao": "Tempo total de caminhada entre a parada de desembarque e o destino",
    },
]

ANALYSIS_METHODS = [
    {
        "nome": "Geração de população sintética estratificada por renda",
        "funcao_codigo": "generate_population",
        "descricao": "Gera agentes sintéticos preservando as participações configuradas para os grupos de renda",
    },
    {
        "nome": "Atribuição ponderada de origens",
        "funcao_codigo": "assign_origins",
        "descricao": "Atribui origens residenciais aos agentes usando o peso populacional das unidades espaciais",
    },
    {
        "nome": "Escolha probabilística de propósito",
        "funcao_codigo": "assign_purpose",
        "descricao": "Sorteia o propósito da viagem segundo probabilidades configuradas por grupo de renda",
    },
    {
        "nome": "Escolha de destino com atratividade e decaimento da distância",
        "funcao_codigo": "assign_destinations",
        "descricao": "Seleciona destinos com peso proporcional à atratividade elevada a um expoente e ao decaimento exponencial da distância",
    },
    {
        "nome": "Escolha modal sensível à distância",
        "funcao_codigo": "calculate_mode_probabilities / choose_mode",
        "descricao": "Ajusta as probabilidades modais por uma função exponencial da distância OD e aplica limites máximos configuráveis por modo",
    },
    {
        "nome": "Cenário baseline comportamentalmente equalizado",
        "funcao_codigo": "build_behavior_scenarios",
        "descricao": "Remove diferenças comportamentais por renda usando médias ponderadas pelas participações populacionais",
    },
    {
        "nome": "Cenário differentiated",
        "funcao_codigo": "build_behavior_scenarios",
        "descricao": "Preserva diferenças por renda nas regras de propósito, destino e probabilidades modais",
    },
    {
        "nome": "Caminho mínimo de Dijkstra",
        "funcao_codigo": "route_agent / networkx.shortest_path",
        "descricao": "Calcula a rota sobre a rede modal usando comprimento como impedância no piloto viário",
    },
    {
        "nome": "Explosão de trajetórias em agente × aresta",
        "funcao_codigo": "build_edge_usage",
        "descricao": "Converte cada trajetória em registros de passagem por aresta para permitir agregação espacial",
    },
    {
        "nome": "Harmonização multimodal por equivalência OSM",
        "funcao_codigo": "build_analysis_segments",
        "descricao": "Associa arestas modais ao mesmo segmento físico quando existe equivalência estável de extremos e identificadores OSM",
    },
    {
        "nome": "Harmonização multimodal por sobreposição geométrica",
        "funcao_codigo": "build_analysis_segments",
        "descricao": "Associa arestas modais a segmentos físicos quando a correspondência exata não existe e a cobertura geométrica satisfaz os parâmetros configurados",
    },
    {
        "nome": "Preservação de segmentos exclusivos",
        "funcao_codigo": "build_analysis_segments",
        "descricao": "Mantém como unidades próprias as arestas modais que não encontram correspondência física adequada",
    },
    {
        "nome": "Entropia socioeconômica de Shannon normalizada",
        "funcao_codigo": "normalized_shannon_entropy",
        "descricao": "Mede a diversidade dos grupos de renda entre agentes distintos que usam o mesmo segmento físico",
    },
    {
        "nome": "Comparação pareada por segmento físico",
        "funcao_codigo": "build_scenario_comparison",
        "descricao": "Compara baseline e differentiated usando o mesmo analysis_segment_id e calcula diferenças apenas quando as métricas são comparáveis",
    },
    {
        "nome": "Análise de sensibilidade por limiar de fluxo",
        "funcao_codigo": "build_segment_statistics / build_scenario_comparison",
        "descricao": "Mantém indicadores para diferentes números mínimos de agentes por segmento",
    },
    {
        "nome": "Mapeamento diagnóstico com escalas fixas",
        "funcao_codigo": "save_pilot_maps",
        "descricao": "Gera mapas de H_soc e delta_H_soc com escalas fixas para permitir comparação visual entre cenários",
    },
    {
        "nome": "Expansão do calendário GTFS",
        "funcao_codigo": "_build_service_dates",
        "descricao": "Combina calendar e calendar_dates para gerar uma linha por service_id e data efetivamente ativa",
    },
    {
        "nome": "Interpolação temporal GTFS por shape_dist_traveled",
        "funcao_codigo": "_interpolate_stop_time_events",
        "descricao": "Interpola horários intermediários pela distância acumulada fornecida pelo GTFS quando esse campo é utilizável",
    },
    {
        "nome": "Interpolação temporal GTFS pela geometria do shape",
        "funcao_codigo": "_refine_stop_times_with_shape_geometry",
        "descricao": "Projeta paradas sobre o shape e interpola horários segundo a posição espacial ao longo da geometria quando a sequência é válida",
    },
    {
        "nome": "Interpolação temporal GTFS por stop_sequence",
        "funcao_codigo": "_interpolate_stop_time_events",
        "descricao": "Usa a posição ordinal das paradas como fallback quando não existe uma base de distância válida",
    },
    {
        "nome": "Associação de paradas à rede de caminhada",
        "funcao_codigo": "_connect_stops_to_walk_network",
        "descricao": "Associa cada parada GTFS ao nó mais próximo da rede de caminhada e calcula distância e tempo do conector",
    },
    {
        "nome": "Tabela temporal de conexões GTFS",
        "funcao_codigo": "_build_scheduled_connections",
        "descricao": "Representa cada par consecutivo de paradas de uma viagem como uma conexão temporal com partida, chegada e duração",
    },
    {
        "nome": "Perfil diário de oferta GTFS",
        "funcao_codigo": "_build_service_day_profile",
        "descricao": "Calcula o número de viagens programadas por data e identifica uma data de referência pela maior oferta do feed",
    },
    {
        "nome": "Roteamento temporal por varredura de conexões",
        "funcao_codigo": "TransitRouter.route",
        "descricao": "Procura a chegada mais cedo percorrendo as conexões GTFS em ordem temporal e combinando acesso e egresso pela rede de caminhada",
    },
    {
        "nome": "Busca de paradas acessíveis pela rede de caminhada",
        "funcao_codigo": "TransitRouter._candidate_stops",
        "descricao": "Usa Dijkstra limitado por distância para identificar múltiplas paradas alcançáveis a partir da origem ou do destino",
    },
    {
        "nome": "Transferência entre viagens no mesmo stop_id",
        "funcao_codigo": "TransitRouter.route",
        "descricao": "Permite a troca entre viagens GTFS na mesma parada quando o intervalo disponível atende ao tempo mínimo de transferência configurado",
    },
    {
        "nome": "Diagnóstico amostral do roteamento temporal",
        "funcao_codigo": "run_diagnostics",
        "descricao": "Seleciona pares origem-destino reprodutíveis das bases do piloto e resume cobertura, tempos, caminhada de acesso e egresso e transferências",
    },
    {
        "nome": "Validação de continuidade do itinerário de transporte coletivo",
        "funcao_codigo": "TransitRouter.route",
        "descricao": "Exige continuidade entre a parada de destino de uma conexão e a parada de origem da conexão seguinte e preserva a ordem numérica de stop_sequence em empates temporais",
    },
    {
        "nome": "Diagnóstico temporal por viagem GTFS",
        "funcao_codigo": "build_trip_temporal_quality",
        "descricao": "Resume por trip_id a quantidade de pontos temporais originais, a duração programada, a incidência de conexões de duração zero e a velocidade implícita pelo comprimento do shape",
    },
]

STATISTICS = [
    {
        "nome": "Contagem",
        "descricao": "Quantifica agentes, viagens, arestas, segmentos, paradas, rotas, shapes e demais unidades discretas",
    },
    {
        "nome": "Número de valores distintos",
        "descricao": "Conta agentes, arestas, nós, pares de paradas e identificadores únicos",
    },
    {
        "nome": "Frequência absoluta",
        "descricao": "Resume quantidades por categoria de renda, propósito, modo, status, método ou tipo",
    },
    {
        "nome": "Proporção",
        "descricao": "Expressa a participação relativa de grupos de renda, métodos de harmonização e outras categorias",
    },
    {
        "nome": "Percentual",
        "descricao": "Apresenta proporções multiplicadas por 100 em diagnósticos de cobertura e qualidade",
    },
    {
        "nome": "Média aritmética",
        "descricao": "Resume valores como distância, H_soc, delta_H_soc, qualidade de correspondência e tempo",
    },
    {
        "nome": "Mediana",
        "descricao": "Resume a tendência central de distâncias, tempos, H_soc e delta_H_soc com menor sensibilidade a extremos",
    },
    {
        "nome": "Mínimo",
        "descricao": "Registra o menor valor observado em distribuições de distância, tempo e outras métricas",
    },
    {
        "nome": "Máximo",
        "descricao": "Registra o maior valor observado em distribuições de distância, tempo e outras métricas",
    },
    {
        "nome": "Percentil 95",
        "descricao": "Resume a cauda superior da distância e do tempo dos conectores entre paradas e rede de caminhada",
    },
    {
        "nome": "Tabela de contingência",
        "descricao": "Cruza renda com propósito e renda com modo para diagnóstico das escolhas dos agentes",
    },
    {
        "nome": "Entropia de Shannon normalizada",
        "descricao": "Calcula a diversidade socioeconômica entre três grupos de renda com resultado normalizado entre zero e um",
    },
    {
        "nome": "Diferença pareada",
        "descricao": "Calcula differentiated menos baseline para H_soc, número de agentes e número de passagens no mesmo segmento físico",
    },
    {
        "nome": "Contagem por limiar",
        "descricao": "Conta segmentos que atingem valores mínimos de 2, 3, 5 e 10 agentes distintos",
    },
    {
        "nome": "Qualidade média de harmonização",
        "descricao": "Resume a qualidade das correspondências geométricas entre arestas modais e segmentos físicos",
    },
    {
        "nome": "Contagem de conexões com duração zero",
        "descricao": "Quantifica conexões GTFS cujo tempo entre partida e chegada é igual a zero para diagnosticar limitações do preenchimento temporal",
    },
    {
        "nome": "Tempo médio por conexão veicular",
        "descricao": "Divide o tempo dentro do veículo pelo número de conexões GTFS usadas na rota para identificar itinerários temporalmente suspeitos",
    },
    {
        "nome": "Velocidade implícita pelo shape",
        "descricao": "Relaciona o comprimento geométrico do shape à duração programada da viagem para diagnosticar a coerência temporal do GTFS processado",
    },
    {
        "nome": "Participação de conexões de duração zero por viagem",
        "descricao": "Mede a proporção de conexões consecutivas com tempo veicular igual a zero dentro de cada trip_id",
    },
]

CLEANING_METHODS = [
    {
        "nome": "Padronização de strings",
        "descricao": "Remove espaços excedentes e normaliza campos textuais usados como identificadores e categorias",
    },
    {
        "nome": "Preservação de identificadores como texto",
        "descricao": "Lê identificadores GTFS como strings para evitar perda de zeros à esquerda ou conversões indevidas",
    },
    {
        "nome": "Conversão numérica validada",
        "descricao": "Converte campos numéricos com detecção explícita de valores inválidos",
    },
    {
        "nome": "Validação de valores não vazios",
        "descricao": "Verifica campos obrigatórios antes de executar análise ou roteamento",
    },
    {
        "nome": "Validação de unicidade",
        "descricao": "Detecta chaves duplicadas em identificadores e sequências que devem ser únicas",
    },
    {
        "nome": "Validação de chaves estrangeiras GTFS",
        "descricao": "Confere referências entre routes, trips, stop_times, stops, service_ids e shapes",
    },
    {
        "nome": "Filtragem de destinos inválidos",
        "descricao": "Remove destinos sem geometria, categoria, peso de atratividade positivo ou nós modais necessários",
    },
    {
        "nome": "Harmonização de CRS",
        "descricao": "Converte camadas espaciais para o CRS projetado EPSG:31982 quando necessário",
    },
    {
        "nome": "Validação de coordenadas geográficas",
        "descricao": "Rejeita latitudes e longitudes GTFS fora dos intervalos válidos",
    },
    {
        "nome": "Ordenação de sequências de viagem",
        "descricao": "Ordena stop_times por trip_id e stop_sequence antes da análise temporal",
    },
    {
        "nome": "Conversão de horários GTFS para segundos",
        "descricao": "Converte HH:MM:SS em segundos desde o início do dia de serviço e preserva horários acima de 24 horas",
    },
    {
        "nome": "Interpolação explícita de horários ausentes",
        "descricao": "Preenche horários intermediários apenas entre âncoras conhecidas e registra o método usado",
    },
    {
        "nome": "Validação de monotonicidade temporal",
        "descricao": "Rejeita viagens em que os horários processados diminuem ao avançar pela sequência de paradas",
    },
    {
        "nome": "Validação de duração de conexão",
        "descricao": "Rejeita conexões temporais com chegada anterior à partida",
    },
    {
        "nome": "Expansão e aplicação de exceções do calendário",
        "descricao": "Combina o padrão semanal com inclusões e exclusões específicas de calendar_dates",
    },
    {
        "nome": "Remoção de estruturas não serializáveis",
        "descricao": "Remove coleções Python como osmid_set antes de gravar determinadas camadas GeoPackage",
    },
    {
        "nome": "Substituição controlada de arquivos processados",
        "descricao": "Remove a versão anterior de produtos derivados antes de gravar uma nova versão",
    },
    {
        "nome": "Deduplicação agente × segmento",
        "descricao": "Usa apenas uma observação por agente e segmento para composição socioeconômica e evita inflar pesos por repetição de passagem",
    },
    {
        "nome": "Ordenação numérica de stop_sequence em empates temporais",
        "descricao": "Ordena conexões com o mesmo horário usando a sequência numérica da parada e evita a ordenação lexicográfica de identificadores como 19 antes de 2",
    },
    {
        "nome": "Validação de continuidade entre conexões GTFS",
        "descricao": "Confere se cada conexão do itinerário começa na parada onde a conexão anterior terminou antes de aceitar o resultado do roteamento",
    },
]

FILES = [
    ("data/graph/rede-poa-car.graphml", "Rede viária OSM processada para roteamento de carro", "rede OSM", False),
    ("data/graph/rede-poa-walk.graphml", "Rede OSM processada para roteamento de caminhada", "rede OSM", False),
    ("data/graph/rede-poa-bike.graphml", "Rede OSM processada para roteamento de bicicleta", "rede OSM", False),
    ("data/graph/rede-poa.graphml", "Rede OSM legada preservada para compatibilidade com etapas exploratórias anteriores", "rede OSM", True),
    ("data/o-d/origens_porto_alegre.gpkg", "Camada de origens espaciais de Porto Alegre usada na preparação das origens socioeconômicas", "origens", True),
    ("data/o-d/origens_porto_alegre_income.gpkg", "Camada de origens residenciais com informação socioeconômica e nós modais associados", "origens", False),
    ("data/o-d/destinos_cnefe_porto_alegre.gpkg", "Camada intermediária de estabelecimentos e destinos derivados do CNEFE", "destinos", True),
    ("data/o-d/destinos_cnefe_classificados_porto_alegre.gpkg", "Camada final de destinos CNEFE classificados por propósito e com nós modais", "destinos", False),
    ("data/gtfs/porto_alegre_gtfs.zip", "Arquivo GTFS original baixado da fonte oficial configurada para a EPTC", "GTFS", False),
    ("data/gtfs/gtfs_download_metadata.json", "Metadados do download GTFS com fonte, data, tamanho e hash SHA-256", "GTFS", False),
    ("data/gtfs/agency_processed.parquet", "Tabela GTFS de operadores após validação", "GTFS processado", False),
    ("data/gtfs/routes_processed.parquet", "Tabela GTFS de rotas após validação e tipagem", "GTFS processado", False),
    ("data/gtfs/trips_processed.parquet", "Tabela GTFS de viagens programadas após validação", "GTFS processado", False),
    ("data/gtfs/stop_times_processed.parquet", "Tabela de horários processados com segundos, flags de ausência e métodos de interpolação", "GTFS processado", False),
    ("data/gtfs/calendar_processed.parquet", "Calendário semanal GTFS processado quando disponível", "GTFS processado", True),
    ("data/gtfs/calendar_dates_processed.parquet", "Exceções de calendário GTFS processadas quando disponíveis", "GTFS processado", True),
    ("data/gtfs/service_dates_processed.parquet", "Datas efetivas de serviço após combinar calendário e exceções", "GTFS processado", False),
    ("data/gtfs/stops_processed.gpkg", "Paradas GTFS projetadas para o CRS do estudo", "GTFS processado", False),
    ("data/gtfs/shapes_processed.gpkg", "Geometrias de shapes GTFS reconstruídas e projetadas para o CRS do estudo", "GTFS processado", True),
    ("data/gtfs/frequencies_processed.parquet", "Tabela GTFS de frequências processada quando o feed fornece frequencies.txt", "GTFS processado", True),
    ("data/gtfs/transfers_processed.parquet", "Tabela GTFS de transferências processada quando o feed fornece transfers.txt", "GTFS processado", True),
    ("data/gtfs/feed_info_processed.parquet", "Metadados do feed GTFS processados quando disponíveis", "GTFS processado", True),
    ("data/gtfs/gtfs_processed_inventory.csv", "Inventário das tabelas GTFS encontradas e processadas", "GTFS processado", False),
    ("data/gtfs/gtfs_processed_summary.csv", "Resumo quantitativo e diagnóstico do processamento GTFS", "GTFS processado", False),
    ("data/gtfs/stops_walk_connected_processed.gpkg", "Paradas GTFS com associação ao nó mais próximo da rede de caminhada e métricas do conector", "rede de transporte coletivo", False),
    ("data/gtfs/transit_stop_walk_connectors_processed.parquet", "Tabela tabular dos conectores entre paradas GTFS e nós da rede de caminhada", "rede de transporte coletivo", False),
    ("data/gtfs/transit_connections_processed.parquet", "Tabela temporal de conexões entre paradas consecutivas de todas as viagens GTFS", "rede de transporte coletivo", False),
    ("data/gtfs/transit_topology_processed.parquet", "Resumo topológico das ligações entre pares direcionais de paradas por rota", "rede de transporte coletivo", False),
    ("data/gtfs/transit_service_day_profile_processed.csv", "Perfil diário do número de serviços e viagens programadas no período do GTFS", "rede de transporte coletivo", False),
    ("data/gtfs/transit_network_summary.csv", "Resumo diagnóstico da associação das paradas à caminhada e da tabela temporal de ônibus", "rede de transporte coletivo", False),
    ("outputs/pilot/agents_baseline.csv", "Agentes e resultados de viagem do cenário baseline", "simulação", False),
    ("outputs/pilot/agents_differentiated.csv", "Agentes e resultados de viagem do cenário differentiated", "simulação", False),
    ("outputs/pilot/agents_all_scenarios.csv", "Agentes dos dois cenários reunidos em uma única tabela", "simulação", False),
    ("outputs/pilot/edge_usage_baseline.csv", "Registros agente × aresta modal do cenário baseline", "trajetórias", False),
    ("outputs/pilot/edge_usage_differentiated.csv", "Registros agente × aresta modal do cenário differentiated", "trajetórias", False),
    ("outputs/pilot/edge_usage_all_scenarios.csv", "Registros agente × aresta modal dos dois cenários", "trajetórias", False),
    ("outputs/pilot/edge_usage_analysis_baseline.csv", "Uso das arestas do baseline associado aos segmentos físicos comuns", "harmonização", False),
    ("outputs/pilot/edge_usage_analysis_differentiated.csv", "Uso das arestas do differentiated associado aos segmentos físicos comuns", "harmonização", False),
    ("outputs/pilot/edge_usage_analysis_all_scenarios.csv", "Uso harmonizado dos segmentos físicos nos dois cenários", "harmonização", False),
    ("outputs/pilot/modal_edge_to_analysis_segment.csv", "Mapeamento de cada aresta modal para um ou mais segmentos físicos de análise", "harmonização", False),
    ("outputs/pilot/analysis_segment_match_report.csv", "Resumo dos métodos e da qualidade de harmonização nas redes completas", "harmonização", False),
    ("outputs/pilot/analysis_segment_used_match_report.csv", "Resumo dos métodos e da qualidade de harmonização restrito às arestas usadas pelos agentes", "harmonização", False),
    ("outputs/pilot/analysis_segments.gpkg", "Camada completa dos segmentos físicos usados como unidade comum de análise", "harmonização", False),
    ("outputs/pilot/segment_statistics_baseline.csv", "Estatísticas de fluxo, composição socioeconômica e H_soc do cenário baseline", "entropia", False),
    ("outputs/pilot/segment_statistics_differentiated.csv", "Estatísticas de fluxo, composição socioeconômica e H_soc do cenário differentiated", "entropia", False),
    ("outputs/pilot/segment_statistics_all_scenarios.csv", "Estatísticas de segmentos dos dois cenários reunidas", "entropia", False),
    ("outputs/pilot/segment_metrics_baseline.gpkg", "Camada espacial dos segmentos físicos com métricas do cenário baseline", "entropia", False),
    ("outputs/pilot/segment_metrics_differentiated.gpkg", "Camada espacial dos segmentos físicos com métricas do cenário differentiated", "entropia", False),
    ("outputs/pilot/segment_scenario_comparison.csv", "Comparação pareada de baseline e differentiated por analysis_segment_id", "comparação", False),
    ("outputs/pilot/segment_scenario_comparison_summary.csv", "Resumo quantitativo da comparação pareada entre os cenários", "comparação", False),
    ("outputs/pilot/segment_scenario_comparison.gpkg", "Camada espacial com métricas pareadas e delta_H_soc", "comparação", False),
    ("outputs/pilot/maps/h_soc_baseline_all.png", "Mapa de H_soc do baseline para todos os segmentos observados", "mapas", False),
    ("outputs/pilot/maps/h_soc_baseline_supported.png", "Mapa de H_soc do baseline restrito aos segmentos com fluxo suficiente", "mapas", False),
    ("outputs/pilot/maps/h_soc_differentiated_all.png", "Mapa de H_soc do differentiated para todos os segmentos observados", "mapas", False),
    ("outputs/pilot/maps/h_soc_differentiated_supported.png", "Mapa de H_soc do differentiated restrito aos segmentos com fluxo suficiente", "mapas", False),
    ("outputs/pilot/maps/delta_h_soc_all.png", "Mapa da diferença pareada de H_soc para todos os segmentos comparáveis", "mapas", False),
    ("outputs/pilot/maps/delta_h_soc_supported.png", "Mapa da diferença pareada de H_soc restrito aos segmentos com fluxo suficiente nos dois cenários", "mapas", False),
    ("outputs/pilot/maps/map_manifest.csv", "Manifesto dos mapas gerados com identificação, quantidade de segmentos e descrição em português", "mapas", False),
    ("outputs/pilot/transit_routing_diagnostics.csv", "Amostra de consultas origem-destino usada para validar cobertura, tempos, acesso, egresso e transferências do roteador temporal de ônibus", "roteamento de transporte coletivo", False),
    ("outputs/pilot/gtfs_trip_temporal_quality.csv", "Diagnóstico por trip_id com duração programada, pontos temporais originais, conexões de duração zero e velocidade implícita pelo shape", "qualidade temporal do GTFS", False),
    ("outputs/metadados_piloto.xlsx", "Planilha consolidada com variáveis, parâmetros, métodos, estatísticas, limpeza e arquivos do piloto", "documentação", False),
    ("outputs/metadados_piloto.html", "Relatório HTML navegável com a documentação metodológica consolidada do piloto", "documentação", False),
]


def _load_json(
    path: Path,
) -> dict:
    """Carrega um arquivo JSON quando ele existe"""

    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )



def _parameter_row(
    *,
    nome: str,
    valor,
    unidade: str,
    descricao: str,
    origem: str,
) -> dict:
    """Cria uma linha padronizada da tabela de parâmetros"""

    return {
        "nome": nome,
        "valor": (
            ""
            if valor is None
            else valor
        ),
        "unidade": unidade,
        "descricao": descricao,
        "origem": origem,
    }


def _collect_config_parameters(
    *,
    config: dict,
    config_agents: dict,
) -> list[dict]:
    """Reúne os principais parâmetros atuais do experimento"""

    rows = [
        _parameter_row(
            nome="N_AGENTS",
            valor=100,
            unidade="agentes",
            descricao="Tamanho atual da população sintética usada na execução técnica do piloto",
            origem="src/simulation/run_pilot.py",
        ),
        _parameter_row(
            nome="SEED",
            valor=42,
            unidade="inteiro",
            descricao="Semente pseudoaleatória usada para garantir reprodutibilidade da população e das escolhas",
            origem="src/simulation/run_pilot.py",
        ),
    ]

    study_area = config.get(
        "study_area",
        {},
    )
    analysis = config.get(
        "analysis",
        {},
    )
    routing = config.get(
        "routing",
        {},
    )
    transit = config.get(
        "transit",
        {},
    )

    configured = [
        (
            "study_area.crs",
            study_area.get(
                "crs"
            ),
            "CRS",
            "Sistema de referência projetado usado nas análises espaciais",
        ),
        (
            "analysis.max_trip_distance",
            analysis.get(
                "max_trip_distance"
            ),
            "m",
            "Distância euclidiana máxima permitida na seleção de destinos candidatos",
        ),
        (
            "analysis.analysis_segments.geometry_tolerance_m",
            analysis.get(
                "analysis_segments",
                {},
            ).get(
                "geometry_tolerance_m"
            ),
            "m",
            "Tolerância geométrica usada na harmonização das redes modais",
        ),
        (
            "analysis.analysis_segments.min_geometry_coverage",
            analysis.get(
                "analysis_segments",
                {},
            ).get(
                "min_geometry_coverage"
            ),
            "proporção de 0 a 1",
            "Cobertura geométrica mínima para aceitar correspondência entre arestas modais e segmentos físicos",
        ),
        (
            "analysis.segment_statistics.min_agents_for_interpretation",
            analysis.get(
                "segment_statistics",
                {},
            ).get(
                "min_agents_for_interpretation"
            ),
            "agentes",
            "Número mínimo de agentes distintos adotado como suporte principal para interpretação de H_soc",
        ),
        (
            "analysis.segment_statistics.flow_thresholds",
            " | ".join(
                str(
                    value
                )
                for value in analysis.get(
                    "segment_statistics",
                    {},
                ).get(
                    "flow_thresholds",
                    [],
                )
            ),
            "agentes",
            "Limiares preservados para análise de sensibilidade do suporte amostral por segmento",
        ),
        (
            "routing.implemented_modes",
            " | ".join(
                routing.get(
                    "implemented_modes",
                    []
                )
            ),
            "categorias",
            "Modos com roteamento viário atualmente integrado ao run_pilot",
        ),
        (
            "transit.network.walk_speed_m_s",
            transit.get(
                "network",
                {},
            ).get(
                "walk_speed_m_s"
            ),
            "m/s",
            "Velocidade provisória usada para converter o conector parada-rede de caminhada em tempo",
        ),
        (
            "transit.network.service_date_strategy",
            transit.get(
                "network",
                {},
            ).get(
                "service_date_strategy"
            ),
            "categoria",
            "Regra usada para selecionar uma data de serviço representativa do feed",
        ),
        (
            "transit.routing.max_access_walk_m",
            transit.get(
                "routing",
                {},
            ).get(
                "max_access_walk_m"
            ),
            "m",
            "Distância máxima de caminhada entre a origem e uma parada candidata de embarque",
        ),
        (
            "transit.routing.max_egress_walk_m",
            transit.get(
                "routing",
                {},
            ).get(
                "max_egress_walk_m"
            ),
            "m",
            "Distância máxima de caminhada entre uma parada candidata de desembarque e o destino",
        ),
        (
            "transit.routing.minimum_transfer_time_s",
            transit.get(
                "routing",
                {},
            ).get(
                "minimum_transfer_time_s"
            ),
            "s",
            "Tempo mínimo provisório exigido para realizar transferência entre viagens na mesma parada",
        ),
        (
            "transit.routing.max_total_travel_time_s",
            transit.get(
                "routing",
                {},
            ).get(
                "max_total_travel_time_s"
            ),
            "s",
            "Horizonte máximo provisório considerado em uma consulta de transporte coletivo",
        ),
        (
            "transit.routing.diagnostics.sample_size",
            transit.get(
                "routing",
                {},
            ).get(
                "diagnostics",
                {},
            ).get(
                "sample_size"
            ),
            "viagens OD",
            "Quantidade de pares origem-destino usada no diagnóstico técnico do roteador temporal",
        ),
        (
            "transit.routing.diagnostics.departure_time_s",
            transit.get(
                "routing",
                {},
            ).get(
                "diagnostics",
                {},
            ).get(
                "departure_time_s"
            ),
            "s desde o início do dia de serviço",
            "Horário de partida comum usado nas consultas do diagnóstico técnico",
        ),
        (
            "transit.routing.diagnostics.seed",
            transit.get(
                "routing",
                {},
            ).get(
                "diagnostics",
                {},
            ).get(
                "seed"
            ),
            "inteiro",
            "Semente pseudoaleatória usada para selecionar os pares origem-destino do diagnóstico",
        ),
    ]

    rows.extend(
        _parameter_row(
            nome=nome,
            valor=valor,
            unidade=unidade,
            descricao=descricao,
            origem="config/config.json",
        )
        for (
            nome,
            valor,
            unidade,
            descricao,
        )
        in configured
    )

    income_groups = (
        config.get(
            "income",
            {},
        )
        .get(
            "groups",
            {},
        )
    )

    for group_name, group_data in income_groups.items():
        rows.extend(
            [
                _parameter_row(
                    nome=f"income.groups.{group_name}.share",
                    valor=group_data.get(
                        "share"
                    ),
                    unidade="proporção de 0 a 1",
                    descricao=f"Participação populacional configurada para o grupo de renda {group_name}",
                    origem="config/config.json",
                ),
                _parameter_row(
                    nome=f"income.groups.{group_name}.min",
                    valor=group_data.get(
                        "min"
                    ),
                    unidade="moeda da variável de renda de origem",
                    descricao=f"Limite inferior configurado para classificar o grupo de renda {group_name}",
                    origem="config/config.json",
                ),
                _parameter_row(
                    nome=f"income.groups.{group_name}.max",
                    valor=group_data.get(
                        "max"
                    ),
                    unidade="moeda da variável de renda de origem",
                    descricao=f"Limite superior configurado para classificar o grupo de renda {group_name}",
                    origem="config/config.json",
                ),
            ]
        )

    distance_adjustment = (
        config_agents.get(
            "mode_choice",
            {},
        )
        .get(
            "distance_adjustment",
            {},
        )
    )

    for mode_name, beta in distance_adjustment.get(
        "decay_per_km",
        {},
    ).items():
        rows.append(
            _parameter_row(
                nome=f"mode_choice.distance_adjustment.decay_per_km.{mode_name}",
                valor=beta,
                unidade="1/km",
                descricao=f"Coeficiente provisório de penalização da distância na escolha do modo {mode_name}",
                origem="config/config_agents.json",
            )
        )

    for mode_name, limit in distance_adjustment.get(
        "max_distance_km",
        {},
    ).items():
        rows.append(
            _parameter_row(
                nome=f"mode_choice.distance_adjustment.max_distance_km.{mode_name}",
                valor=limit,
                unidade="km",
                descricao=f"Distância OD máxima provisória permitida para o modo {mode_name} quando configurada",
                origem="config/config_agents.json",
            )
        )

    destination_decay = (
        config_agents.get(
            "destination_choice",
            {},
        )
        .get(
            "distance_decay_per_km",
            {},
        )
    )

    for purpose, values in destination_decay.items():
        for group_name, beta in values.items():
            rows.append(
                _parameter_row(
                    nome=f"destination_choice.distance_decay_per_km.{purpose}.{group_name}",
                    valor=beta,
                    unidade="1/km",
                    descricao=f"Coeficiente de decaimento da distância para destino de {purpose} no grupo {group_name}",
                    origem="config/config_agents.json",
                )
            )

    purpose_choice = config_agents.get(
        "purpose_choice",
        {},
    )

    for group_name, values in purpose_choice.items():
        for purpose, probability in values.items():
            rows.append(
                _parameter_row(
                    nome=f"purpose_choice.{group_name}.{purpose}",
                    valor=probability,
                    unidade="probabilidade de 0 a 1",
                    descricao=f"Probabilidade configurada do propósito {purpose} para o grupo de renda {group_name}",
                    origem="config/config_agents.json",
                )
            )

    mode_choice = (
        config_agents.get(
            "mode_choice",
            {},
        )
        .get(
            "differentiated",
            {},
        )
    )

    for group_name, values in mode_choice.items():
        for mode_name, probability in values.items():
            rows.append(
                _parameter_row(
                    nome=f"mode_choice.differentiated.{group_name}.{mode_name}",
                    valor=probability,
                    unidade="probabilidade de 0 a 1",
                    descricao=f"Probabilidade modal base de {mode_name} no cenário differentiated para o grupo {group_name}",
                    origem="config/config_agents.json",
                )
            )

    return rows


def _collect_file_rows(
    *,
    project_root: Path,
    generated_paths: set[Path],
) -> list[dict]:
    """Reúne o inventário dos arquivos gerados ao longo do piloto"""

    rows: list[
        dict
    ] = []

    for (
        relative_path,
        description,
        stage,
        optional,
    ) in FILES:
        absolute_path = (
            project_root
            / relative_path
        )
        exists_now = (
            absolute_path.exists()
            or absolute_path.resolve()
            in generated_paths
        )

        rows.append(
            {
                "nome": Path(
                    relative_path
                ).name,
                "caminho": relative_path,
                "etapa": stage,
                "descricao": description,
                "opcional": (
                    "sim"
                    if optional
                    else "não"
                ),
                "existe_no_momento": (
                    "sim"
                    if exists_now
                    else "não"
                ),
                "tamanho_bytes": (
                    absolute_path.stat().st_size
                    if absolute_path.exists()
                    else ""
                ),
            }
        )

    return rows


def _build_metadata_frames(
    *,
    project_root: Path,
    xlsx_path: Path,
    html_path: Path,
) -> tuple[
    dict[str, pd.DataFrame],
    str,
]:
    """Constrói as tabelas usadas nas duas formas de documentação"""

    config = _load_json(
        project_root
        / "config"
        / "config.json"
    )
    config_agents = _load_json(
        project_root
        / "config"
        / "config_agents.json"
    )

    generated_at = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    generated_paths = {
        xlsx_path.resolve(),
        html_path.resolve(),
    }

    summary = pd.DataFrame(
        [
            {
                "campo": "Projeto",
                "valor": "EtPilot",
            },
            {
                "campo": "Descrição",
                "valor": "Piloto computacional de mobilidade urbana, diferenciação socioespacial e entropia socioeconômica de trajetórias",
            },
            {
                "campo": "Gerado em UTC",
                "valor": generated_at,
            },
            {
                "campo": "Idioma das descrições",
                "valor": "português",
            },
            {
                "campo": "Quantidade de variáveis documentadas",
                "valor": len(
                    VARIABLES
                ),
            },
            {
                "campo": "Quantidade de métodos de análise",
                "valor": len(
                    ANALYSIS_METHODS
                ),
            },
            {
                "campo": "Quantidade de estatísticas documentadas",
                "valor": len(
                    STATISTICS
                ),
            },
            {
                "campo": "Quantidade de métodos de limpeza",
                "valor": len(
                    CLEANING_METHODS
                ),
            },
            {
                "campo": "Quantidade de arquivos catalogados",
                "valor": len(
                    FILES
                ),
            },
        ]
    )

    frames = {
        "Resumo": summary,
        "Variáveis": pd.DataFrame(
            VARIABLES
        ),
        "Parâmetros": pd.DataFrame(
            _collect_config_parameters(
                config=config,
                config_agents=config_agents,
            )
        ),
        "Métodos de análise": pd.DataFrame(
            ANALYSIS_METHODS
        ),
        "Estatísticas": pd.DataFrame(
            STATISTICS
        ),
        "Métodos de limpeza": pd.DataFrame(
            CLEANING_METHODS
        ),
        "Arquivos gerados": pd.DataFrame(
            _collect_file_rows(
                project_root=project_root,
                generated_paths=generated_paths,
            )
        ),
    }

    return (
        frames,
        generated_at,
    )


def _excel_column_widths(
    sheet_name: str,
) -> dict[str, int]:
    """Define larguras legíveis para cada planilha"""

    defaults = {
        "Resumo": {
            "campo": 38,
            "valor": 95,
        },
        "Variáveis": {
            "nome": 30,
            "grupo": 26,
            "unidade": 30,
            "descricao": 90,
        },
        "Parâmetros": {
            "nome": 58,
            "valor": 24,
            "unidade": 30,
            "descricao": 90,
            "origem": 34,
        },
        "Métodos de análise": {
            "nome": 52,
            "funcao_codigo": 42,
            "descricao": 95,
        },
        "Estatísticas": {
            "nome": 40,
            "descricao": 100,
        },
        "Métodos de limpeza": {
            "nome": 48,
            "descricao": 100,
        },
        "Arquivos gerados": {
            "nome": 48,
            "caminho": 72,
            "etapa": 28,
            "descricao": 100,
            "opcional": 14,
            "existe_no_momento": 20,
            "tamanho_bytes": 20,
        },
    }

    return defaults.get(
        sheet_name,
        {},
    )


def _write_xlsx(
    *,
    path: Path,
    frames: dict[str, pd.DataFrame],
) -> None:
    """Gera a planilha de metadados com uma aba por categoria"""

    with pd.ExcelWriter(
        path,
        engine="xlsxwriter",
    ) as writer:
        workbook = writer.book

        title_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 15,
                "font_color": "#FFFFFF",
                "bg_color": "#1F4E78",
                "align": "left",
                "valign": "vcenter",
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#4472C4",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        body_format = workbook.add_format(
            {
                "valign": "top",
                "text_wrap": True,
                "border": 1,
                "border_color": "#D9E2F3",
            }
        )
        alternate_format = workbook.add_format(
            {
                "valign": "top",
                "text_wrap": True,
                "border": 1,
                "border_color": "#D9E2F3",
                "bg_color": "#F5F9FD",
            }
        )

        for sheet_name, frame in frames.items():
            frame.to_excel(
                writer,
                sheet_name=sheet_name,
                startrow=2,
                index=False,
            )

            worksheet = writer.sheets[
                sheet_name
            ]

            worksheet.merge_range(
                0,
                0,
                0,
                max(
                    len(
                        frame.columns
                    )
                    - 1,
                    0,
                ),
                f"Metadados do piloto — {sheet_name}",
                title_format,
            )
            worksheet.set_row(
                0,
                24,
            )
            worksheet.freeze_panes(
                3,
                0,
            )
            worksheet.autofilter(
                2,
                0,
                max(
                    len(
                        frame
                    )
                    + 2,
                    2,
                ),
                max(
                    len(
                        frame.columns
                    )
                    - 1,
                    0,
                ),
            )

            for column_index, column_name in enumerate(
                frame.columns
            ):
                worksheet.write(
                    2,
                    column_index,
                    column_name,
                    header_format,
                )

                width = (
                    _excel_column_widths(
                        sheet_name
                    )
                    .get(
                        str(
                            column_name
                        ),
                        24,
                    )
                )

                worksheet.set_column(
                    column_index,
                    column_index,
                    width,
                )

            for row_index in range(
                len(
                    frame
                )
            ):
                worksheet.set_row(
                    row_index
                    + 3,
                    34,
                )

                format_to_use = (
                    alternate_format
                    if row_index
                    % 2
                    else body_format
                )

                for column_index, value in enumerate(
                    frame.iloc[
                        row_index
                    ]
                ):
                    worksheet.write(
                        row_index
                        + 3,
                        column_index,
                        (
                            ""
                            if pd.isna(
                                value
                            )
                            else value
                        ),
                        format_to_use,
                    )


def _html_table(
    *,
    title: str,
    section_id: str,
    frame: pd.DataFrame,
    description: str,
) -> str:
    """Gera uma seção HTML tabular"""

    table = frame.to_html(
        index=False,
        escape=True,
        classes=[
            "metadata-table",
        ],
        border=0,
        na_rep="",
    )

    return (
        f'<section id="{escape(section_id)}">'
        f"<h2>{escape(title)}</h2>"
        f"<p>{escape(description)}</p>"
        f"{table}"
        "</section>"
    )


def _write_html(
    *,
    path: Path,
    frames: dict[str, pd.DataFrame],
    generated_at: str,
) -> None:
    """Gera um relatório HTML navegável dos metadados"""

    sections = [
        (
            "Variáveis principais",
            "variaveis",
            frames[
                "Variáveis"
            ],
            "Variáveis centrais usadas na simulação, no roteamento, na harmonização, nas métricas e no processamento do GTFS",
        ),
        (
            "Parâmetros de configuração",
            "parametros",
            frames[
                "Parâmetros"
            ],
            "Parâmetros que controlam a população sintética, as escolhas comportamentais, a análise espacial e a preparação do transporte coletivo",
        ),
        (
            "Métodos de análise",
            "metodos",
            frames[
                "Métodos de análise"
            ],
            "Métodos computacionais e analíticos empregados ao longo do piloto",
        ),
        (
            "Estatísticas",
            "estatisticas",
            frames[
                "Estatísticas"
            ],
            "Estatísticas e medidas resumidas usadas nos diagnósticos e comparações",
        ),
        (
            "Métodos de limpeza e validação",
            "limpeza",
            frames[
                "Métodos de limpeza"
            ],
            "Operações de limpeza, validação, padronização e controle de consistência aplicadas às bases",
        ),
        (
            "Arquivos gerados",
            "arquivos",
            frames[
                "Arquivos gerados"
            ],
            "Inventário dos arquivos produzidos ou mantidos ao longo do piloto e a função de cada produto",
        ),
    ]

    navigation = "".join(
        (
            f'<a href="#{escape(section_id)}">'
            f"{escape(title)}"
            "</a>"
        )
        for title, section_id, _, _
        in sections
    )

    cards = "".join(
        [
            (
                '<div class="card">'
                '<span class="card-number">'
                f"{len(VARIABLES)}"
                "</span>"
                '<span class="card-label">variáveis</span>'
                "</div>"
            ),
            (
                '<div class="card">'
                '<span class="card-number">'
                f"{len(ANALYSIS_METHODS)}"
                "</span>"
                '<span class="card-label">métodos</span>'
                "</div>"
            ),
            (
                '<div class="card">'
                '<span class="card-number">'
                f"{len(STATISTICS)}"
                "</span>"
                '<span class="card-label">estatísticas</span>'
                "</div>"
            ),
            (
                '<div class="card">'
                '<span class="card-number">'
                f"{len(CLEANING_METHODS)}"
                "</span>"
                '<span class="card-label">métodos de limpeza</span>'
                "</div>"
            ),
            (
                '<div class="card">'
                '<span class="card-number">'
                f"{len(FILES)}"
                "</span>"
                '<span class="card-label">arquivos catalogados</span>'
                "</div>"
            ),
        ]
    )

    content = "".join(
        _html_table(
            title=title,
            section_id=section_id,
            frame=frame,
            description=description,
        )
        for (
            title,
            section_id,
            frame,
            description,
        )
        in sections
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metadados do piloto EtPilot</title>
<style>
:root {{
    --azul-escuro: #17365d;
    --azul: #4472c4;
    --azul-claro: #eef4fb;
    --cinza: #5b6573;
    --borda: #d9e2f3;
    --fundo: #f6f8fb;
}}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    color: #1f2937;
    background: var(--fundo);
    line-height: 1.45;
}}
header {{
    background: var(--azul-escuro);
    color: white;
    padding: 34px max(24px, calc((100vw - 1400px) / 2));
}}
header h1 {{
    margin: 0 0 8px;
    font-size: 30px;
}}
header p {{
    margin: 4px 0;
    max-width: 1000px;
}}
nav {{
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px max(24px, calc((100vw - 1400px) / 2));
    background: white;
    border-bottom: 1px solid var(--borda);
}}
nav a {{
    color: var(--azul-escuro);
    text-decoration: none;
    font-weight: 700;
    padding: 7px 10px;
    border-radius: 6px;
}}
nav a:hover {{
    background: var(--azul-claro);
}}
main {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 28px 24px 60px;
}}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin-bottom: 28px;
}}
.card {{
    background: white;
    border: 1px solid var(--borda);
    border-radius: 10px;
    padding: 18px;
}}
.card-number {{
    display: block;
    color: var(--azul-escuro);
    font-size: 28px;
    font-weight: 700;
}}
.card-label {{
    color: var(--cinza);
}}
section {{
    scroll-margin-top: 80px;
    background: white;
    margin: 20px 0;
    padding: 22px;
    border: 1px solid var(--borda);
    border-radius: 10px;
    overflow-x: auto;
}}
section h2 {{
    color: var(--azul-escuro);
    margin-top: 0;
}}
.metadata-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.metadata-table th {{
    position: sticky;
    top: 52px;
    background: var(--azul);
    color: white;
    text-align: left;
    padding: 9px;
    border: 1px solid #365f91;
}}
.metadata-table td {{
    vertical-align: top;
    padding: 8px;
    border: 1px solid var(--borda);
}}
.metadata-table tbody tr:nth-child(even) {{
    background: #f8fbff;
}}
footer {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 24px 36px;
    color: var(--cinza);
    font-size: 12px;
}}
code {{
    background: var(--azul-claro);
    padding: 2px 5px;
    border-radius: 4px;
}}
</style>
</head>
<body>
<header>
    <h1>Metadados do piloto EtPilot</h1>
    <p>Piloto computacional de mobilidade urbana, diferenciação socioespacial e entropia socioeconômica de trajetórias</p>
    <p>Documento gerado em UTC: {escape(generated_at)}</p>
</header>
<nav>{navigation}</nav>
<main>
    <div class="cards">{cards}</div>
    {content}
</main>
<footer>
    Todas as descrições deste relatório são apresentadas em português
</footer>
</body>
</html>
"""

    path.write_text(
        html,
        encoding="utf-8",
    )


def export_pilot_metadata(
    *,
    project_root: Path,
) -> dict[str, Path]:
    """Exporta os metadados do piloto em XLSX e HTML"""

    project_root = Path(
        project_root
    )

    output_dir = (
        project_root
        / "outputs"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    xlsx_path = (
        output_dir
        / "metadados_piloto.xlsx"
    )
    html_path = (
        output_dir
        / "metadados_piloto.html"
    )
    legacy_xml_path = (
        output_dir
        / "metadados_piloto.xml"
    )

    frames, generated_at = _build_metadata_frames(
        project_root=project_root,
        xlsx_path=xlsx_path,
        html_path=html_path,
    )

    _write_xlsx(
        path=xlsx_path,
        frames=frames,
    )
    _write_html(
        path=html_path,
        frames=frames,
        generated_at=generated_at,
    )

    if legacy_xml_path.exists():
        legacy_xml_path.unlink()

    return {
        "xlsx": xlsx_path,
        "html": html_path,
    }


def main() -> None:
    """Exporta os metadados usando a raiz atual do projeto"""

    project_root = Path(
        __file__
    ).resolve().parents[
        2
    ]

    paths = export_pilot_metadata(
        project_root=project_root
    )

    print(
        "Metadados do piloto exportados em:"
    )
    print(
        "  XLSX: "
        f"{paths['xlsx']}"
    )
    print(
        "  HTML: "
        f"{paths['html']}"
    )


if __name__ == "__main__":
    main()
