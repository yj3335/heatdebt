# HeatDebt — NYC Urban Heat Inequality Auditor

**Code4City Hackathon 2026**

Extreme heat kills more New Yorkers than hurricanes, floods, and lightning combined. But it doesn't kill equally. On the same July afternoon, a resident of Hunts Point in the Bronx can experience temperatures 10°F higher than someone in Prospect Park, because decades of disinvestment stripped some neighborhoods of trees and replaced them with asphalt.

HeatDebt is a spatial query engine that fuses five public datasets into a single, fast, queryable index. It computes a "Heat Debt Score" for every census tract in NYC, measuring the combined burden of missing tree canopy, heat-absorbing land use, and socioeconomic vulnerability. The result: a ranked, interactive map that answers one question — **where should the next dollar of cooling investment go?**

## The Problem

The data to prove urban heat inequality already exists. NYC publishes satellite surface temperature imagery, a census of every street tree, land use records for every tax lot, and household income tables for every census tract. But these datasets sit in silos across different agencies, formats, and geographic units. No tool today lets a community board member, city planner, or journalist ask:

> "Show me every census tract where tree density is below 5 per hectare, impervious surface exceeds 30%, and median income is under $40,000."

Without that ability, cooling interventions like tree plantings, cool roofs, and spray parks are allocated by intuition instead of evidence. The neighborhoods that need them most are often the last to receive them.

## The Solution

HeatDebt treats this as a data infrastructure problem, not a data collection problem. It ingests and indexes all five datasets into a single DuckDB analytical database, computes a composite Heat Debt Score per census tract using normalized percentile ranking, and serves the results through an interactive choropleth map with a natural-language query interface powered by a local LLM.

## Key Findings

From our analysis of 2,327 NYC census tracts:

- **The Bronx** has the highest average heat debt score (0.5928) across all boroughs
- **66 tracts** fall in the "Critical" tier (score 0.8-1.0)
- The single worst tract — **Census Tract 29.01 in Manhattan** — has zero street trees and a median household income of $11,094
- The Bronx averages 197 trees per tract compared to Staten Island's 646

## Heat Debt Score

The Heat Debt Score is a composite metric from 0 to 1, where higher values indicate greater heat inequity. It combines three normalized components:

| Component | Weight | What It Measures | Source |
|---|---|---|---|
| Tree Deficit | 40% | How few trees a tract has relative to others | NYC Street Tree Census |
| Impervious Surface | 30% | Share of land used for parking, industrial, and vacant lots | NYC PLUTO |
| Income Vulnerability | 30% | How low the median household income is | Census ACS 2024 |

Each component is computed as a percentile rank across all 2,327 NYC census tracts. A tract scoring 0.90 on tree deficit means 90% of NYC tracts have more trees. The weighted sum of these three ranks produces the final Heat Debt Score.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Leaflet.js)                │
│  Choropleth Map · Detail Panel · Ranked Sidebar · Query │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP
┌──────────────────────────┴──────────────────────────────┐
│                   API Server (Flask/Python)              │
│           /query · /tract/<id> · static files            │
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
└────────────────────┘         └────────────────────────┘
```

Everything runs locally. No cloud services, no API keys for the core functionality, no external dependencies at runtime.

## Data Sources

### NYC Street Tree Census (2015)

The most recent complete georeferenced inventory of every street tree in NYC. Contains 683,788 trees with species, trunk diameter, health rating, and exact latitude/longitude. Published by NYC Parks Department through NYC Open Data.

We aggregate this to census-tract level: tree count, average diameter, healthy tree count, and species diversity. The `boro_ct` field maps directly to census tract GEOIDs via borough-to-county-FIPS translation.

- **Source:** https://data.cityofnewyork.us/Environment/2015-Street-Tree-Census-Tree-Data/uvpi-gqnh
- **Format:** CSV, ~210 MB
- **Update Cycle:** Every 10 years (2025 census underway, data not yet published)

### PLUTO (Primary Land Use Tax Lot Output)

Every tax lot in NYC with its zoning, land use classification, lot area, and building characteristics. Published by NYC Department of City Planning.

We use land use codes to compute an impervious surface proxy per tract. Lots classified as Industrial (05), Parking Facilities (10), and Vacant Land (11) are flagged as heat-absorbing surfaces. The ratio of heat-absorbing lot area to total lot area within each tract becomes the impervious surface percentage.

- **Source:** https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change
- **Format:** CSV, ~368 MB (version 25v4)
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

Pre-computed heat vulnerability scores (1-5) by ZIP code from the NYC Department of Health. Incorporates surface temperature, green space, AC access, and poverty rate. Used as a validation reference and fallback thermal layer.

- **Source:** https://data.cityofnewyork.us (search "Heat Vulnerability Index")
- **Format:** CSV, 184 ZIP codes

### Landsat Surface Temperature (Stretch Goal)

Mean summer (June-September) surface temperature in Celsius, derived from Landsat 8 Collection 2 Tier 1 thermal band (ST_B10) for 2020-2023. Exported from Google Earth Engine at 30-meter resolution. Cloud-masked and temporally averaged.

- **Source:** Google Earth Engine (LANDSAT/LC08/C02/T1_L2)
- **Format:** GeoTIFF, ~28 MB
- **Coverage:** NYC bounding box (-74.27, 40.49) to (-73.68, 40.92)

## Join Strategy

Each dataset uses a different geographic identifier. The join logic:

| Dataset | Raw Key | Transformation | Joins To |
|---|---|---|---|
| Tract Shapefile | `GEOID` = `36005006500` | None (this is the base) | — |
| Street Trees | `boro_ct` = `2006500` | Map first digit (boro) to state+county FIPS, concat rest | tracts.GEOID |
| PLUTO | `bct2020` = `2006500` | Same boro-to-FIPS mapping as trees | tracts.GEOID |
| ACS Income | `GEO_ID` = `1400000US36005006500` | Split on 'US', take right side | tracts.GEOID |
| HVI | `zip_code` | No direct join to tracts (different geography) | Used as overlay only |

Borough code to county FIPS mapping:
- 1 → 36061 (Manhattan / New York County)
- 2 → 36005 (Bronx / Bronx County)
- 3 → 36047 (Brooklyn / Kings County)
- 4 → 36081 (Queens / Queens County)
- 5 → 36085 (Staten Island / Richmond County)

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Database | DuckDB + Spatial Extension | Sub-second analytical queries on millions of rows, runs on a laptop, no server needed |
| Data Pipeline | Python 3.9 | Data ingestion, scoring, GeoJSON export |
| Frontend | Leaflet.js + CartoDB dark tiles | Lightweight choropleth rendering, no build step |
| LLM Agent | Ollama + Mistral 7B | Local natural-language-to-SQL translation, no API keys |
| API Server | Flask (Python) | Connects frontend to DuckDB and LLM |

## Project Structure

```
heatdebt/
├── data/
│   ├── street_trees_2015.csv          # NYC Street Tree Census
│   ├── pluto_25v4.csv                 # PLUTO land use
│   ├── hvi_rankings.csv               # Heat Vulnerability Index
│   ├── ACSDT5Y2024.B19013-Data.csv    # ACS median income
│   ├── nyc_surface_temp.tif           # Landsat surface temperature
│   └── census_tracts/
│       └── tl_2023_36_tract.shp       # Census tract boundaries
├── frontend/
│   ├── index.html                     # Map UI
│   └── tracts.geojson                 # Exported scored tract data
├── ingest.py                          # Load all datasets into DuckDB
├── compute_score.py                   # Compute Heat Debt Score
├── export_geojson.py                  # Export scored data for frontend
├── agent_prompt.txt                   # LLM system prompt with schemas
├── llm_agent.py                       # Natural language query agent
├── heatdebt.duckdb                    # Built database (generated)
├── verify_data.py                     # Dataset verification script
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

pip install duckdb pandas numpy httpx flask
```

### Build the Database

```bash
# 1. Load all datasets into DuckDB
python ingest.py

# 2. Compute Heat Debt Scores
python compute_score.py

# 3. Export GeoJSON for the frontend
python export_geojson.py
```

### Run the Application

```bash
# Start a local server
cd frontend
python -m http.server 8000

# Open http://localhost:8000 in your browser
```

### Enable the LLM Query Feature (Optional)

```bash
# In a separate terminal
ollama serve
ollama pull mistral

# Start the API server (replaces the simple http.server above)
python app.py
```

## Usage

### Interactive Map

Open the application in a browser. The choropleth map shows all 2,327 NYC census tracts colored by Heat Debt Score (darker red = higher heat inequity). Click any tract to see its detail panel with tree count, impervious surface percentage, median income, and the component scores that contribute to its ranking. The sidebar lists the top 20 most heat-indebted tracts.

### Natural Language Queries

Type a question into the query bar. The LLM translates it to SQL, executes it against DuckDB, and returns results. Example queries:

- "Where should NYC plant its next 1,000 trees?"
- "Show me the 10 hottest low-income tracts in the Bronx"
- "Compare heat debt between boroughs"
- "Which tracts have zero trees?"
- "What's the most common tree species in Brooklyn?"

## Limitations & Future Work

**Current limitations:**
- Tree data is from 2015. The 2025 NYC tree census is underway but results are not yet published.
- The impervious surface metric is a proxy based on land use codes, not actual measured surface coverage.
- The Heat Debt Score weights (40/30/30) are a starting assumption. Proper calibration would require validation against heat-related health outcome data.
- The Landsat surface temperature raster is not yet integrated into the composite score.
- The HVI fallback layer operates at ZIP code level, which is coarser than census tract level.

**Future directions:**
- Integrate the Landsat surface temperature as a fourth score component
- Incorporate heat-related 911 call data and emergency room visit data for outcome validation
- Add temporal analysis: how has heat debt changed over time as neighborhoods develop?
- Build a budget allocation optimizer: given $X million for tree planting, which tracts maximize heat debt reduction?
- Integrate the 2025 tree census data when published

## License

This project was built for the Code4City Hackathon 2026. All data sources are publicly available through NYC Open Data, the U.S. Census Bureau, and Google Earth Engine.

## Acknowledgments

- NYC Department of Parks & Recreation (Street Tree Census)
- NYC Department of City Planning (PLUTO)
- NYC Department of Health and Mental Hygiene (Heat Vulnerability Index)
- U.S. Census Bureau (ACS, TIGER/Line)
- USGS / NASA (Landsat 8)
- NYU Center for Urban Science and Progress (CUSP) and Code4City organizers