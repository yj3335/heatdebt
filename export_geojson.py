import duckdb
import json
import os

DB_PATH = "heatdebt.duckdb"
OUT_PATH = os.path.join("frontend", "tracts.geojson")

os.makedirs("frontend", exist_ok=True)

con = duckdb.connect(DB_PATH, read_only=True)
con.execute("LOAD spatial;")

print("Exporting GeoJSON...")

rows = con.execute("""
    SELECT
        tract_id,
        tract_name,
        borough,
        tree_count,
        trees_per_hectare,
        impervious_pct,
        median_income,
        tree_deficit_score,
        impervious_score,
        income_vuln_score,
        heat_debt_score,
        ST_AsGeoJSON(geom) AS geojson_geom
    FROM heat_debt_final
    WHERE geom IS NOT NULL
""").fetchall()

features = []
for r in rows:
    feature = {
        "type": "Feature",
        "properties": {
            "tract_id": r[0],
            "tract_name": r[1],
            "borough": r[2],
            "tree_count": r[3],
            "trees_per_hectare": float(r[4]) if r[4] else 0,
            "impervious_pct": float(r[5]) if r[5] else 0,
            "median_income": r[6],
            "tree_deficit_score": float(r[7]) if r[7] else 0,
            "impervious_score": float(r[8]) if r[8] else 0,
            "income_vuln_score": float(r[9]) if r[9] else 0,
            "heat_debt_score": float(r[10]) if r[10] else 0,
        },
        "geometry": json.loads(r[11])
    }
    features.append(feature)

geojson = {
    "type": "FeatureCollection",
    "features": features
}

with open(OUT_PATH, "w") as f:
    json.dump(geojson, f)

size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
print(f"Exported {len(features):,} tracts to {OUT_PATH} ({size_mb:.1f} MB)")

con.close()
