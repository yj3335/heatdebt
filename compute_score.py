import duckdb
import os

DB_PATH = "heatdebt.duckdb"

con = duckdb.connect(DB_PATH)
con.execute("LOAD spatial;")

print("Assembling tract-level metrics...\n")

con.execute("""
    CREATE OR REPLACE TABLE tract_metrics AS
    SELECT
        t.GEOID AS tract_id,
        t.tract_name,
        t.county_fips,
        t.ALAND AS land_area_sqm,

        -- Tree metrics
        COALESCE(tr.tree_count, 0) AS tree_count,
        COALESCE(tr.avg_tree_diameter, 0) AS avg_tree_diameter,
        COALESCE(tr.healthy_trees, 0) AS healthy_trees,
        COALESCE(tr.species_count, 0) AS species_count,

        -- Impervious surface from PLUTO
        COALESCE(ip.total_lots, 0) AS total_lots,
        COALESCE(ip.heat_lots, 0) AS heat_lots,
        COALESCE(ip.impervious_pct, 0) AS impervious_pct,

        -- Income
        COALESCE(inc.median_income, 0) AS median_income,

        -- Derived: trees per hectare (ALAND is in sq meters)
        CASE WHEN t.ALAND > 0 THEN
            ROUND(COALESCE(tr.tree_count, 0) * 10000.0 / t.ALAND, 2)
        ELSE 0 END AS trees_per_hectare,

        -- Borough name for readability
        CASE t.county_fips
            WHEN '005' THEN 'Bronx'
            WHEN '047' THEN 'Brooklyn'
            WHEN '061' THEN 'Manhattan'
            WHEN '081' THEN 'Queens'
            WHEN '085' THEN 'Staten Island'
        END AS borough,

        t.geom

    FROM tracts t
    LEFT JOIN trees_per_tract tr ON t.GEOID = tr.tract_geoid
    LEFT JOIN impervious_per_tract ip ON t.GEOID = ip.tract_geoid
    LEFT JOIN income inc ON t.GEOID = inc.tract_geoid
""")

count = con.execute("SELECT COUNT(*) FROM tract_metrics").fetchone()[0]
print(f"Assembled metrics for {count:,} tracts")

# Check join coverage
coverage = con.execute("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN tree_count > 0 THEN 1 ELSE 0 END) AS has_trees,
        SUM(CASE WHEN total_lots > 0 THEN 1 ELSE 0 END) AS has_pluto,
        SUM(CASE WHEN median_income > 0 THEN 1 ELSE 0 END) AS has_income
    FROM tract_metrics
""").fetchone()
print(f"  Tracts with tree data: {coverage[1]:,} / {coverage[0]:,}")
print(f"  Tracts with PLUTO data: {coverage[2]:,} / {coverage[0]:,}")
print(f"  Tracts with income data: {coverage[3]:,} / {coverage[0]:,}")

print("\nComputing Heat Debt Score...")

con.execute("""
    CREATE OR REPLACE TABLE heat_debt_scored AS
    SELECT
        tract_id,
        tract_name,
        borough,
        county_fips,
        land_area_sqm,
        tree_count,
        avg_tree_diameter,
        healthy_trees,
        species_count,
        trees_per_hectare,
        total_lots,
        heat_lots,
        impervious_pct,
        median_income,

        -- Component 1: Tree deficit (fewer trees per hectare = higher score)
        -- Using percentile rank: what fraction of tracts have MORE trees
        PERCENT_RANK() OVER (ORDER BY trees_per_hectare DESC) AS tree_deficit_score,

        -- Component 2: Impervious surface (more impervious = higher score)
        PERCENT_RANK() OVER (ORDER BY impervious_pct ASC) AS impervious_score,

        -- Component 3: Income vulnerability (lower income = higher score)
        -- Tracts with 0 income (parks, airports) get neutral 0.5
        CASE WHEN median_income > 0 THEN
            PERCENT_RANK() OVER (
                ORDER BY CASE WHEN median_income > 0 THEN median_income ELSE NULL END DESC
            )
        ELSE 0.5 END AS income_vuln_score,

        geom

    FROM tract_metrics
""")

con.execute("""
    CREATE OR REPLACE TABLE heat_debt_final AS
    SELECT
        *,
        ROUND(
            0.40 * tree_deficit_score
          + 0.30 * impervious_score
          + 0.30 * income_vuln_score
        , 4) AS heat_debt_score
    FROM heat_debt_scored
    ORDER BY heat_debt_score DESC
""")

print("\nTop 15 Most Heat-Indebted Census Tracts:")
print("-" * 95)
print(f"{'Rank':>4}  {'Tract':<28} {'Borough':<15} {'Trees':>6} {'Imperv%':>8} {'Income':>10} {'Score':>7}")
print("-" * 95)

top = con.execute("""
    SELECT tract_name, borough, tree_count, impervious_pct,
           median_income, heat_debt_score
    FROM heat_debt_final
    ORDER BY heat_debt_score DESC
    LIMIT 15
""").fetchall()

for i, r in enumerate(top, 1):
    income_str = f"${r[4]:,}" if r[4] > 0 else "N/A"
    print(f"{i:>4}  {r[0]:<28} {r[1]:<15} {r[2]:>6} {r[3]:>7.1f}% {income_str:>10} {r[5]:>7.4f}")

print()

# Borough-level summary
print("Borough Summary:")
print("-" * 75)
borough_stats = con.execute("""
    SELECT
        borough,
        COUNT(*) AS tracts,
        ROUND(AVG(heat_debt_score), 4) AS avg_score,
        ROUND(AVG(tree_count), 0)::INTEGER AS avg_trees,
        ROUND(AVG(impervious_pct), 1) AS avg_imperv,
        ROUND(AVG(CASE WHEN median_income > 0 THEN median_income END), 0)::INTEGER AS avg_income
    FROM heat_debt_final
    GROUP BY borough
    ORDER BY avg_score DESC
""").fetchall()

for r in borough_stats:
    print(f"  {r[0]:<15} {r[1]:>4} tracts | Score: {r[2]:.4f} | "
          f"Trees: {r[3]:>5} | Imperv: {r[4]:>5.1f}% | Income: ${r[5]:,}")

# Score distribution
print("\nScore Distribution:")
dist = con.execute("""
    SELECT
        CASE
            WHEN heat_debt_score >= 0.8 THEN 'Critical (0.8-1.0)'
            WHEN heat_debt_score >= 0.6 THEN 'High (0.6-0.8)'
            WHEN heat_debt_score >= 0.4 THEN 'Moderate (0.4-0.6)'
            WHEN heat_debt_score >= 0.2 THEN 'Low (0.2-0.4)'
            ELSE 'Minimal (0.0-0.2)'
        END AS tier,
        COUNT(*) AS tracts
    FROM heat_debt_final
    GROUP BY tier
    ORDER BY tier DESC
""").fetchall()
for r in dist:
    bar = "#" * (r[1] // 10)
    print(f"  {r[0]:<25} {r[1]:>5} tracts  {bar}")

con.close()
print(f"\nScoring complete. Results saved in {DB_PATH}")
