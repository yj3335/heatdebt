# HeatDebt — NYC Urban Heat Inequality Auditor

**Code4City Hackathon 2026**

Extreme heat kills more New Yorkers than hurricanes, floods, and lightning combined. But it doesn't kill equally. On the same July afternoon, a resident of Mott Haven in the Bronx can experience a surface temperature of 101°F while someone in Lower Manhattan feels 86°F. Same city. Same hour. Fifteen degree difference. That gap isn't weather. It's policy.

HeatDebt is a spatial query engine that fuses six public datasets into a single, fast, queryable index. It computes a "Heat Debt Score" for every census tract in NYC, measuring the combined burden of missing tree canopy, heat-absorbing land use, socioeconomic vulnerability, and satellite-measured surface temperature. The result: a ranked, interactive 3D map that answers one question — **where should the next dollar of cooling investment go?**

## The Problem

The data to prove urban heat inequality already exists. NYC publishes satellite surface temperature imagery, a census of every street tree, land use records for every tax lot, and household income tables for every census tract. But these datasets sit in silos across different agencies, formats, and geographic units. No tool today lets a community board member, city planner, or journalist ask:

> "Show me every neighborhood where tree density is below 5 per hectare, impervious surface exceeds 30%, and median income is under $40,000."

Without that ability, cooling interventions like tree plantings, cool roofs, and spray parks are allocated by intuition instead of evidence. The neighborhoods that need them most are often the last to receive them.

## The Solution

HeatDebt treats this as a data infrastructure problem, not a data collection problem. It ingests and indexes all six datasets into a single DuckDB analytical database, computes a composite Heat Debt Score per census tract using normalized percentile ranking, and serves the results through an interactive 3D choropleth map with a natural-language query interface powered by a local LLM.

## Key Findings

From our analysis of 2,327 NYC census tracts:

- **The Bronx** has the highest average heat debt score (0.5760) across all boroughs
- **66 tracts** fall in the "Critical" tier (score 0.8-1.0)
- The single worst tract — **Census Tract 1028.01 in Brooklyn** — scores 0.8882 with zero trees and a surface temperature of 102°F
- **Mott Haven-Port Morris** in the Bronx ranks #2 with 291 trees but 101°F surface temperature and median income of $25,851
- The Bronx averages 197 trees per tract compared to Staten Island's 646
- Manhattan has the lowest average surface temperature (85.6°F) due to building shade, despite having the most impervious surface (16.7%)
- **Census Tract 323 in Staten Island** recorded the highest surface temperature at 111°F

## Heat Debt Score

The Heat Debt Score is a composite metric from 0 to 1, where higher values indicate greater heat inequity. It combines four normalized components:

| Component | Weight | What It Measures | Source |
|---|---|---|---|
| Tree Deficit | 30% | How few trees a tract has relative to others | NYC Street Tree Census (2015) |
| Impervious Surface | 25% | Share of land used for parking, industrial, and vacant lots | NYC PLUTO (2025 v4) |
| Income Vulnerability | 25% | How low the median household income is | Census ACS (2024) |
| Surface Temperature | 20% | Satellite-measured summer surface heat | Landsat 8 (2020-2023) |

Each component is computed as a percentile rank across all 2,327 NYC census tracts. A tract scoring 0.90 on tree deficit means 90% of NYC tracts have more trees per hectare. The weighted sum of all four ranks produces the final Heat Debt Score.

**Why these weights?** Tree deficit gets the highest weight (30%) because it's the most actionable variable — a city can plant trees. Impervious surface and income get equal weight (25%) as contextual factors. Surface temperature gets the lowest weight (20%) because it's sampled at a single centroid point per tract rather than averaged across the area, making it less precise than the other components.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Frontend (MapLibre GL JS)                 │
│    3D Choropleth · Detail Panel · AI Chat · Filters     │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP
┌──────────────────────────┴──────────────────────────────┐
│                   API Server (Flask/Python)              │
│             /ask · /tract/<id> · static files            │
└──────────────────────────┬──────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                                 │
┌─────────┴──────────┐         ┌────────────┴───────────┐
│   DuckDB + Spatial  │         │   LLM Agent (Ollama)   │
│   heatdebt.duckdb   │         │   Mistral 7B (local)   │
│   2,327 tracts      │         │   NL → SQL translation │
│   652K trees        │         │                        │
│   857K tax lots     │         │                        │
│   Landsat temps     │         │                        │
└────────────────────┘         └────────────────────────┘
```

Everything runs locally. No cloud services, no API keys for the core functionality, no external dependencies at runtime.

## Data Sources

### NYC Street Tree Census (2015)

The most recent complete georeferenced inventory of every street tree in NYC. Contains 683,788 trees with species, trunk diameter, health rating, and exact latitude/longitude. Published by NYC Parks Department through NYC Open Data.

We aggregate this to census-tract level: tree count, average diameter, healthy tree count, and species diversity. The `boro_ct` field maps directly to census tract GEOIDs via borough-to-county-FIPS translation. This dataset also provides neighborhood names (NTA) for each tract.

- **Source:** https://data.cityofnewyork.us/Environment/2015-Street-Tree-Census-Tree-Data/uvpi-gqnh
- **Format:** CSV, ~210 MB, 683,788 rows
- **Update Cycle:** Every 10 years (2025 census underway, data not yet published)

### PLUTO (Primary Land Use Tax Lot Output)

Every tax lot in NYC with its zoning, land use classification, lot area, and building characteristics. Published by NYC Department of City Planning.

We use land use codes to compute an impervious surface proxy per tract. Lots classified as Industrial (05), Parking Facilities (10), and Vacant Land (11) are flagged as heat-absorbing surfaces. The ratio of heat-absorbing lot area to total lot area within each tract becomes the impervious surface percentage.

- **Source:** https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change
- **Format:** CSV, ~368 MB, 858,644 rows (version 25v4)
- **Update Cycle:** Quarterly

### American Community Survey (ACS) 5-Year Estimates

Median household income per census tract from the U.S. Census Bureau. Provides the socioeconomic vulnerability layer. Low-income tracts score higher on heat debt because residents have fewer resources to cope with extreme heat (less AC access, less mobility, less ability to relocate).

- **Source:** https://data.census.gov (Table B19013)
- **Format:** CSV, 2,327 NYC tracts
- **Update Cycle:** Annual (using 2024 estimates)

### Census Tract Boundaries (TIGER/Line Shapefiles)

Polygon geometries defining the boundaries of every census tract in New York State. We filter to the five NYC counties (Bronx 005, Brooklyn 047, Manhattan 061, Queens 081, Staten Island 085) to get 2,327 tracts.

- **Source:** https://www2.census.gov/geo/tiger/TIGER2023/TRACT/
- **Format:** Shapefile (.shp), ~15 MB zipped
- **GEOID Format:** 11 digits (state 36 + county 3 digits + tract 6 digits)

### NYC Heat Vulnerability Index (HVI) Rankings

Pre-computed heat vulnerability scores (1-5) by ZIP code from the NYC Department of Health. Incorporates surface temperature, green space, AC access, and poverty rate. Used as a validation reference.

- **Source:** https://data.cityofnewyork.us (search "Heat Vulnerability Index")
- **Format:** CSV, 184 ZIP codes

### Landsat Surface Temperature

Mean summer (June-September) surface temperature derived from Landsat 8 Collection 2 Tier 1 thermal band (ST_B10) for 2020-2023. Exported from Google Earth Engine at 30-meter resolution. Cloud-masked and temporally averaged. Values stored in Fahrenheit.

We sample the raster at each tract's centroid using the GeoTIFF's geotransform tags to map pixel coordinates to lat/lon. All 2,327 tract centroids fall within the raster bounds, giving 100% coverage.

- **Source:** Google Earth Engine (LANDSAT/LC08/C02/T1_L2)
- **Format:** BigTIFF (LZW compressed), ~28 MB
- **Coverage:** NYC bounding box (-74.27, 40.49) to (-73.68, 40.92)
- **Temperature Range:** 57.6°F to 111.4°F across NYC tracts

## Join Strategy

Each dataset uses a different geographic identifier. The join logic:

| Dataset | Raw Key | Transformation | Joins To |
|---|---|---|---|
| Tract Shapefile | `GEOID` = `36005006500` | None (this is the base) | — |
| Street Trees | `boro_ct` = `2006500` | Map first digit (boro) to state+county FIPS, concat rest | tracts.GEOID |
| PLUTO | `bct2020` = `2006500` | Same boro-to-FIPS mapping as trees | tracts.GEOID |
| ACS Income | `GEO_ID` = `1400000US36005006500` | Split on 'US', take right side | tracts.GEOID |
| Landsat Temp | Raster centroid sample | ST_Centroid(geom) to pixel coords | Spatial lookup |
| HVI | `zip_code` | No direct join to tracts (different geography) | Validation only |

Borough code to county FIPS mapping:
- 1 -> 36061 (Manhattan / New York County)
- 2 -> 36005 (Bronx / Bronx County)
- 3 -> 36047 (Brooklyn / Kings County)
- 4 -> 36081 (Queens / Queens County)
- 5 -> 36085 (Staten Island / Richmond County)

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Database | DuckDB + Spatial Extension | Sub-second analytical queries on millions of rows, runs on a laptop, no server needed |
| Data Pipeline | Python 3.9 | Data ingestion, scoring, GeoJSON export |
| Frontend | MapLibre GL JS + CartoDB dark tiles | WebGL-powered 3D choropleth with smooth interactions, no build step |
| LLM Agent | Ollama + Mistral 7B | Local natural-language-to-SQL translation, no API keys |
| API Server | Flask (Python) | Connects frontend to DuckDB and LLM |
| Satellite Data | Google Earth Engine + tifffile | Landsat 8 thermal band export and raster sampling |

## Project Structure

```
heatdebt/
├── data/
│   ├── street_trees_2015.csv          # NYC Street Tree Census
│   ├── pluto_25v4.csv                 # PLUTO land use
│   ├── hvi_rankings.csv               # Heat Vulnerability Index
│   ├── ACSDT5Y2024.B19013-Data.csv    # ACS median income
│   ├── nyc_surface_temp.tif           # Landsat surface temperature
│   ├── README.md                      # Data documentation
│   └── census_tracts/
│       └── tl_2023_36_tract.shp       # Census tract boundaries
├── frontend/
│   ├── index.html                     # Map UI (MapLibre GL JS)
│   └── tracts.geojson                 # Exported scored tract data
├── ingest.py                          # Load all datasets into DuckDB
├── fix_trees.py                       # Fix tree-to-tract join keys
├── compute_score.py                   # Compute Heat Debt Score (3 components)
├── integrate_temperature.py           # Add Landsat temp as 4th component
├── export_geojson.py                  # Export scored data for frontend
├── verify_data.py                     # Dataset verification script
├── agent_prompt.txt                   # LLM system prompt with schemas
├── llm_agent.py                       # Natural language query agent
├── app.py                             # Flask API server
├── heatdebt.duckdb                    # Built database (~62 MB)
├── pitch.md                           # 3-minute demo pitch script
└── README.md
```

## Setup & Installation

### Prerequisites

- Python 3.9+
- Ollama (for the LLM query feature)

### Install Dependencies

```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

pip install duckdb pandas numpy httpx flask flask-cors tifffile imagecodecs
```

### Build the Database

```bash
# 1. Load all datasets into DuckDB
python ingest.py

# 2. Fix tree-to-tract join keys (uses boro_ct instead of census tract)
python fix_trees.py

# 3. Compute Heat Debt Score (tree deficit, impervious surface, income)
python compute_score.py

# 4. Integrate Landsat surface temperature as 4th component
python integrate_temperature.py

# 5. Export GeoJSON for the frontend
python export_geojson.py
```

### Run the Application

```bash
# Option A: Simple static server (map only, no AI queries)
cd frontend
python -m http.server 8000
# Open http://localhost:8000

# Option B: Full application with AI query interface
ollama serve                    # In a separate terminal
python app.py                   # Starts Flask on port 5001
# Open http://localhost:5001
```

## Usage

### Interactive Map

Open the application in a browser. The 3D choropleth map shows all 2,327 NYC census tracts colored by Heat Debt Score (darker red = higher heat inequity). Hover over any tract to preview its data in the sidebar. Click to lock the selection and see the tract extrude in 3D proportional to its score.

The detail panel shows the neighborhood name, Heat Debt Score, and four component metrics each with the raw measured value and the percentile rank (e.g., "1,413 trees (61st pct)").

Use the borough filter buttons at the bottom to isolate a single borough.

### AI Query Interface

Click the AI button in the bottom right to open the query dialog. Type a question in plain English. The local LLM translates it to SQL, executes it against DuckDB, and returns results as a table. Example queries:

- "Where should NYC plant its next 1,000 trees?"
- "Show me the 10 hottest low-income neighborhoods in the Bronx"
- "Compare heat debt between boroughs"
- "Which neighborhoods have zero trees?"
- "What's the most common tree species in Brooklyn?"
- "Show me heat debt in Hunts Point"
- "What is the temperature difference between the richest and poorest neighborhoods?"

The top 20 most heat-indebted tracts are displayed by default when the dialog opens.

## Limitations & Future Work

**Current limitations:**
- Tree data is from 2015. The 2025 NYC tree census is underway but results are not yet published. When published, HeatDebt can ingest it with zero code changes — it's a CSV swap.
- The impervious surface metric is a proxy based on land use codes, not actual measured surface coverage or albedo.
- The Heat Debt Score weights (30/25/25/20) are a starting assumption. Proper calibration would require validation against heat-related health outcome data.
- Surface temperature is sampled at the tract centroid only, not averaged across the full tract area. A centroid that falls on a park gives a misleadingly cool reading.
- The HVI validation layer operates at ZIP code level, which is coarser than census tract level.
- 305 tracts (13%) lack neighborhood names because they had no trees in the 2015 census and fall back to "Census Tract X".

**Future directions:**
- Incorporate heat-related 911 call data and emergency room visit data for outcome validation and weight calibration
- Add temporal analysis: how has heat debt changed over time as neighborhoods develop?
- Build a budget allocation optimizer: given $X million for tree planting, which tracts maximize heat debt reduction?
- Integrate the 2025 tree census data when published
- Average surface temperature across full tract polygons instead of centroid sampling
- Add cool roof and green infrastructure datasets to measure existing interventions

## License

This project was built for the Code4City Hackathon 2026. All data sources are publicly available through NYC Open Data, the U.S. Census Bureau, and Google Earth Engine.

## Acknowledgments

- NYC Department of Parks & Recreation (Street Tree Census)
- NYC Department of City Planning (PLUTO)
- NYC Department of Health and Mental Hygiene (Heat Vulnerability Index)
- U.S. Census Bureau (ACS, TIGER/Line)
- USGS / NASA (Landsat 8)
- Google Earth Engine
- NYU Center for Urban Science and Progress (CUSP) and Code4City organizers