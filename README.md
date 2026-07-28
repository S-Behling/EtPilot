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

1. Download street network
2. Characterize road infrastructure
3. Generate origins (population)
4. Generate destinations (amenities)
5. Build OD matrix
6. Compute routes
7. Build trajectories
5. Compute urban metrics
6. Calculate Trajectory Entropy (ET)
7. Visualize and analyze results

---

## Current Status

Current implementation:

- ✔ Street network download
- ✔ Road classification
- ✔ Network visualization

In progress:

- Routing
- Trajectory generation
- Trajectory Entropy (ET)

Future work:

- Segregation indicators
- Accessibility analysis
- Agent-Based Modeling
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
