import duckdb
import os
import csv

DATA_DIR = "data"
DB_PATH = "heatdebt.duckdb"

# Delete old DB if re-running
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"Removed old {DB_PATH}")

con = duckdb.connect(DB_PATH)
con.execute("INSTALL spatial; LOAD spatial;")
print("DuckDB ready, spatial extension loaded.\n")
print("Loading census tract boundaries...")

shp_path = os.path.join(DATA_DIR, "census_tracts", "tl_2023_36_tract.shp")
con.execute(f"""
    CREATE TABLE tracts AS
    SELECT
        GEOID,
        NAMELSAD AS tract_name,
        COUNTYFP AS county_fips,
        ALAND,
        geom
    FROM ST_Read('{shp_path}')
    WHERE COUNTYFP IN ('005','047','061','081','085')
""")
count = con.execute("SELECT COUNT(*) FROM tracts").fetchone()[0]
print(f"  Loaded {count:,} NYC census tracts\n")
print("Loading street trees...")

trees_path = os.path.join(DATA_DIR, "street_trees_2015.csv")

# check what boro_ct looks like so we can build the join key
sample = con.execute(f"""
    SELECT DISTINCT borocode, "census tract", boro_ct
    FROM read_csv_auto('{trees_path}', sample_size=5000)
    WHERE "census tract" IS NOT NULL
    LIMIT 5
""").fetchall()
print(f"  Sample tree tract data: {sample}")

# Mapping: borocode -> state+county FIPS prefix
# 1=Manhattan(36061), 2=Bronx(36005), 3=Brooklyn(36047),
# 4=Queens(36081), 5=Staten Island(36085)
con.execute(f"""
    CREATE TABLE trees_raw AS
    SELECT
        tree_id,
        tree_dbh,
        health,
        spc_common,
        borocode,
        "census tract" AS census_tract,
        boro_ct,
        latitude,
        longitude
    FROM read_csv_auto('{trees_path}', sample_size=5000)
    WHERE latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND status = 'Alive'
""")
count = con.execute("SELECT COUNT(*) FROM trees_raw").fetchone()[0]
print(f"  Loaded {count:,} live trees")

# Build a GEOID to join against tract shapefile
con.execute("""
    CREATE TABLE trees AS
    SELECT
        *,
        CASE CAST(borocode AS INTEGER)
            WHEN 1 THEN '36061'
            WHEN 2 THEN '36005'
            WHEN 3 THEN '36047'
            WHEN 4 THEN '36081'
            WHEN 5 THEN '36085'
        END || LPAD(CAST(census_tract AS VARCHAR), 6, '0') AS geoid
    FROM trees_raw
""")

# Verify the join will work
match_check = con.execute("""
    SELECT COUNT(DISTINCT t.geoid) as tree_tracts,
           COUNT(DISTINCT tr.GEOID) as shp_tracts,
           COUNT(DISTINCT CASE WHEN tr.GEOID IS NOT NULL THEN t.geoid END) as matched
    FROM (SELECT DISTINCT geoid FROM trees) t
    LEFT JOIN tracts tr ON t.geoid = tr.GEOID
""").fetchone()
print(f"  Tree tract IDs: {match_check[0]}, Shapefile tracts: {match_check[1]}, Matched: {match_check[2]}")
if match_check[2] < match_check[0] * 0.9:
    print("  WARNING: Less than 90% match. Checking GEOID format mismatch...")
    mismatch_sample = con.execute("""
        SELECT DISTINCT t.geoid
        FROM (SELECT DISTINCT geoid FROM trees) t
        LEFT JOIN tracts tr ON t.geoid = tr.GEOID
        WHERE tr.GEOID IS NULL
        LIMIT 5
    """).fetchall()
    print(f"  Unmatched tree GEOIDs: {[r[0] for r in mismatch_sample]}")
    shp_sample = con.execute("SELECT GEOID FROM tracts LIMIT 3").fetchall()
    print(f"  Shapefile GEOIDs: {[r[0] for r in shp_sample]}")
else:
    print(f"  Join match rate: {100*match_check[2]/max(match_check[0],1):.1f}% - GOOD")

# Aggregate trees per tract
con.execute("""
    CREATE TABLE trees_per_tract AS
    SELECT
        geoid AS tract_geoid,
        COUNT(*) AS tree_count,
        AVG(tree_dbh) AS avg_tree_diameter,
        SUM(CASE WHEN health = 'Good' THEN 1 ELSE 0 END) AS healthy_trees,
        COUNT(DISTINCT spc_common) AS species_count
    FROM trees
    GROUP BY geoid
""")
count = con.execute("SELECT COUNT(*) FROM trees_per_tract").fetchone()[0]
print(f"  Aggregated trees into {count:,} tracts\n")
print("Loading PLUTO land use data...")
pluto_path = os.path.join(DATA_DIR, "pluto_25v4.csv")

# boro-to-county mapping as trees
con.execute(f"""
    CREATE TABLE pluto_raw AS
    SELECT
        CAST(bct2020 AS VARCHAR) AS bct2020,
        landuse,
        lotarea,
        latitude,
        longitude
    FROM read_csv_auto('{pluto_path}', sample_size=5000)
    WHERE bct2020 IS NOT NULL
""")

con.execute("""
    CREATE TABLE pluto AS
    SELECT
        *,
        CASE SUBSTRING(bct2020, 1, 1)
            WHEN '1' THEN '36061'
            WHEN '2' THEN '36005'
            WHEN '3' THEN '36047'
            WHEN '4' THEN '36081'
            WHEN '5' THEN '36085'
        END || SUBSTRING(bct2020, 2) AS geoid
    FROM pluto_raw
""")

# Compute impervious surface metrics per tract
# Heat-absorbing land uses:
#   05 = Industrial/Manufacturing
#   10 = Parking Facilities
#   11 = Vacant Land
con.execute("""
    CREATE TABLE impervious_per_tract AS
    SELECT
        geoid AS tract_geoid,
        COUNT(*) AS total_lots,
        SUM(CASE WHEN landuse IN ('05','10','11') THEN 1 ELSE 0 END) AS heat_lots,
        SUM(CASE WHEN landuse IN ('05','10','11') THEN COALESCE(lotarea, 0) ELSE 0 END) AS heat_lot_area,
        SUM(COALESCE(lotarea, 0)) AS total_lot_area,
        ROUND(100.0 * SUM(CASE WHEN landuse IN ('05','10','11')
            THEN COALESCE(lotarea, 0) ELSE 0 END)
            / NULLIF(SUM(COALESCE(lotarea, 0)), 0), 2) AS impervious_pct
    FROM pluto
    GROUP BY geoid
""")
count = con.execute("SELECT COUNT(*) FROM impervious_per_tract").fetchone()[0]
print(f"  Computed impervious metrics for {count:,} tracts\n")
print("Loading ACS income data...")

acs_path = None
for f in os.listdir(DATA_DIR):
    if 'B19013' in f and f.endswith('.csv') and 'Data' in f:
        acs_path = os.path.join(DATA_DIR, f)
        break

if acs_path is None:
    print("  WARNING: ACS income file not found! Skipping.")
    con.execute("""
        CREATE TABLE income AS
        SELECT '' AS tract_geoid, 0 AS median_income WHERE false
    """)
else:
    print(f"  Found: {os.path.basename(acs_path)}")

    con.execute(f"""
        CREATE TABLE acs_raw AS
        SELECT *
        FROM read_csv('{acs_path}', header=true, skip=1, auto_detect=true)
    """)

    # Get actual column names
    acs_cols = con.execute("SELECT * FROM acs_raw LIMIT 0").description
    col_names = [c[0] for c in acs_cols]
    print(f"  Columns detected: {col_names[:5]}")

    geo_col = col_names[0]
    income_col = col_names[2]

    con.execute(f"""
        CREATE TABLE income AS
        SELECT
            -- Extract 11-digit FIPS from GEO_ID like '1400000US36005006500'
            CASE
                WHEN "{geo_col}" LIKE '%US%'
                THEN SPLIT_PART(CAST("{geo_col}" AS VARCHAR), 'US', 2)
                ELSE CAST("{geo_col}" AS VARCHAR)
            END AS tract_geoid,
            TRY_CAST("{income_col}" AS INTEGER) AS median_income
        FROM acs_raw
        WHERE TRY_CAST("{income_col}" AS INTEGER) IS NOT NULL
    """)
    count = con.execute("SELECT COUNT(*) FROM income").fetchone()[0]
    print(f"  Loaded income for {count:,} tracts")

    # Quick stats
    stats = con.execute("""
        SELECT MIN(median_income), MAX(median_income), AVG(median_income)::INTEGER
        FROM income
        WHERE median_income > 0
    """).fetchone()
    print(f"  Income range: ${stats[0]:,} to ${stats[1]:,}, avg ${stats[2]:,}\n")

print("Loading HVI rankings (ZIP-level fallback)...")
hvi_path = os.path.join(DATA_DIR, "hvi_rankings.csv")
con.execute(f"""
    CREATE TABLE hvi AS
    SELECT
        "ZIP Code Tabulation Area (ZCTA) 2020" AS zip_code,
        "Heat Vulnerability Index (HVI)" AS hvi_score
    FROM read_csv_auto('{hvi_path}')
""")
count = con.execute("SELECT COUNT(*) FROM hvi").fetchone()[0]
print(f"  Loaded HVI for {count} ZIP codes\n")