import os
import sys
import json

DATA_DIR = os.path.expanduser("./data")

passed = 0
failed = 0
warnings = 0

def ok(msg):
    global passed
    passed += 1
    print(f"  [OK]   {msg}")

def fail(msg):
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")

def warn(msg):
    global warnings
    warnings += 1
    print(f"  [WARN] {msg}")

print("STREET TREES (street_trees_2015.csv)")

trees_path = os.path.join(DATA_DIR, "street_trees_2015.csv")
if not os.path.exists(trees_path):
    fail(f"File not found: {trees_path}")
else:
    size_mb = os.path.getsize(trees_path) / (1024*1024)
    ok(f"File exists ({size_mb:.1f} MB)")

    import duckdb
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_csv_auto('{trees_path}', sample_size=1000) LIMIT 5").fetchdf()
    cols = list(df.columns)

    needed = ['latitude', 'longitude', 'tree_dbh', 'health', 'spc_common', 'census tract']
    for c in needed:
        if c in cols:
            ok(f"Column '{c}' found")
        else:
            matches = [x for x in cols if x.lower().strip() == c.lower().strip()]
            if matches:
                warn(f"Column '{c}' found as '{matches[0]}' (case mismatch)")
            else:
                fail(f"Column '{c}' NOT FOUND. Available: {cols[:10]}...")

    row_count = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{trees_path}', sample_size=1000)
    """).fetchone()[0]
    if row_count > 600000:
        ok(f"Row count: {row_count:,} (expected ~683K)")
    else:
        fail(f"Row count: {row_count:,} (expected ~683K, too low)")

    # Check lat/lon ranges (should be NYC area)
    bounds = con.execute(f"""
        SELECT
            MIN(latitude) as min_lat, MAX(latitude) as max_lat,
            MIN(longitude) as min_lon, MAX(longitude) as max_lon,
            SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) as null_count
        FROM read_csv_auto('{trees_path}', sample_size=1000)
    """).fetchone()
    min_lat, max_lat, min_lon, max_lon, null_count = bounds

    if 40.4 < min_lat < 40.6 and 40.85 < max_lat < 41.0:
        ok(f"Latitude range: {min_lat:.4f} to {max_lat:.4f} (valid NYC)")
    else:
        fail(f"Latitude range: {min_lat} to {max_lat} (NOT NYC)")

    if -74.3 < min_lon < -74.0 and -73.7 < max_lon < -73.5:
        ok(f"Longitude range: {min_lon:.4f} to {max_lon:.4f} (valid NYC)")
    else:
        fail(f"Longitude range: {min_lon} to {max_lon} (NOT NYC)")

    if null_count < 1000:
        ok(f"Null coordinates: {null_count:,} (acceptable)")
    else:
        warn(f"Null coordinates: {null_count:,} (will lose some trees)")

    # Check the census tract column values
    sample_tracts = con.execute(f"""
        SELECT DISTINCT "census tract"
        FROM read_csv_auto('{trees_path}', sample_size=1000)
        WHERE "census tract" IS NOT NULL
        LIMIT 5
    """).fetchall()
    ok(f"Sample census tract values: {[r[0] for r in sample_tracts]}")

    con.close()


print("PLUTO (pluto_25v4.csv)")

pluto_path = os.path.join(DATA_DIR, "pluto_25v4.csv")
if not os.path.exists(pluto_path):
    fail(f"File not found: {pluto_path}")
else:
    size_mb = os.path.getsize(pluto_path) / (1024*1024)
    ok(f"File exists ({size_mb:.1f} MB)")

    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_csv_auto('{pluto_path}', sample_size=1000) LIMIT 5").fetchdf()
    cols = list(df.columns)

    needed_pluto = ['latitude', 'longitude', 'landuse', 'lotarea', 'bldgarea', 'borocode', 'bct2020']
    for c in needed_pluto:
        if c in cols:
            ok(f"Column '{c}' found")
        else:
            matches = [x for x in cols if x.lower() == c.lower()]
            if matches:
                warn(f"Column '{c}' found as '{matches[0]}' (case mismatch)")
            else:
                fail(f"Column '{c}' NOT FOUND. Available: {cols[:15]}...")

    row_count = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{pluto_path}', sample_size=1000)
    """).fetchone()[0]
    if row_count > 800000:
        ok(f"Row count: {row_count:,} (expected ~858K)")
    else:
        warn(f"Row count: {row_count:,} (expected ~858K)")

    # Check landuse code distribution
    lu_dist = con.execute(f"""
        SELECT landuse, COUNT(*) as cnt
        FROM read_csv_auto('{pluto_path}', sample_size=1000)
        WHERE landuse IS NOT NULL
        GROUP BY landuse
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    ok(f"Top land use codes: {[(r[0], r[1]) for r in lu_dist[:5]]}")

    # Check for lat/lon nulls
    null_geo = con.execute(f"""
        SELECT
            SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) as null_lat,
            COUNT(*) as total
        FROM read_csv_auto('{pluto_path}', sample_size=1000)
    """).fetchone()
    null_pct = 100.0 * null_geo[0] / null_geo[1]
    if null_pct < 5:
        ok(f"Null lat/lon: {null_geo[0]:,} of {null_geo[1]:,} ({null_pct:.1f}%)")
    else:
        warn(f"Null lat/lon: {null_geo[0]:,} of {null_geo[1]:,} ({null_pct:.1f}%) - high, but usable")

    # Check bct2020 format (this is borough + census tract 2020)
    sample_bct = con.execute(f"""
        SELECT DISTINCT bct2020
        FROM read_csv_auto('{pluto_path}', sample_size=1000)
        WHERE bct2020 IS NOT NULL
        LIMIT 5
    """).fetchall()
    ok(f"Sample bct2020 values: {[r[0] for r in sample_bct]}")
    print(f"         Note: bct2020 = borough code + census tract. You can join")
    print(f"         to tract shapefiles using this field.")

    con.close()


print("HEAT VULNERABILITY INDEX (hvi_rankings.csv)")

hvi_path = os.path.join(DATA_DIR, "hvi_rankings.csv")
if not os.path.exists(hvi_path):
    fail(f"File not found: {hvi_path}")
else:
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_csv_auto('{hvi_path}') LIMIT 5").fetchdf()
    cols = list(df.columns)
    ok(f"File exists. Columns: {cols}")

    row_count = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{hvi_path}')
    """).fetchone()[0]
    ok(f"Row count: {row_count} (184 ZIP codes)")

    # Check HVI score range
    stats = con.execute(f"""
        SELECT
            MIN(COLUMNS(*)::FLOAT) as min_val,
            MAX(COLUMNS(*)::FLOAT) as max_val
        FROM (
            SELECT * EXCLUDE("ZIP Code Tabulation Area (ZCTA) 2020")
            FROM read_csv_auto('{hvi_path}')
        )
    """)
    try:
        hvi_stats = con.execute(f"""
            SELECT
                MIN("Heat Vulnerability Index (HVI)") as min_hvi,
                MAX("Heat Vulnerability Index (HVI)") as max_hvi,
                AVG("Heat Vulnerability Index (HVI)") as avg_hvi
            FROM read_csv_auto('{hvi_path}')
        """).fetchone()
        ok(f"HVI range: {hvi_stats[0]} to {hvi_stats[1]}, avg: {hvi_stats[2]:.2f}")
    except Exception as e:
        warn(f"Could not parse HVI values: {e}")

    print(f"         Note: This is by ZIP code, not census tract. You will")
    print(f"         need to join via ZIP <-> tract crosswalk or use it as")
    print(f"         a coarser overlay. This is your FALLBACK thermal data.")

    con.close()


print("4. ACS INCOME DATA (ACSDT5Y2024.B19013-Data.csv)")

acs_candidates = [
    "ACSDT5Y2024.B19013-Data.csv",
    "ACSDT5Y2023.B19013-Data.csv",
    "ACSDT5Y2022.B19013-Data.csv",
]
acs_path = None
for candidate in acs_candidates:
    p = os.path.join(DATA_DIR, candidate)
    if os.path.exists(p):
        acs_path = p
        break

if acs_path is None:
    # Try any file matching pattern
    for f in os.listdir(DATA_DIR):
        if 'B19013' in f and f.endswith('.csv'):
            acs_path = os.path.join(DATA_DIR, f)
            break

if acs_path is None:
    fail("ACS income file not found. Look for ACSDT5Y*.B19013-Data.csv")
else:
    ok(f"Found: {os.path.basename(acs_path)}")

    con = duckdb.connect()

    df = con.execute(f"""
        SELECT * FROM read_csv_auto('{acs_path}', header=true, skip=1) LIMIT 5
    """).fetchdf()
    cols = list(df.columns)
    ok(f"Columns: {cols[:5]}...")

    row_count = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{acs_path}', header=true, skip=1)
    """).fetchone()[0]
    if row_count > 2000:
        ok(f"Row count: {row_count:,} (expected ~2,328 NYC tracts)")
    else:
        warn(f"Row count: {row_count:,} (seems low for all NYC tracts)")

    sample = con.execute(f"""
        SELECT GEO_ID, NAME, B19013_001E
        FROM read_csv_auto('{acs_path}', header=true, skip=1)
        WHERE B19013_001E IS NOT NULL
        LIMIT 3
    """).fetchall()
    ok(f"Sample rows:")
    for r in sample:
        geo_id = str(r[0])
        tract_fips = geo_id.split("US")[-1] if "US" in geo_id else geo_id[-11:]
        print(f"           GEO_ID={r[0]}, NAME={r[1]}, Income=${r[2]}")
        print(f"           -> Extracted FIPS: {tract_fips}")

    # Count null/missing incomes
    null_income = con.execute(f"""
        SELECT
            SUM(CASE WHEN B19013_001E IS NULL
                      OR TRY_CAST(B19013_001E AS INTEGER) IS NULL
                 THEN 1 ELSE 0 END) as missing,
            COUNT(*) as total
        FROM read_csv_auto('{acs_path}', header=true, skip=1)
    """).fetchone()
    ok(f"Missing income values: {null_income[0]} of {null_income[1]}")
    if null_income[0] > 100:
        warn("Many tracts lack income data (likely group quarters, parks, etc). Normal.")

    con.close()

print("5. CENSUS TRACT BOUNDARIES (shapefile)")

# Look for the shapefile
shp_candidates = []
for root, dirs, files in os.walk(DATA_DIR):
    for f in files:
        if f.endswith('.shp') and 'tract' in f.lower():
            shp_candidates.append(os.path.join(root, f))

if not shp_candidates:
    for d in ['census_tracts', 'tracts', '']:
        check = os.path.join(DATA_DIR, d)
        if os.path.isdir(check):
            for f in os.listdir(check):
                if f.endswith('.shp'):
                    shp_candidates.append(os.path.join(check, f))

if not shp_candidates:
    fail("No shapefile found. Expected tl_2023_36_tract.shp in data directory")
else:
    shp_path = shp_candidates[0]
    ok(f"Found: {shp_path}")

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")

    # Load and filter to NYC
    try:
        nyc_tracts = con.execute(f"""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN COUNTYFP IN ('005','047','061','081','085') THEN 1 END) as nyc
            FROM ST_Read('{shp_path}')
        """).fetchone()
        ok(f"Total NY State tracts: {nyc_tracts[0]:,}")
        ok(f"NYC tracts (5 boroughs): {nyc_tracts[1]:,}")

        if nyc_tracts[1] > 2000:
            ok("NYC tract count looks correct (expected ~2,300)")
        else:
            fail(f"Only {nyc_tracts[1]} NYC tracts found (expected ~2,300)")

        # Check GEOID format
        sample_geoid = con.execute(f"""
            SELECT GEOID, NAMELSAD, COUNTYFP
            FROM ST_Read('{shp_path}')
            WHERE COUNTYFP IN ('005','047','061','081','085')
            LIMIT 3
        """).fetchall()
        ok(f"Sample tract GEOIDs:")
        for r in sample_geoid:
            print(f"           GEOID={r[0]}, Name={r[1]}, County={r[2]}")

        print(f"\n         KEY JOIN INFO:")
        print(f"         Shapefile GEOID format: e.g., '{sample_geoid[0][0]}'")
        print(f"         ACS GEO_ID format: '1400000US{sample_geoid[0][0]}'")
        print(f"         -> To join: SPLIT ACS GEO_ID on 'US' and take the right side")

    except Exception as e:
        fail(f"Could not read shapefile: {e}")

    con.close()

print("LANDSAT SURFACE TEMPERATURE (GeoTIFF)")

tif_candidates = []
for f in os.listdir(DATA_DIR):
    if f.endswith('.tif') or f.endswith('.tiff'):
        tif_candidates.append(os.path.join(DATA_DIR, f))

if not tif_candidates:
    warn("No GeoTIFF found. If GEE export is still running, check back later.")
    print("         You can still proceed with the HVI CSV as thermal fallback.")
else:
    tif_path = tif_candidates[0]
    size_mb = os.path.getsize(tif_path) / (1024*1024)
    ok(f"Found: {os.path.basename(tif_path)} ({size_mb:.1f} MB)")

    try:
        import rasterio
        import numpy as np

        with rasterio.open(tif_path) as src:
            ok(f"CRS: {src.crs}")
            ok(f"Resolution: {src.res[0]:.6f} x {src.res[1]:.6f} degrees")
            ok(f"Size: {src.width} x {src.height} pixels")

            bounds = src.bounds
            ok(f"Bounds: W={bounds.left:.4f}, S={bounds.bottom:.4f}, E={bounds.right:.4f}, N={bounds.top:.4f}")

            # Verify bounds cover NYC
            # lon -74.27 to -73.68, lat 40.49 to 40.92
            if bounds.left < -74.0 and bounds.right > -73.8 and \
               bounds.bottom < 40.6 and bounds.top > 40.8:
                ok("Bounds cover NYC area")
            else:
                fail(f"Bounds may NOT cover NYC! Expected roughly (-74.27, 40.49) to (-73.68, 40.92)")

            data = src.read(1)  # Band 1
            valid = data[data != src.nodata] if src.nodata is not None else data[~np.isnan(data)]

            if len(valid) == 0:
                fail("Raster has no valid pixels!")
            else:
                ok(f"Valid pixels: {len(valid):,}")
                ok(f"Temperature range: {valid.min():.1f} to {valid.max():.1f}")

                # Sanity check: NYC summer surface temp should be roughly 20-50 C
                if 15 < valid.min() < 30 and 35 < valid.max() < 60:
                    ok("Temperature range looks correct for NYC summer (Celsius)")
                elif 280 < valid.min() < 310 and 310 < valid.max() < 340:
                    warn("Values appear to be in KELVIN, not Celsius. Subtract 273.15 during ingestion.")
                elif valid.max() > 10000:
                    warn(f"Values look like raw DN (scale factors not applied). "
                         f"Apply: (DN * 0.00341802 + 149.0) - 273.15 to get Celsius.")
                else:
                    warn(f"Unexpected temp range ({valid.min():.1f} to {valid.max():.1f}). "
                         f"Verify units manually.")

                # Check mean temp for a quick sanity check
                mean_temp = np.mean(valid)
                ok(f"Mean temperature: {mean_temp:.1f}")

    except ImportError:
        warn("rasterio not installed. Run: pip install rasterio numpy")
        print("         Cannot verify GeoTIFF contents without rasterio.")
    except Exception as e:
        fail(f"Error reading GeoTIFF: {e}")

print("7. JOIN COMPATIBILITY CHECK")

print("\nChecking if datasets can actually join to each other...")

try:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")

    # Load tract GEOIDs
    if shp_candidates:
        tract_geoids = con.execute(f"""
            SELECT DISTINCT GEOID
            FROM ST_Read('{shp_candidates[0]}')
            WHERE COUNTYFP IN ('005','047','061','081','085')
            LIMIT 5
        """).fetchall()
        tract_format = tract_geoids[0][0] if tract_geoids else "UNKNOWN"
        ok(f"Tract GEOID format: '{tract_format}' (length {len(str(tract_format))})")

    # Check ACS join key
    if acs_path:
        acs_geoids = con.execute(f"""
            SELECT GEO_ID
            FROM read_csv_auto('{acs_path}', header=true, skip=1)
            LIMIT 3
        """).fetchall()
        raw = str(acs_geoids[0][0])
        extracted = raw.split("US")[-1] if "US" in raw else raw
        ok(f"ACS GEO_ID: '{raw}' -> extracted: '{extracted}'")

        if len(extracted) == len(str(tract_format)):
            ok("ACS and tract GEOID lengths match. Join will work.")
        else:
            warn(f"Length mismatch: ACS={len(extracted)}, Tract={len(str(tract_format))}. "
                 f"May need padding or trimming.")

    # Check PLUTO join possibility
    if os.path.exists(pluto_path):
        pluto_bct = con.execute(f"""
            SELECT DISTINCT bct2020
            FROM read_csv_auto('{pluto_path}', sample_size=1000)
            WHERE bct2020 IS NOT NULL
            LIMIT 3
        """).fetchall()
        bct_val = str(pluto_bct[0][0]) if pluto_bct else "UNKNOWN"
        ok(f"PLUTO bct2020 format: '{bct_val}' (length {len(bct_val)})")
        print(f"         PLUTO bct2020 = boro(1 digit) + tract. To match shapefile GEOID,")
        print(f"         you need to map boro code -> county FIPS:")
        print(f"           1 -> 36061 (Manhattan)")
        print(f"           2 -> 36005 (Bronx)")
        print(f"           3 -> 36047 (Brooklyn)")
        print(f"           4 -> 36081 (Queens)")
        print(f"           5 -> 36085 (Staten Island)")

    # Check tree census tract column
    if os.path.exists(trees_path):
        tree_tracts = con.execute(f"""
            SELECT DISTINCT "census tract"
            FROM read_csv_auto('{trees_path}', sample_size=1000)
            WHERE "census tract" IS NOT NULL
            LIMIT 5
        """).fetchall()
        tt_val = str(tree_tracts[0][0]) if tree_tracts else "UNKNOWN"
        ok(f"Tree 'census tract' format: '{tt_val}'")

        # Also check borocode
        tree_boro = con.execute(f"""
            SELECT DISTINCT borocode
            FROM read_csv_auto('{trees_path}', sample_size=1000)
            LIMIT 5
        """).fetchall()
        ok(f"Tree borocode values: {[r[0] for r in tree_boro]}")
        print(f"         Trees have borocode + census tract separately.")
        print(f"         You can build a GEOID from these to avoid spatial join.")

    con.close()

except Exception as e:
    fail(f"Join compatibility check error: {e}")