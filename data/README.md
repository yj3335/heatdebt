# HeatDebt — Data Directory

This folder contains all source datasets used by the HeatDebt pipeline. Everything here is publicly available and free to download. No API keys are required except for the Census API (free, instant signup) and Google Earth Engine (free, academic use).

## Files

### street_trees_2015.csv (~210 MB)

Every street tree in New York City, mapped during the 2015-2016 TreesCount! census by NYC Parks and over 2,200 volunteers.

- **Rows:** 683,788
- **Key columns used:** `tree_id`, `tree_dbh` (trunk diameter in inches), `health` (Good/Fair/Poor), `spc_common` (species), `borocode`, `boro_ct`, `latitude`, `longitude`
- **Join key:** `boro_ct` — first digit is the borough code, remaining digits are the census tract. We convert borough code to county FIPS (e.g., 2 becomes 36005) and concatenate to build the 11-digit GEOID that matches the shapefile.
- **Source:** https://data.cityofnewyork.us/Environment/2015-Street-Tree-Census-Tree-Data/uvpi-gqnh
- **Why:** Tree canopy is the strongest factor in local surface temperature. Tracts with fewer trees absorb and radiate more heat. This dataset drives the tree deficit score (30% of the final composite).

### pluto_25v4.csv (~368 MB)

Every tax lot in NYC with its land use classification, lot size, building characteristics, and location. Published quarterly by NYC Department of City Planning.

- **Rows:** 858,644
- **Key columns used:** `bct2020` (borough + census tract 2020), `landuse` (2-digit code), `lotarea` (square feet), `latitude`, `longitude`
- **Join key:** `bct2020` — same format as tree `boro_ct`. First digit is borough code, rest is census tract. Same FIPS conversion applies.
- **Land use codes that indicate heat-absorbing surfaces:**
  - `05` — Industrial/Manufacturing
  - `10` — Parking Facilities
  - `11` — Vacant Land
- **Source:** https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change
- **Why:** Parking lots, industrial sites, and vacant land absorb and radiate far more heat than residential or green areas. The ratio of heat-absorbing lot area to total lot area in each tract becomes the impervious surface score (25% of the final composite).

### ACSDT5Y2024.B19013-Data.csv (~1 MB)

Median household income per census tract from the U.S. Census Bureau's American Community Survey, 5-year estimates (2024 release).

- **Rows:** 2,327 (one per NYC census tract, plus one header row and one descriptor row)
- **Key columns used:** `GEO_ID` (geographic identifier), `B19013_001E` (median income estimate)
- **Important format quirk:** This CSV has two header rows. Row 1 has machine-readable column names (`GEO_ID`, `B19013_001E`). Row 2 has human-readable descriptions. The ingestion script skips row 2 during loading.
- **Join key:** `GEO_ID` looks like `1400000US36005006500`. We split on `US` and take the right side to get the 11-digit GEOID.
- **Source:** https://data.census.gov (Table B19013, filtered to NYC counties: 36005, 36047, 36061, 36081, 36085)
- **Why:** Low-income households are less likely to have air conditioning, less able to relocate during heat waves, and more likely to live in historically redlined neighborhoods with less green space. Income is the equity layer that makes this a justice project, not just a climate project. Drives the income vulnerability score (25% of the final composite).

### hvi_rankings.csv (~5 KB)

Heat Vulnerability Index rankings from the NYC Department of Health and Mental Hygiene. Pre-computed vulnerability scores at the ZIP code level incorporating surface temperature, green space, poverty, and AC access.

- **Rows:** 184 (one per NYC ZIP code)
- **Columns:** `ZIP Code Tabulation Area (ZCTA) 2020`, `Heat Vulnerability Index (HVI)` (score 1-5, where 5 is most vulnerable)
- **Join key:** ZIP code. Does not join directly to census tracts (different geographic unit). Used as a validation layer and fallback.
- **Source:** https://data.cityofnewyork.us (search "Heat Vulnerability Index")
- **Why:** This is the city's official heat vulnerability measure. We use it to validate that our independently computed Heat Debt Score correlates with the government's assessment. It was also our fallback thermal layer in case the Landsat satellite data didn't work out.

### census_tracts/ (subfolder, ~15 MB unzipped)

Census tract boundary polygons for all of New York State from the Census Bureau's TIGER/Line shapefiles (2023 vintage).

- **Files:** `tl_2023_36_tract.shp` (plus .shx, .dbf, .prj, .cpg companion files)
- **Total tracts in file:** 5,411 (full NY State)
- **NYC tracts after filtering:** 2,327 (filtered by COUNTYFP IN 005, 047, 061, 081, 085)
- **Key columns:** `GEOID` (11-digit tract identifier, e.g., `36005006500`), `NAMELSAD` (human name, e.g., "Census Tract 65"), `COUNTYFP` (county code), `ALAND` (land area in square meters), `geom` (polygon geometry)
- **Source:** https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_36_tract.zip
- **Why:** This is the geographic skeleton of the entire project. Every other dataset joins to these tract polygons. The geometry is what draws the choropleth map. Without it, we have data points but no map.

### nyc_surface_temp.tif (~28 MB)

Mean summer surface temperature derived from Landsat 8 satellite imagery. Generated using Google Earth Engine by filtering Landsat 8 Collection 2 Tier 1 Level 2 images for June through September, 2020-2023, applying cloud masking via QA_PIXEL band, extracting surface temperature from the ST_B10 thermal band, and averaging all cloud-free observations.

- **Format:** BigTIFF (GeoTIFF with LZW compression)
- **Resolution:** 30 meters per pixel
- **CRS:** EPSG:4326 (WGS84 lat/lon)
- **Pixel size:** ~0.000269 degrees
- **Bounds:** lon -74.2700 to -73.6798, lat 40.4899 to 40.9206
- **Raster size:** 2,190 x 1,598 pixels
- **Values:** Surface temperature in Celsius (range 14.2 to 44.1)
- **NoData:** 0
- **GEE script:** See the repository root for the Earth Engine export script. Based on methodology from the NYC Council Data Team's heat map project.
- **Source:** Google Earth Engine (LANDSAT/LC08/C02/T1_L2), exported to Google Drive
- **Why:** Actual measured heat. While tree count and land use are proxies for how hot a neighborhood gets, this is the direct satellite measurement. We sample the raster value at each tract's centroid to get a temperature reading, which becomes the surface temperature score (20% of the final composite).

## Join Map

All datasets connect through the census tract GEOID:

```
street_trees_2015.csv ──(boro_ct → GEOID)──┐
                                            │
pluto_25v4.csv ────(bct2020 → GEOID)────────┤
                                            ├── tracts (GEOID) ── heat_debt_final
ACSDT5Y2024.B19013-Data.csv ──(GEO_ID)─────┤
                                            │
nyc_surface_temp.tif ──(centroid sample)────┘

hvi_rankings.csv ──(ZIP code, no direct join)── used for validation only
```

Borough code to county FIPS translation used in the tree and PLUTO joins:

| Borough Code | Borough | County FIPS | State+County |
|---|---|---|---|
| 1 | Manhattan | 061 | 36061 |
| 2 | Bronx | 005 | 36005 |
| 3 | Brooklyn | 047 | 36047 |
| 4 | Queens | 081 | 36081 |
| 5 | Staten Island | 085 | 36085 |

## Freshness

| Dataset | Vintage | Update Cycle | Notes |
|---|---|---|---|
| Street Trees | 2015-2016 | Every 10 years | 2025 census underway, data not yet published |
| PLUTO | 2025 (v4) | Quarterly | Current as of download |
| ACS Income | 2024 (5-year) | Annual | Most recent available |
| Census Tracts | 2023 | ~Every 10 years | 2020 census boundaries |
| HVI Rankings | 2018 | Irregular | Based on 2018 data |
| Landsat Temp | 2020-2023 | Generated on demand | 4-summer average |