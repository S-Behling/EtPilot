"""Implementa o roteamento temporal por ônibus com acesso e egresso a pé

Usa uma tabela compacta de conexões GTFS ordenadas por horário de partida
Filtra somente os service_ids ativos na data consultada
Conecta origem e destino a múltiplas paradas pela rede de caminhada
Permite transferências entre viagens no mesmo stop_id
Preserva as arestas de caminhada do acesso e do egresso para integração futura
com o cálculo de uso da rede e H_soc
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import networkx as nx
import pandas as pd

from src.routing.multimodal_router import (
    node_path_to_edges,
)


ROUTE_OK = "ok"
ROUTE_NO_ACTIVE_SERVICE = "no_active_service"
ROUTE_NO_ACCESS_STOP = "no_access_stop"
ROUTE_NO_EGRESS_STOP = "no_egress_stop"
ROUTE_NO_TRANSIT_PATH = "no_transit_path"
ROUTE_INVALID_NODE = "invalid_node"


@dataclass
class TransitRouteResult:
    """Representa o resultado completo de uma viagem por transporte coletivo"""

    status: str
    service_date: str
    departure_time_s: int
    arrival_time_s: int | None = None
    total_travel_time_s: float | None = None

    access_stop_id: str | None = None
    egress_stop_id: str | None = None

    access_walk_distance_m: float | None = None
    access_walk_time_s: float | None = None
    initial_wait_time_s: float | None = None

    in_vehicle_time_s: float | None = None
    transfer_and_dwell_time_s: float | None = None
    n_boardings: int = 0
    n_transfers: int = 0

    egress_walk_distance_m: float | None = None
    egress_walk_time_s: float | None = None

    access_walk_edges: list[
        tuple[
            int,
            int,
            int,
        ]
    ] = field(
        default_factory=list
    )
    egress_walk_edges: list[
        tuple[
            int,
            int,
            int,
        ]
    ] = field(
        default_factory=list
    )

    transit_connection_ids: list[str] = field(
        default_factory=list
    )
    transit_trip_ids: list[str] = field(
        default_factory=list
    )
    transit_route_ids: list[str] = field(
        default_factory=list
    )


class TransitRouter:
    """Executa consultas temporais usando conexões GTFS e rede de caminhada"""

    def __init__(
        self,
        *,
        walk_graph,
        connectors: pd.DataFrame,
        connections: pd.DataFrame,
        service_dates: pd.DataFrame,
        walk_speed_m_s: float,
        max_access_walk_m: float,
        max_egress_walk_m: float,
        minimum_transfer_time_s: int,
        max_total_travel_time_s: int,
    ) -> None:
        """Inicializa e valida as estruturas necessárias ao roteamento"""

        if walk_speed_m_s <= 0:
            raise ValueError(
                "walk_speed_m_s precisa ser maior que zero"
            )

        if max_access_walk_m <= 0:
            raise ValueError(
                "max_access_walk_m precisa ser maior que zero"
            )

        if max_egress_walk_m <= 0:
            raise ValueError(
                "max_egress_walk_m precisa ser maior que zero"
            )

        if minimum_transfer_time_s < 0:
            raise ValueError(
                "minimum_transfer_time_s não pode ser negativo"
            )

        if max_total_travel_time_s <= 0:
            raise ValueError(
                "max_total_travel_time_s precisa ser maior que zero"
            )

        required_connectors = {
            "stop_id",
            "node_walk",
            "walk_connector_distance_m",
            "walk_connector_time_s",
        }
        required_connections = {
            "connection_id",
            "route_id",
            "service_id",
            "trip_id",
            "from_stop_id",
            "to_stop_id",
            "departure_seconds",
            "arrival_seconds",
            "in_vehicle_time_s",
        }
        required_service_dates = {
            "service_id",
            "service_date",
        }

        missing_connectors = (
            required_connectors
            - set(
                connectors.columns
            )
        )
        missing_connections = (
            required_connections
            - set(
                connections.columns
            )
        )
        missing_service_dates = (
            required_service_dates
            - set(
                service_dates.columns
            )
        )

        if missing_connectors:
            raise ValueError(
                "connectors não possui as colunas obrigatórias: "
                f"{sorted(missing_connectors)}"
            )

        if missing_connections:
            raise ValueError(
                "connections não possui as colunas obrigatórias: "
                f"{sorted(missing_connections)}"
            )

        if missing_service_dates:
            raise ValueError(
                "service_dates não possui as colunas obrigatórias: "
                f"{sorted(missing_service_dates)}"
            )

        self.walk_graph = walk_graph
        self.walk_speed_m_s = float(
            walk_speed_m_s
        )
        self.max_access_walk_m = float(
            max_access_walk_m
        )
        self.max_egress_walk_m = float(
            max_egress_walk_m
        )
        self.minimum_transfer_time_s = int(
            minimum_transfer_time_s
        )
        self.max_total_travel_time_s = int(
            max_total_travel_time_s
        )

        self.connectors = connectors.copy()
        self.connectors[
            "stop_id"
        ] = self.connectors[
            "stop_id"
        ].astype(
            "string"
        )
        self.connectors[
            "node_walk"
        ] = pd.to_numeric(
            self.connectors[
                "node_walk"
            ],
            errors="raise",
        ).astype(
            "Int64"
        )

        self.connections = connections.copy()
        self.connections[
            "service_id"
        ] = self.connections[
            "service_id"
        ].astype(
            "string"
        )
        self.connections[
            "trip_id"
        ] = self.connections[
            "trip_id"
        ].astype(
            "string"
        )
        self.connections[
            "route_id"
        ] = self.connections[
            "route_id"
        ].astype(
            "string"
        )
        self.connections[
            "from_stop_id"
        ] = self.connections[
            "from_stop_id"
        ].astype(
            "string"
        )
        self.connections[
            "to_stop_id"
        ] = self.connections[
            "to_stop_id"
        ].astype(
            "string"
        )
        self.connections[
            "departure_seconds"
        ] = pd.to_numeric(
            self.connections[
                "departure_seconds"
            ],
            errors="raise",
        ).astype(
            "Int64"
        )
        self.connections[
            "arrival_seconds"
        ] = pd.to_numeric(
            self.connections[
                "arrival_seconds"
            ],
            errors="raise",
        ).astype(
            "Int64"
        )

        self.service_dates = service_dates.copy()
        self.service_dates[
            "service_id"
        ] = self.service_dates[
            "service_id"
        ].astype(
            "string"
        )
        self.service_dates[
            "service_date"
        ] = pd.to_datetime(
            self.service_dates[
                "service_date"
            ]
        ).dt.normalize()

        self._stops_by_walk_node = (
            self.connectors.groupby(
                "node_walk",
                sort=False,
            )
        )
        self._active_connections_cache: dict[
            str,
            pd.DataFrame,
        ] = {}

    @classmethod
    def from_project(
        cls,
        *,
        project_root: Path,
        config: dict,
        walk_graph,
    ) -> "TransitRouter":
        """Carrega os produtos processados definidos na configuração do projeto"""

        gtfs_config = config[
            "transit"
        ][
            "gtfs"
        ]
        network_config = config[
            "transit"
        ][
            "network"
        ]
        routing_config = config[
            "transit"
        ][
            "routing"
        ]

        data_dir = (
            Path(
                project_root
            )
            / gtfs_config[
                "data_dir"
            ]
        )

        connectors = pd.read_parquet(
            data_dir
            / network_config[
                "stop_connectors_file"
            ]
        )
        connections = pd.read_parquet(
            data_dir
            / network_config[
                "connections_file"
            ]
        )
        service_dates = pd.read_parquet(
            data_dir
            / "service_dates_processed.parquet"
        )

        return cls(
            walk_graph=walk_graph,
            connectors=connectors,
            connections=connections,
            service_dates=service_dates,
            walk_speed_m_s=float(
                network_config[
                    "walk_speed_m_s"
                ]
            ),
            max_access_walk_m=float(
                routing_config[
                    "max_access_walk_m"
                ]
            ),
            max_egress_walk_m=float(
                routing_config[
                    "max_egress_walk_m"
                ]
            ),
            minimum_transfer_time_s=int(
                routing_config[
                    "minimum_transfer_time_s"
                ]
            ),
            max_total_travel_time_s=int(
                routing_config[
                    "max_total_travel_time_s"
                ]
            ),
        )

    def _active_connections(
        self,
        service_date,
    ) -> pd.DataFrame:
        """Retorna as conexões cujos service_ids estão ativos na data"""

        normalized = pd.Timestamp(
            service_date
        ).normalize()
        cache_key = normalized.date().isoformat()

        if cache_key in self._active_connections_cache:
            return self._active_connections_cache[
                cache_key
            ]

        active_ids = set(
            self.service_dates.loc[
                self.service_dates[
                    "service_date"
                ]
                == normalized,
                "service_id",
            ].astype(
                str
            )
        )

        if not active_ids:
            active = self.connections.iloc[
                0:0
            ].copy()
        else:
            active = (
                self.connections.loc[
                    self.connections[
                        "service_id"
                    ]
                    .astype(
                        str
                    )
                    .isin(
                        active_ids
                    )
                ]
                .sort_values(
                    [
                        "departure_seconds",
                        "arrival_seconds",
                        "trip_id",
                        "connection_id",
                    ]
                )
                .reset_index(
                    drop=True
                )
            )

        self._active_connections_cache[
            cache_key
        ] = active

        return active

    def _candidate_stops(
        self,
        *,
        node: int,
        maximum_walk_m: float,
        reverse: bool,
    ) -> dict[str, dict]:
        """Calcula paradas alcançáveis a pé e seus custos de acesso ou egresso"""

        graph = (
            self.walk_graph.reverse(
                copy=False
            )
            if reverse
            else self.walk_graph
        )

        distances = nx.single_source_dijkstra_path_length(
            graph,
            source=int(
                node
            ),
            cutoff=float(
                maximum_walk_m
            ),
            weight="length",
        )

        candidates: dict[
            str,
            dict,
        ] = {}

        for walk_node, network_distance_m in distances.items():
            walk_node_int = int(
                walk_node
            )

            if walk_node_int not in self._stops_by_walk_node.groups:
                continue

            stop_rows = self._stops_by_walk_node.get_group(
                walk_node_int
            )

            for row in stop_rows.itertuples(
                index=False
            ):
                connector_distance_m = float(
                    row.walk_connector_distance_m
                )
                total_distance_m = (
                    float(
                        network_distance_m
                    )
                    + connector_distance_m
                )

                if total_distance_m > maximum_walk_m:
                    continue

                total_time_s = (
                    float(
                        network_distance_m
                    )
                    / self.walk_speed_m_s
                    + float(
                        row.walk_connector_time_s
                    )
                )

                stop_id = str(
                    row.stop_id
                )

                existing = candidates.get(
                    stop_id
                )

                if (
                    existing is None
                    or total_time_s
                    < existing[
                        "walk_time_s"
                    ]
                ):
                    candidates[
                        stop_id
                    ] = {
                        "stop_id": stop_id,
                        "node_walk": walk_node_int,
                        "network_distance_m": float(
                            network_distance_m
                        ),
                        "walk_distance_m": total_distance_m,
                        "walk_time_s": total_time_s,
                    }

        return candidates

    def _walk_edges(
        self,
        *,
        origin_node: int,
        destination_node: int,
    ) -> tuple[
        list[
            tuple[
                int,
                int,
                int,
            ]
        ],
        float,
    ]:
        """Reconstrói as arestas exatas de uma caminhada na rede OSM"""

        if int(
            origin_node
        ) == int(
            destination_node
        ):
            return (
                [],
                0.0,
            )

        node_path = nx.shortest_path(
            self.walk_graph,
            source=int(
                origin_node
            ),
            target=int(
                destination_node
            ),
            weight="length",
            method="dijkstra",
        )

        return node_path_to_edges(
            self.walk_graph,
            list(
                node_path
            ),
            weight="length",
        )

    @staticmethod
    def _count_boardings(
        trip_ids: Iterable[str],
    ) -> int:
        """Conta embarques considerando mudanças sucessivas de trip_id"""

        previous = None
        count = 0

        for trip_id in trip_ids:
            trip_id = str(
                trip_id
            )

            if trip_id != previous:
                count += 1
                previous = trip_id

        return count

    def route(
        self,
        *,
        origin_walk_node: int,
        destination_walk_node: int,
        service_date,
        departure_time_s: int,
    ) -> TransitRouteResult:
        """Calcula a chegada mais cedo combinando caminhada e ônibus"""

        normalized_date = pd.Timestamp(
            service_date
        ).normalize()
        service_date_text = (
            normalized_date
            .date()
            .isoformat()
        )

        if (
            int(
                origin_walk_node
            )
            not in self.walk_graph
            or int(
                destination_walk_node
            )
            not in self.walk_graph
        ):
            return TransitRouteResult(
                status=ROUTE_INVALID_NODE,
                service_date=service_date_text,
                departure_time_s=int(
                    departure_time_s
                ),
            )

        active_connections = self._active_connections(
            normalized_date
        )

        if active_connections.empty:
            return TransitRouteResult(
                status=ROUTE_NO_ACTIVE_SERVICE,
                service_date=service_date_text,
                departure_time_s=int(
                    departure_time_s
                ),
            )

        access = self._candidate_stops(
            node=int(
                origin_walk_node
            ),
            maximum_walk_m=self.max_access_walk_m,
            reverse=False,
        )

        if not access:
            return TransitRouteResult(
                status=ROUTE_NO_ACCESS_STOP,
                service_date=service_date_text,
                departure_time_s=int(
                    departure_time_s
                ),
            )

        egress = self._candidate_stops(
            node=int(
                destination_walk_node
            ),
            maximum_walk_m=self.max_egress_walk_m,
            reverse=True,
        )

        if not egress:
            return TransitRouteResult(
                status=ROUTE_NO_EGRESS_STOP,
                service_date=service_date_text,
                departure_time_s=int(
                    departure_time_s
                ),
            )

        stop_arrival: dict[
            str,
            float,
        ] = {}
        stop_paths: dict[
            str,
            tuple[
                int,
                ...,
            ],
        ] = {}

        for stop_id, candidate in access.items():
            stop_arrival[
                stop_id
            ] = (
                float(
                    departure_time_s
                )
                + float(
                    candidate[
                        "walk_time_s"
                    ]
                )
            )
            stop_paths[
                stop_id
            ] = tuple()

        reachable_trip_paths: dict[
            str,
            tuple[
                int,
                ...,
            ],
        ] = {}

        horizon = (
            int(
                departure_time_s
            )
            + self.max_total_travel_time_s
        )

        for connection_index, row in enumerate(
            active_connections.itertuples(
                index=False
            )
        ):
            connection_departure = int(
                row.departure_seconds
            )

            if connection_departure < departure_time_s:
                continue

            if connection_departure > horizon:
                break

            from_stop_id = str(
                row.from_stop_id
            )
            to_stop_id = str(
                row.to_stop_id
            )
            trip_id = str(
                row.trip_id
            )

            trip_path = reachable_trip_paths.get(
                trip_id
            )

            if trip_path is None:
                arrival_at_stop = stop_arrival.get(
                    from_stop_id
                )

                if arrival_at_stop is None:
                    continue

                prior_path = stop_paths.get(
                    from_stop_id,
                    tuple(),
                )

                transfer_buffer = (
                    self.minimum_transfer_time_s
                    if prior_path
                    else 0
                )

                if (
                    arrival_at_stop
                    + transfer_buffer
                    > connection_departure
                ):
                    continue

                trip_path = (
                    *prior_path,
                    connection_index,
                )
            else:
                trip_path = (
                    *trip_path,
                    connection_index,
                )

            reachable_trip_paths[
                trip_id
            ] = trip_path

            connection_arrival = float(
                row.arrival_seconds
            )
            current_best = stop_arrival.get(
                to_stop_id
            )

            if (
                current_best is None
                or connection_arrival
                < current_best
            ):
                stop_arrival[
                    to_stop_id
                ] = connection_arrival
                stop_paths[
                    to_stop_id
                ] = trip_path

        best_stop_id = None
        best_arrival_time = None
        best_total_time = None

        for stop_id, candidate in egress.items():
            path = stop_paths.get(
                stop_id
            )

            if not path:
                continue

            transit_arrival = stop_arrival.get(
                stop_id
            )

            if transit_arrival is None:
                continue

            final_arrival = (
                float(
                    transit_arrival
                )
                + float(
                    candidate[
                        "walk_time_s"
                    ]
                )
            )
            total_time = (
                final_arrival
                - float(
                    departure_time_s
                )
            )

            if (
                total_time < 0
                or total_time
                > self.max_total_travel_time_s
            ):
                continue

            if (
                best_total_time is None
                or total_time
                < best_total_time
            ):
                best_stop_id = stop_id
                best_arrival_time = final_arrival
                best_total_time = total_time

        if best_stop_id is None:
            return TransitRouteResult(
                status=ROUTE_NO_TRANSIT_PATH,
                service_date=service_date_text,
                departure_time_s=int(
                    departure_time_s
                ),
            )

        path_indices = stop_paths[
            best_stop_id
        ]

        path_rows = active_connections.iloc[
            list(
                path_indices
            )
        ]

        access_stop_id = str(
            path_rows.iloc[
                0
            ][
                "from_stop_id"
            ]
        )
        egress_stop_id = str(
            best_stop_id
        )

        access_candidate = access[
            access_stop_id
        ]
        egress_candidate = egress[
            egress_stop_id
        ]

        access_edges, access_network_distance = self._walk_edges(
            origin_node=int(
                origin_walk_node
            ),
            destination_node=int(
                access_candidate[
                    "node_walk"
                ]
            ),
        )
        egress_edges, egress_network_distance = self._walk_edges(
            origin_node=int(
                egress_candidate[
                    "node_walk"
                ]
            ),
            destination_node=int(
                destination_walk_node
            ),
        )

        access_distance = (
            float(
                access_network_distance
            )
            + (
                float(
                    access_candidate[
                        "walk_distance_m"
                    ]
                )
                - float(
                    access_candidate[
                        "network_distance_m"
                    ]
                )
            )
        )
        egress_distance = (
            float(
                egress_network_distance
            )
            + (
                float(
                    egress_candidate[
                        "walk_distance_m"
                    ]
                )
                - float(
                    egress_candidate[
                        "network_distance_m"
                    ]
                )
            )
        )

        access_walk_time = (
            access_distance
            / self.walk_speed_m_s
        )
        egress_walk_time = (
            egress_distance
            / self.walk_speed_m_s
        )

        first_departure = float(
            path_rows.iloc[
                0
            ][
                "departure_seconds"
            ]
        )
        last_arrival = float(
            path_rows.iloc[
                -1
            ][
                "arrival_seconds"
            ]
        )

        initial_wait_time = max(
            0.0,
            first_departure
            - (
                float(
                    departure_time_s
                )
                + access_walk_time
            ),
        )

        in_vehicle_time = float(
            path_rows[
                "in_vehicle_time_s"
            ].astype(
                float
            ).sum()
        )

        transit_elapsed = (
            last_arrival
            - first_departure
        )
        transfer_and_dwell_time = max(
            0.0,
            transit_elapsed
            - in_vehicle_time
        )

        trip_ids = (
            path_rows[
                "trip_id"
            ]
            .astype(
                str
            )
            .tolist()
        )
        route_ids = (
            path_rows[
                "route_id"
            ]
            .astype(
                str
            )
            .tolist()
        )
        connection_ids = (
            path_rows[
                "connection_id"
            ]
            .astype(
                str
            )
            .tolist()
        )

        n_boardings = self._count_boardings(
            trip_ids
        )

        return TransitRouteResult(
            status=ROUTE_OK,
            service_date=service_date_text,
            departure_time_s=int(
                departure_time_s
            ),
            arrival_time_s=int(
                round(
                    float(
                        best_arrival_time
                    )
                )
            ),
            total_travel_time_s=float(
                best_total_time
            ),
            access_stop_id=access_stop_id,
            egress_stop_id=egress_stop_id,
            access_walk_distance_m=access_distance,
            access_walk_time_s=access_walk_time,
            initial_wait_time_s=initial_wait_time,
            in_vehicle_time_s=in_vehicle_time,
            transfer_and_dwell_time_s=transfer_and_dwell_time,
            n_boardings=n_boardings,
            n_transfers=max(
                0,
                n_boardings
                - 1,
            ),
            egress_walk_distance_m=egress_distance,
            egress_walk_time_s=egress_walk_time,
            access_walk_edges=access_edges,
            egress_walk_edges=egress_edges,
            transit_connection_ids=connection_ids,
            transit_trip_ids=trip_ids,
            transit_route_ids=route_ids,
        )
