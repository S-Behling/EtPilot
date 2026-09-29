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

python -m src.analysis.article_v01 --workers 2
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

This stage does not build a fully time-expanded graph. It keeps compact
temporal connection tables and also constructs the stable physical GTFS layer
used by the integrated timetable router and H_soc pipeline.

The generated products remain under `data/gtfs/`:

```text
stops_walk_connected_processed.gpkg
transit_stop_walk_connectors_processed.parquet
transit_connections_processed.parquet
transit_connections_routable_processed.parquet
transit_connections_spatial_routable_processed.parquet
transit_physical_edges_processed.gpkg
transit_physical_edge_diagnostics_processed.csv
transit_connection_to_physical_edge_processed.parquet
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

## GTFS temporal reconstruction for routing

The temporal diagnostics show that most EPTC trips contain only a small number
of original timepoints. The processing pipeline therefore keeps the published
timepoints as anchors and regularizes only the intermediate estimated times.

For each span between two original timepoints, the processor:

```text
preserves the original start and end times
        ↓
uses strictly increasing shape position when available
        ↓
falls back to stop_sequence when shape progress is not strictly increasing
        ↓
distributes integer seconds across the intermediate connections
        ↓
keeps at least the configured minimum interval when mathematically feasible
```

The current technical minimum is defined in `config/config.json` as
`transit.gtfs.temporal_reconstruction.minimum_interval_s`.

Trips for which the published anchor interval is too short to assign the
minimum positive interval to every consecutive stop are not modified
artificially. They are flagged with
`temporal_regularization_feasible=False`.

The network preparation preserves three separate connection products:

```text
data/gtfs/transit_connections_processed.parquet
data/gtfs/transit_connections_routable_processed.parquet
data/gtfs/transit_connections_spatial_routable_processed.parquet
```

The first keeps the complete processed feed for auditing and diagnostics. The
second applies the temporal quality filter. The third keeps only temporally
valid connections that also belong to a valid physical GTFS edge and is the
table used by the integrated timetable router. Invalid physical geometries
remain documented in the physical-edge diagnostics rather than entering the
spatial analysis silently.

The quality decision for every `trip_id` is stored in:

```text
data/gtfs/transit_trip_quality_processed.csv
```

The implied-speed ceiling is a conservative technical anomaly filter for the
pilot rather than an empirical estimate of normal bus operating speed.

## GTFS temporal quality diagnostics

The EPTC feed contains a large share of interpolated stop times. Evaluate
temporal consistency at the trip level with:

```bash
python -m src.transit.validateGTFSTemporalQuality
```

The diagnostic writes:

```text
outputs/pilot/gtfs_trip_temporal_quality.csv
```

Each `trip_id` is summarized with the number of stops, number of original
timepoints, scheduled duration, number and share of zero-duration connections,
connection-time statistics, shape length when available, and implied average
speed from the shape length and scheduled duration.

The console report emphasizes descriptive diagnostics rather than filtering
trips automatically. It reports trip-duration percentiles, prevalence of
zero-duration connections, and the distribution of implied shape speeds.
These results support the quality filter used by the transit network and
remain part of the audit trail after transit enters `run_pilot`.

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
shortest path and enter the same physical-segment usage table as the other
trajectories. The transit portion preserves the ordered GTFS connection, trip,
and route identifiers.

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

The road and active-mode portion of the main agent pipeline uses three OSM
networks:

- `car` → OSMnx `network_type="drive"`
- `walk` → OSMnx `network_type="walk"`
- `bike` → OSMnx `network_type="bike"`

Transit now uses the GTFS timetable router inside `run_pilot`. The modal
choice includes `walk`, `bike`, `car`, and `transit` without
redistributing the transit probability to the three OSM-only modes.

Origins and destinations are spatial entities independent of a single graph.
Each point stores a mode-specific nearest node:

- `node_car`
- `node_walk`
- `node_bike`

For the three OSM modes, select the corresponding origin and destination nodes
after mode choice. Transit reuses `node_walk` as the spatial origin and
destination for access and egress and uses the quality-filtered GTFS
connection table for the bus portion of the trip.

Build the common analysis network from complete modal sources rather than from
sampled trajectories. Use walk as the initial OSM reference, map bike and car
first by exact OSM equivalence and then by geometric overlap, and preserve
unmatched OSM edges as exclusive segments.

Transit contributes a fourth physical source. During
`python -m src.transit.buildTransitNetwork`, all spatially valid routable GTFS
connections are grouped into stable stop-to-stop physical edges that do not
depend on schedule time, agent count, seed, or scenario. The products are:

```text
data/gtfs/transit_connections_spatial_routable_processed.parquet
data/gtfs/transit_physical_edges_processed.gpkg
data/gtfs/transit_physical_edge_diagnostics_processed.csv
data/gtfs/transit_connection_to_physical_edge_processed.parquet
```

The connection-to-physical-edge table allows repeated scheduled trips over the
same shape segment to share the same `transit_physical_edge_id`.

During `run_pilot`, the complete GTFS physical network is integrated after
the OSM walk-bike-car layer. The primary stage searches physical segments
supported by the car network. The fallback searches the complete OSM physical
layer. If a valid GTFS physical edge still has no safe correspondence, the
pipeline creates a new exclusive transit `analysis_segment_id` instead of
removing agents.

This keeps the physical layer independent of the N=100 sample and preserves
GTFS-only analytical geometry when no safe OSM correspondence is available.
An exclusive transit segment does not by itself prove that the real street is
a bus-only corridor: it may represent dedicated infrastructure, an OSM
coverage difference, or a geometric disagreement between GTFS and OSM.

For transit trips, preserve three leg types in the usage table:

```text
access_walk
in_vehicle
egress_walk
```

The walking legs keep `mode=transit` as the trip mode but use
`mapping_mode=walk` to reuse the existing walk-edge harmonization. The bus
leg uses the stable `transit_physical_edge_id` produced before simulation, so
every observed transit passage refers to a physical edge that already belongs
to the complete common network.

The integrated pilot writes the transit harmonization audit files:

```text
outputs/pilot/transit_physical_edge_to_analysis_segment.csv
outputs/pilot/transit_physical_match_diagnostics.csv
outputs/pilot/transit_physical_network_summary.csv
```

The summary separates primary matches, fallback matches, and exclusive transit
segments. A used transit physical edge without `analysis_segment_id` is
treated as an internal consistency error rather than as a reason to exclude an
agent.

To prepare the multimodal data:

```bash
# 1. Run notebooks/01_download_network.ipynb
# 2. Then update origins and rebuild CNEFE destinations:
python -m src.network.prepare_multimodal_data
```


## Transit trip outlier control

The pilot preserves every routed agent in the scenario tables while allowing
technically extreme transit trajectories to be excluded from the spatial
analysis before edge usage, segment statistics and H_soc are calculated.

The current provisional rule pools successful transit trips from baseline and
differentiated so both scenarios use the same thresholds. It evaluates both
`travel_distance_m` and `route_to_od_ratio = travel_distance_m / od_distance_m`
with the upper Tukey outer fence `Q3 + 3 × IQR`.

A trip is flagged when routed distance exceeds its upper outer fence, or when
the route-to-OD ratio exceeds its upper outer fence while routed distance is
also above the third quartile. This keeps the filter conservative for short
trips with very small OD distances.

With paired exclusion enabled, the same `agent_id` is excluded from
trajectory analysis in both scenarios when either scenario contains a direct
outlier.

The routed records remain in the agent tables with `analysis_included=False`
and an explicit exclusion reason. The complete pre-filter trajectory usage is
also preserved separately from the filtered analytical usage.

```text
outputs/pilot/edge_usage_routed_baseline.csv
outputs/pilot/edge_usage_routed_differentiated.csv
outputs/pilot/edge_usage_routed_all_scenarios.csv
outputs/pilot/outlier_exclusions.csv
outputs/pilot/outlier_filter_summary.csv
```

The regular `edge_usage_baseline.csv` and `edge_usage_differentiated.csv`
files contain the post-filter trajectory set that enters spatial
harmonization.
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
transit beta=0.03 /km   no maximum, routed with the integrated GTFS network
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
- ✔ GTFS trip-level temporal quality diagnostic
- ✔ Positive-interval reconstruction between published GTFS timepoints
- ✔ Separate complete, temporal-routable and spatial-routable GTFS connection tables
- ✔ Stable full GTFS physical-edge layer independent of N, seed and scenario
- ✔ Transit included in the main agent mode choice and routing pipeline
- ✔ Transit access and egress represented on the walk network
- ✔ Full GTFS physical network integrated into the common analysis layer
- ✔ Unmatched valid GTFS edges preserved as GTFS-only analytical segments
- ✔ Transit included in segment-level modal counts and H_soc trajectory usage
- ✔ Pilot metadata export in XLSX and HTML

In progress:

- Local validation of the full GTFS physical network integration in the N=100 pilot
- Sensitivity analysis of the provisional GTFS-to-OSM matching parameters
- Final N=100 sensitivity battery with repeated paired runs across multiple seeds
- Local sensitivity of destination-distance and modal-distance parameters
- Decomposition of destination/purpose effects from differentiated modal probabilities

## Final pilot sensitivity with fixed N=100

The pilot now fixes **N=100 agents per realization** as an operational choice
because larger populations have a high computational cost. This must not be
reported as evidence that N=100 is a converged population size.

The final sensitivity battery is defined in `config/config.json` under
`analysis.final_pilot_sensitivity` and currently uses:

```text
N = 100 agents per realization
nominal seeds = 11, 23, 42, 73, 101
reference seed for local perturbations = 42
primary flow-support threshold = n_agents >= 5
reported support thresholds = 2, 3, 5, 10
```

Run the complete battery with:

```bash
python -m src.analysis.final_pilot_sensitivity --resume
```

The runner evaluates five nominal independent realizations and one-at-a-time
local perturbations of the behavioral parameters:

```text
destination distance decay: 0.75 x, 1.00 x, 1.25 x
modal distance decay:       0.75 x, 1.00 x, 1.25 x
decomposition: differentiated purpose/destination with homogenized mode shares for all nominal seeds
```

The nominal 1.00 x, seed=42 run is reused as the reference. When available,
the validated historical `outputs/pilot/population_sensitivity/n_0100_seed_42`
run is reused instead of rerouting it.

Repeated runs are written under:

```text
outputs/pilot/final_sensitivity/
```

The main products are:

```text
final_sensitivity_plan.csv
final_sensitivity_runs.csv
final_sensitivity_seed_stability.csv
final_sensitivity_parameter_comparison.csv
final_sensitivity_report.md
```

`final_sensitivity_seed_stability.csv` summarizes the nominal realizations
using mean, median, quartiles, IQR and range. For delta-H_soc metrics it also
reports the share of seeds preserving the sign of the median effect.
`final_sensitivity_parameter_comparison.csv` compares each local perturbation
with the nominal seed=42 reference.

The main pilot accepts the same sensitivity overrides directly:

```bash
python -m src.simulation.run_pilot \
  --n-agents 100 \
  --seed 42 \
  --destination-decay-multiplier 0.75 \
  --mode-decay-multiplier 1.0 \
  --output-dir outputs/pilot/example_sensitivity \
  --skip-maps \
  --skip-metadata
```

Use `--homogenize-differentiated-mode` to isolate the contribution of
differentiated purpose/destination rules while keeping modal probabilities
equal between income groups.

## Article v01 reproducible package

The full article pipeline has a single entry point:

```bash
python -m src.analysis.article_v01
```

Independent simulation runs are executed with two workers by default. If the
machine becomes memory-constrained, use `--workers 1`. To obtain the central
article results first, without waiting for the local parameter-sensitivity
reruns, use:

```bash
python -m src.analysis.article_v01 --core-only --workers 2
```

The core-only mode still uses all five nominal seeds and produces the three
analytical bases, the hierarchical-bootstrap result, spatial consensus,
income-group entropy contributions, behavioral diagnostics, tables and the
main maps/figures. The extra counterfactual and ±25% parameter perturbations
can be completed later by running the full command; `--resume` preserves all
already completed simulations.

The command first executes/reuses the fixed-N sensitivity battery and then
creates the complete article package under:

```text
outputs/v01 artigo/
```

Use the following command only when all simulation runs already exist and the
goal is to rebuild the analytical package:

```bash
python -m src.analysis.article_v01 --skip-simulations
```

The package contains three final analytical bases:

```text
01_bases/base01_agentes_pareados
01_bases/base02_segmentos_pareados
01_bases/base03_realizacoes
```

The inferential result does **not** treat street segments as independent
observations. Uncertainty is estimated with a hierarchical bootstrap that
resamples seeds and, within each seed, paired agents while preserving every
agent's complete trajectory. Segment-level outputs remain the descriptive and
spatial representation layer.

The article package also produces:

- a direct answer table for the operational research question;
- a multi-seed spatial consensus layer;
- exact additive contributions of each income group to `delta_H_soc`;
- a behavioral decomposition separating purpose+destination from differentiated
  mode probabilities;
- route-overlap and behavioral-change diagnostics by income group;
- local parameter-sensitivity results;
- automatic article tables in CSV and XLSX;
- a figure/map set and a figure manifest;
- a reproducibility manifest and a concise results report.

## Remaining work to close the pilot

Complete the pilot in this order:

1. run the unit-test suite after pulling this branch;
2. execute `python -m src.analysis.article_v01`;
3. inspect the five-seed stability, hierarchical-bootstrap interval, spatial
   consensus, mechanism decomposition and local parameter perturbations;
4. freeze the nominal behavioral configuration if the central pattern is not
   driven by a single seed or by the local 0.75x/1.25x perturbations;
5. use the generated `outputs/v01 artigo/` package as the frozen analytical
   source for article tables, maps, figures and reported numerical results.

Increasing N above 100 is not part of the closing battery. The previous N=250
run remains useful as a diagnostic showing that N=100 must be described as an
operational compromise rather than as a converged population size.

Sensitivity of GTFS-to-OSM geometric matching, alternate departure times and
other routing-architecture choices are deferred unless a concrete diagnostic
shows that they materially affect the final behavioral result. They should not
be mixed with the final behavioral-parameter freeze by default.

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
