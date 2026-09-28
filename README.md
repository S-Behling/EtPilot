# Urban Complexity

Python library and research pipeline for the analysis of urban complexity, mobility, and socio-spatial segregation.

This project is part of a broader research initiative that investigates the relationship between urban form, mobility patterns, and segregation through graph theory, information theory, and computational modeling.

The first phase of the project focuses on the implementation and validation of the **Trajectory Entropy (ET)** metric using a pilot area in Porto Alegre, Brazil.

---

## Objectives

- Download and process urban street networks from OpenStreetMap.
- Characterize transportation infrastructure.
- Generate and analyze movement trajectories.
- Compute Trajectory Entropy (ET).
- Support future implementations of segregation and complexity indicators.

---

## Project Structure

```text
urban-complexity/

│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── results/
│   └── graph/
│
├── notebooks/
│   ├── 01_download_network.ipynb
│   ├── 02_explore_network.ipynb
│   ├── 03_characterize_network.ipynb
│   └── ...
│
├── src/
│   ├── downloads/
│   │   └── downloadGTFS.py
│   ├── network.py
│   ├── classification.py
│   ├── visualization.py
│   ├── origins.py
│   └── metrics/
│       ├── entropy.py
│       └── ...
├── config/
│   ├── config.json
│   ├── road_classification.json
│   └── ...
│
├── requirements.txt
├── README.md
├── anotacoes.md
└── .gitignore

```

---

## Environment

Create a virtual environment

```bash
python -m venv .venv
```

Activate

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

## Main Libraries

- OSMnx
- GeoPandas
- NetworkX
- Shapely
- Pandas
- NumPy
- Matplotlib

Additional libraries will be incorporated as the project evolves.

---

## Workflow

The project is organized as a sequential research pipeline:

1. Download mode-specific OSM networks (car, walk, bike)
2. Generate socioeconomic origins and associate modal nodes
3. Generate/classify CNEFE destinations and associate modal nodes
4. Generate synthetic agents
5. Assign origins, purposes, destinations and travel modes
6. Select the routing network according to the chosen mode
7. Compute routes and edge usage
8. Harmonize the complete modal networks into common physical analysis segments
9. Compute segment statistics and normalized socioeconomic trajectory entropy (H_soc)
10. Compare experimental scenarios
11. Generate spatial maps of H_soc and paired delta_H_soc

---

## External data downloads

Keep download code under `src/downloads/` and keep downloaded files under
`data/`. Store the GTFS feed directly in `data/gtfs/` without an
additional `raw/` level.

Current structure:

```text
src/
├── downloads/
│   ├── __init__.py
│   └── downloadGTFS.py
└── transit/
    ├── __init__.py
    └── processGTFS.py

data/
└── gtfs/
    ├── porto_alegre_gtfs.zip
    ├── gtfs_download_metadata.json
    ├── agency_processed.parquet
    ├── routes_processed.parquet
    ├── trips_processed.parquet
    ├── stop_times_processed.parquet
    ├── service_dates_processed.parquet
    ├── stops_processed.gpkg
    ├── shapes_processed.gpkg
    ├── gtfs_processed_inventory.csv
    └── gtfs_processed_summary.csv
```

Run the official Porto Alegre GTFS download with:

```bash
python -m src.downloads.downloadGTFS
```

The downloader reads the official EPTC source URL from `config/config.json`,
stores the ZIP directly in `data/gtfs/`, and records the download timestamp,
file size, source URL, and SHA-256 hash in `gtfs_download_metadata.json`.

Keep later processed GTFS products in the same `data/gtfs/` directory and
make their processed state explicit in the filename, for example
`porto_alegre_gtfs_processed.gpkg` or
`transit_network_processed.parquet`.

Process the downloaded feed with:

```bash
python -m src.transit.processGTFS
```

The processor reads the original ZIP directly without creating an additional
`raw/` directory. It validates the core GTFS relationships, converts GTFS
times such as `25:10:00` to seconds from the beginning of the service day,
expands active service dates, projects stops to the study CRS, and builds
projected line geometries from `shapes.txt` when the feed provides shapes.

When intermediate `stop_times` records omit arrival and departure times, the
processor preserves the original missing-value flags and creates explicit
processed estimates between known temporal anchors. It first uses
`shape_dist_traveled` when that field is complete and monotonic within the
trip. When the feed does not provide usable stop-level shape distances, it
projects the stops onto the processed `shapes.txt` geometry and refines the
interpolation with distance along the shape whenever the projected sequence is
monotonic. It falls back to `stop_sequence` only where neither distance-based
method can be applied safely. The processed table records
`time_interpolated`, `time_interpolation_method`, and `shape_position_m` so
estimated schedule times remain distinguishable from values supplied by the
GTFS producer.

The current official EPTC GTFS source represents the Porto Alegre bus mode.
Keep the internal `transit` label for the pilot while documenting this bus
scope explicitly. Add other transit systems through additional feeds or
network layers instead of assuming that this EPTC feed represents every
public-transport mode.

## Transit network preparation

After processing the GTFS feed, connect the 5,909 EPTC stops to the walking
network and create the scheduled stop-to-stop connection table with:

```bash
python -m src.transit.buildTransitNetwork
```

This stage does not build a fully time-expanded graph. It keeps a compact
connection table that can support a timetable routing algorithm in the next
stage.

The generated products remain under `data/gtfs/`:

```text
stops_walk_connected_processed.gpkg
transit_stop_walk_connectors_processed.parquet
transit_connections_processed.parquet
transit_topology_processed.parquet
transit_service_day_profile_processed.csv
transit_network_summary.csv
```

Each stop receives the nearest `node_walk`, the connector distance in metres,
and the connector time in seconds using the provisional walking speed defined
in `config/config.json`. Each GTFS trip is decomposed into directed temporal
connections between consecutive stops with departure time, arrival time,
in-vehicle duration, interpolation flags, and shape distance when available.

The service-day profile counts scheduled trips by date. The current strategy
selects the date with the largest number of scheduled trips as the
representative service date for later routing diagnostics.

## Pilot metadata documentation

Export the consolidated methodological documentation in two complementary
formats:

```text
outputs/metadados_piloto.xlsx
outputs/metadados_piloto.html
```

The XLSX workbook separates the documentation into Portuguese worksheets for
the summary, main variables, configuration parameters, analysis methods,
statistics, cleaning methods, and generated files.

The HTML report presents the same content as a navigable document with section
links and tabular summaries.

Both outputs contain Portuguese descriptions for:

- main variables and their units;
- current configuration parameters;
- analysis methods;
- statistics;
- cleaning and validation methods;
- generated files and their purpose.

The metadata files are refreshed by `src.transit.buildTransitNetwork` and by
the main pilot simulation. They can also be generated directly with:

```bash
python -m src.reporting.exportPilotMetadata
```

The exporter removes the former `outputs/metadados_piloto.xml` file when it
exists so that XLSX and HTML remain the canonical metadata formats.

## Timetable transit routing

The pilot now includes a standalone timetable router in:

```text
src/transit/routeTransit.py
```

The router combines:

```text
origin walk node
    ↓
walking access to one of several candidate stops
    ↓
scheduled GTFS connections
    ↓
same-stop transfers between trips
    ↓
walking egress from one of several candidate stops
    ↓
destination walk node
```

The search scans only the `service_id` values active on the requested date
and seeks the earliest final arrival within the configured travel-time
horizon.

Current provisional routing parameters are defined in `config/config.json`:

```text
max_access_walk_m
max_egress_walk_m
minimum_transfer_time_s
max_total_travel_time_s
```

These values are technical pilot assumptions and are not treated as
empirically calibrated travel-demand parameters.

Walking access and egress preserve the exact OSM walk edges used by the
shortest path so they can later be incorporated into physical-segment usage.
The transit portion preserves the ordered GTFS connection, trip, and route
identifiers.

At this stage transfers are implemented between trips that share the same
`stop_id`. Walking transfers between distinct nearby stops remain outside
the router until the same-stop implementation is validated.

Run the real-data diagnostic with:

```bash
python -m src.transit.validateTransitRouting
```

The diagnostic samples reproducible origin-destination pairs from the current
pilot bases, uses the representative GTFS service date and configured
departure time, and writes:

```text
outputs/pilot/transit_routing_diagnostics.csv
```

The console output reports units and percentages for routing coverage, travel
times, walking distances, waiting time, and transfers.

## Multimodal network

The first routing implementation uses three OSM networks:

- `car` → OSMnx `network_type="drive"`
- `walk` → OSMnx `network_type="walk"`
- `bike` → OSMnx `network_type="bike"`

Origins and destinations are spatial entities independent of a single graph.
Each point stores a mode-specific nearest node:

- `node_car`
- `node_walk`
- `node_bike`

After the agent chooses a travel mode, select the corresponding origin and
destination nodes for routing. Exclude transit from this first routing stage
and plan it as a GTFS-based network.

Build the common analysis network from the complete walk, bike and car
graphs, not from the sampled trajectories. Use walk as the initial reference,
map bike and car edges first by exact OSM equivalence and then by geometric
overlap, and preserve unmatched edges as exclusive segments. Keep this layer
independent of agent count, seed and scenario so that `analysis_segment_id`
remains stable across simulations.

To prepare the multimodal data:

```bash
# 1. Run notebooks/01_download_network.ipynb
# 2. Then update origins and rebuild CNEFE destinations:
python -m src.network.prepare_multimodal_data
```


## Segment statistics and H_soc

Aggregate the harmonized edge usage by `analysis_segment_id`. Keep passage
volume and distinct-agent volume separate. Use one observation per distinct
agent and segment to compute socioeconomic composition so that 1:N network
harmonization does not artificially increase the social weight of an agent.

Compute:

- `n_passages`: number of harmonized traversal records;
- `n_agents`: number of distinct agents using the segment;
- `n_low`, `n_middle`, `n_high`: distinct agents by income group;
- `p_low`, `p_middle`, `p_high`: income-group proportions;
- `income_groups_present`: number of observed income groups;
- `H_soc`: normalized Shannon entropy of the income-group composition;
- `sufficient_flow`: flag the configured minimum number of agents;
- `flow_ge_2`, `flow_ge_3`, `flow_ge_5`, `flow_ge_10`: preserve
  sensitivity thresholds for later robustness analysis.

Calculate normalized entropy as:

```text
H_soc = -sum(p_g * ln(p_g)) / ln(K)
```

Use `K=3` for the current low/middle/high income classification. Interpret
`H_soc=0` as observed concentration in a single group and `H_soc=1` as
equal representation of all three groups. Preserve `H_soc=NaN` for unused
segments; do not convert absence of observed flow into social homogeneity.

Because the normalized expression divides by the maximum entropy computed
with the same logarithm base, the normalized `H_soc` is invariant to the
choice of logarithm base. Keep the legacy `analysis.entropy_base` setting
for compatibility with older exploratory code, but do not use it to alter
the normalized `H_soc` produced by this pipeline.

Interpret `H_soc` together with `n_agents`, `n_passages`, and the flow
threshold flags. Treat the current 100-agent run as a pipeline validation
exercise rather than an empirical estimate of urban segregation.

Treat `H_soc` as a measure of the socioeconomic diversity of trajectories
using a physical street segment. Do not interpret it as direct interpersonal
contact, interaction, or as a complete segregation index by itself.

The pilot writes:

```text
outputs/pilot/
├── segment_statistics_baseline.csv
├── segment_statistics_differentiated.csv
├── segment_statistics_all_scenarios.csv
├── segment_metrics_baseline.gpkg
└── segment_metrics_differentiated.gpkg
```

Keep all physical analysis segments in each GeoPackage. Fill count fields with
zero for unused segments and preserve proportions and `H_soc` as null values
when no agent uses the segment.


## Paired scenario comparison

Compare baseline and differentiated by the same `analysis_segment_id`. Do not
compare scenario-level averages as if they represented the same spatial
sample.

Preserve four spatial states in the comparison layer:

- `used_both`: use the segment in both scenarios;
- `baseline_only`: use the segment only in baseline;
- `differentiated_only`: use the segment only in differentiated;
- `unused_both`: keep the physical segment in the GeoPackage even when
  neither scenario uses it.

Calculate:

```text
delta_H_soc = H_soc_differentiated - H_soc_baseline
delta_n_agents = n_agents_differentiated - n_agents_baseline
delta_n_passages = n_passages_differentiated - n_passages_baseline
```

Calculate `delta_H_soc` only when both scenarios contain an observed
`H_soc` on the same physical segment. Flag paired support with
`sufficient_flow_both` and with `flow_ge_2_both`, `flow_ge_3_both`,
`flow_ge_5_both`, and `flow_ge_10_both`.

Interpret a positive `delta_H_soc` only as an increase in the observed
socioeconomic diversity of trajectories on that segment. Interpret a negative
value only as a reduction. Do not label either direction as better or worse.

Write:

```text
outputs/pilot/
├── segment_scenario_comparison.csv
├── segment_scenario_comparison_summary.csv
└── segment_scenario_comparison.gpkg
```

Use the CSV for statistical diagnostics and the GeoPackage for paired spatial
comparison and mapping.


## Distance-sensitive mode choice

Use the Euclidean origin-destination distance selected during destination
choice as a pre-routing impedance for mode choice. Store it separately as
`od_distance_m` and keep `travel_distance_m` for the routed network
distance.

Adjust each available modal prior with:

```text
adjusted_weight_m = base_probability_m * exp(-beta_m * distance_km)
```

Apply the same distance-response parameters in baseline and differentiated so
that the experimental difference remains in the behavioral priors rather than
in a different distance function.

Use the current pilot parameters as provisional constraints:

```text
walk    beta=0.55 /km   maximum OD distance=6 km
bike    beta=0.12 /km   maximum OD distance=20 km
car     beta=0.00 /km   no maximum
transit beta=0.03 /km   no maximum, reserved for the future GTFS stage
```

Treat these values as technical pilot parameters rather than empirically
estimated travel-demand coefficients. Replace or calibrate them with an
appropriate observed mobility source before treating modal outputs as
empirical estimates.

The purpose of this stage is to remove implausible distance-independent active
mode assignments while preserving a transparent and configurable experimental
rule.

## Pilot maps

Generate six static PNG maps with the same physical network extent and fixed
metric scales so that visual differences are not created by automatic
rescaling between figures.

Use `H_soc` with the fixed interval [0, 1] and use `delta_H_soc` with the
fixed interval [-1, 1] centered on zero.

Generate one map with all observed or comparable segments and one map
restricted to the configured flow support for each metric:

```text
outputs/pilot/maps/
├── h_soc_baseline_all.png
├── h_soc_baseline_supported.png
├── h_soc_differentiated_all.png
├── h_soc_differentiated_supported.png
├── delta_h_soc_all.png
├── delta_h_soc_supported.png
└── map_manifest.csv
```

The supported H_soc maps highlight only segments with
`sufficient_flow=True`. The supported delta map highlights only segments
with `sufficient_flow_both=True`. The complete physical network remains in
the background as a spatial reference.

The `map_manifest.csv` file includes `description_pt`, a short Portuguese
description of what each generated image displays.

Treat the current maps as diagnostic outputs while the experiment still uses
100 agents. Use them to validate spatial behavior and the comparison pipeline,
not as final empirical representations of segregation.

## Current Status

Current implementation:

- ✔ Separate car, walk and bike network download
- ✔ Socioeconomic origin generation
- ✔ CNEFE destination classification
- ✔ Synthetic agent population
- ✔ Experimental baseline/differentiated scenarios
- ✔ Purpose, destination and mode choice
- ✔ Mode-specific origin/destination node resolution
- ✔ Multimodal shortest-path routing
- ✔ Agent × edge usage tables
- ✔ Common physical analysis segments from complete modal networks
- ✔ Segment-level passage and distinct-agent statistics
- ✔ Socioeconomic composition by income group
- ✔ Normalized socioeconomic trajectory entropy (H_soc)
- ✔ Flow-threshold flags for sensitivity analysis
- ✔ GeoPackage outputs with metrics attached to the complete analysis network
- ✔ Paired baseline × differentiated comparison by analysis_segment_id
- ✔ Paired flow-threshold flags and delta_H_soc
- ✔ Static H_soc maps with fixed [0, 1] scale
- ✔ Static paired delta_H_soc maps with fixed [-1, 1] scale
- ✔ Supported-flow map variants and map manifest
- ✔ Distance-sensitive mode choice using pre-routing OD distance
- ✔ Fixed distance-response rule across baseline and differentiated
- ✔ GTFS downloader with direct storage under data/gtfs
- ✔ GTFS validation and preprocessing code
- ✔ Service-date expansion and stop/shape processing logic
- ✔ Validation of the downloaded EPTC GTFS feed
- ✔ Stop-to-walking-network association code
- ✔ Scheduled GTFS connection-table construction
- ✔ Standalone timetable transit router with walking access and egress
- ✔ Same-stop transfer logic with configurable transfer time
- ✔ Real-data transit routing diagnostic
- ✔ Pilot metadata export in XLSX and HTML

In progress:

- Local validation of the stop connectors and scheduled connection table
- Local validation of the timetable router on real pilot OD pairs
- Integration of transit into the main agent simulation
- Sensitivity analysis with larger synthetic populations
- Repeated paired runs with multiple seeds
- Empirical calibration of provisional modal-distance parameters

## Remaining work to close the pilot

Complete the pilot in this order:

1. validate the scheduled GTFS connection table, stop-to-walk connectors and
   real-data timetable routing diagnostics;
2. integrate transit into the main agent simulation without redistributing the
   transit probability to car, bicycle or walking;
3. validate the provisional distance-sensitive mode rule against routed
   distances and replace its parameters with empirical calibration when an
   appropriate observed mobility source is selected;
4. increase the synthetic population progressively and inspect convergence of
   segment coverage, flow support, and `H_soc`;
5. repeat paired baseline × differentiated runs across multiple seeds and
   summarize the stability of `delta_H_soc`;
6. run sensitivity checks for the flow thresholds and for the geometric
   harmonization parameters;
7. consolidate final pilot tables, maps, diagnostics, limitations, and
   reproducibility instructions.

The current GTFS integration covers the EPTC bus feed. Add other public
transport systems as separate feeds or network layers when required by the
research scope.

Future work:

- Additional public transport feeds beyond EPTC buses
- Segregation indicators
- Accessibility analysis
- Machine Learning
- Space-time analysis

---

## References

The implementation is based on concepts from:

- Shannon (1948)
- Kwan (1998, 2013)
- Netto et al.
- Boeing (2018)
- Network Science
- OSMnx

---

## License

Research project.

For academic use only.
