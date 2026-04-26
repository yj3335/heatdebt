import duckdb

con = duckdb.connect("heatdebt.duckdb")
con.execute("LOAD spatial;")

con.execute("DROP TABLE IF EXISTS trees_per_tract")
con.execute("DROP TABLE IF EXISTS trees")

con.execute("""
    CREATE TABLE trees AS
    SELECT *,
        CASE CAST(SUBSTRING(CAST(boro_ct AS VARCHAR), 1, 1) AS INTEGER)
            WHEN 1 THEN '36061'
            WHEN 2 THEN '36005'
            WHEN 3 THEN '36047'
            WHEN 4 THEN '36081'
            WHEN 5 THEN '36085'
        END || SUBSTRING(CAST(boro_ct AS VARCHAR), 2) AS geoid
    FROM trees_raw
""")

r = con.execute("""
    SELECT COUNT(DISTINCT t.geoid) as tree_tracts,
           COUNT(DISTINCT CASE WHEN tr.GEOID IS NOT NULL THEN t.geoid END) as matched
    FROM (SELECT DISTINCT geoid FROM trees) t
    LEFT JOIN tracts tr ON t.geoid = tr.GEOID
""").fetchone()
print(f"Tree tracts: {r[0]}, Matched to shapefile: {r[1]}")
print(f"Match rate: {100*r[1]/r[0]:.1f}%")

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
print(f"Aggregated into {count} tracts")

con.close()