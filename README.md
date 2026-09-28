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
10. Compare experimental scenarios and visualize results

---

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

In progress:

- Scenario comparison and map visualization
- Sensitivity analysis with larger synthetic populations and multiple seeds

Future work:

- GTFS public transport routing
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
