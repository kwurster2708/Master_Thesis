"""
Improving the database structure and creating optimized tables for a better lookup in the experiments.
"""

import sqlite3
import pandas as pd
import json

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# Generate Helper Functions
def get_rmse_values():
    """Calculate baseline values (medians) from all models for normalization"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        AVG(CASE WHEN name = 'rmse' THEN value END),
        MAX(CASE WHEN name = 'rmse' THEN value END),
        MIN(CASE WHEN name = 'rmse' THEN value END)
    FROM metric;
    """)
    result = cur.fetchone()
    
    rmse = {
        "avg": result[0],
        "max": result[1],
        "min": result[2]
    }
    conn.close()
    return rmse

RMSE = None  # Will be populated on first use

def get_rmse():
    global RMSE
    if RMSE is None:
        RMSE = get_rmse_values()
    return RMSE


# --- Label Active Model in each device --- #
"""Giving the devices/first models lables according to the outliers

Underperforming: Overall Error Score above 1.1 - performing worse than predicting the mean (use overall error score from active model)
Low Accuracy: Overall Error Score 1.1 or below but high RMSE values (for RMSE value use threshold use baseline if 10% higher than baseline - high RMSE)
Partial Outlier: Are outliers for some tags but not all (outlier: warning count above 50% and under 75% and or extreme ratio below 50% and above 25%)
Full Outlier: Good RMSE but highly different from other models (extreme ratio above 50% or warning count above 75%)
No Outlier: Does not belong to any of the above categories based on the outlier score value

Outlier based on the active model for the device.
"""

def create_outlier_classification_table(db_path: str = "WeatherData.sqlite"):
    conn = sqlite3.connect(db_path)
    rmse = get_rmse()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS device_outlier_classification")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_outlier_classification (
            device_id INT PRIMARY KEY,
            localmodel_id INT,
            outlier_classification VARCHAR(50),
            skill_score REAL,
            rmse_value REAL,
            outlier_ratio REAL
        )
    """)
    
    cur.execute("""
    SELECT
        aml.device_id,
        aml.localmodel_id,
        
    (SELECT value FROM metric 
     WHERE name = 'rmse' 
     AND localmodel_id = aml.localmodel_id 
     ORDER BY update_time DESC LIMIT 1) AS local_rmse

    FROM active_model_lookup aml;
    """)
    
    data = cur.fetchall()
    
    high_rmse_threshold = 11.20 # based on the distribution graph
    skill_threshold = 1.0 # this threshold is given by the Case Study
    
    cur.execute("""
        SELECT 
            aml.device_id,
            COUNT(*) as total_tags,
            SUM(CASE WHEN dtd.outlier_score IN ('moderate', 'strong', 'extreme') THEN 1 ELSE 0 END) as warning_count
        FROM active_model_lookup aml
        JOIN device_tag_diagnostics dtd ON aml.device_id = dtd.device_id AND dtd.localmodel_id = aml.localmodel_id
        GROUP BY aml.device_id, aml.localmodel_id
    """)
    warning_data = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    classifications = []
    for row in data:
        device_id, localmodel_id, local_rmse = row
        
        if local_rmse is None:
            continue
        
        local_nrmse = (local_rmse - rmse["min"])/(rmse['max'] - rmse['min'])
        nrmse_avg = (rmse['avg'] - rmse["min"])/(rmse['max'] - rmse['min'])
        
        relative_score = local_nrmse/nrmse_avg
        skill_score = relative_score/3
        
        total_tags, warning_count = warning_data.get(device_id, (0, 0))
        warning_pct = (warning_count / total_tags) if total_tags > 0 else 0

        classification = "Functioning"

        if skill_score > skill_threshold:
            classification = "Underperforming"
        elif local_rmse > high_rmse_threshold:
            classification = "Low Accuracy"
        elif 0.4 <= warning_pct < 1.0 :
            classification = "Partial Outlier"
        elif warning_pct == 1.0:
            classification = "Full Outlier"

        classifications.append((
            device_id,
            localmodel_id,
            classification,
            skill_score, 
            local_rmse, 
            warning_pct
        ))


    cur.executemany("""
        INSERT INTO device_outlier_classification 
        (device_id, localmodel_id, outlier_classification, skill_score, rmse_value, outlier_ratio)
        VALUES (?, ?, ?, ?, ?, ?)
    """, classifications)

    conn.commit()

    #double check the classification
    cur.execute("""
        SELECT outlier_classification, COUNT(*) 
        FROM device_outlier_classification 
        GROUP BY outlier_classification
        ORDER BY COUNT(*) DESC
    """)
    print("\nClassification Summary:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    conn.close()
    print("\n ✓ Table 'device_outlier_classification' created successfully.")

# Active Model Table
def create_active_model_lookup():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS active_model_lookup AS
                SELECT lm.device_id, lm.id AS
                localmodel_id, lm.version_number, lm.last_train_time,
                lm.is_valid, lm.is_compatible, lm.modelbinary_id
                FROM localmodel lm
                INNER JOIN (
                    SELECT device_id, MAX(version_number) AS max_version
                    FROM localmodel
                    GROUP BY device_id
                ) latest ON lm.device_id = latest.device_id 
                AND lm.version_number = latest.max_version
                """)
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                idx_aml_device ON active_model_lookup (device_id);""")
    conn.commit()
    conn.close()
    print("✓ active_model_lookup table created")

# Model Performance Table 
def create_model_performance_pivot():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DROP TABLE IF EXISTS model_performance_pivot")
    
    cur.execute("""
                CREATE TABLE IF NOT EXISTS model_performance_pivot AS
                SELECT
                    mh.device_id, mh.localmodel_id,  
                    AVG(mh.rmse) AS global_rmse,
                    mh.analytics_time,
                    lm.version_number
                    FROM modelhealth mh
                    JOIN tag t ON mh.tag_id = t.id
                    JOIN  localmodel lm ON mh.localmodel_id = lm.id
                WHERE t.key = 'All' 
                GROUP BY mh.device_id, mh.localmodel_id, mh.analytics_time,
                lm.version_number;""")
    
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                idx_mpp_localmodel_id ON model_performance_pivot (localmodel_id);""")
    conn.commit()
    conn.close()
    print(f"✓ model_performance_pivot table created")

# Seed Model Performance Table
def create_model_performance_metrics():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DROP TABLE IF EXISTS model_performance_metrics")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS model_performance_metrics AS
                SELECT
                    m.localmodel_id,  
                    m.seedmodel_id,
                    m.update_time,
                    AVG(CASE 
                            WHEN m.name = 'rmse' THEN m.value 
                        END) AS "local_rmse"
                FROM metric m
                WHERE m.name = 'rmse' AND m.value IS NOT NULL
                GROUP BY m.localmodel_id, m.update_time, m.seedmodel_id;
                """)
    
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                idx_mpm_localmodel_id ON model_performance_metrics (localmodel_id);""")
    conn.commit()
    conn.close()
    print(f"✓ model_performance_metrics table created")

#  Model Performance Summary Table 
def create_model_performance_trend():
    """Calculate performance trend based on recent vs older metrics"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DROP TABLE IF EXISTS model_performance_trend")
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_performance_trend AS
        WITH base AS (
            SELECT 
                localmodel_id,
                analytics_time,
                global_rmse AS metric_value
            FROM model_performance_pivot
            WHERE global_rmse IS NOT NULL
        ),

        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY localmodel_id
                    ORDER BY datetime(analytics_time) DESC
                ) AS rn
            FROM base
        ),

        comparison AS (
            SELECT 
                localmodel_id,

                -- latest 10 avg
                AVG(CASE WHEN rn <= 10 THEN metric_value END) AS avg_recent,

                -- past avg
                AVG(CASE WHEN rn > 10 THEN metric_value END) AS avg_past

            FROM ranked
            GROUP BY localmodel_id
        )

        SELECT 
            c.localmodel_id,

            CASE 
                WHEN c.avg_past IS NULL THEN 'stable'
                WHEN c.avg_recent < c.avg_past * 0.90 THEN 'improving'
                WHEN c.avg_recent > c.avg_past * 1.10 THEN 'degrading'
                ELSE 'stable'
            END AS global_rmse_trend

        FROM comparison c;
    """)
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mpt_localmodel ON model_performance_trend(localmodel_id);")
    conn.commit()
    conn.close()
    print("✓ model_performance_trend table created")

def create_model_performance_metrics_trend():
    """Calculate local RMSE and concept drift trend based on model_performance_metrics"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS model_performance_metrics_trend")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_performance_metrics_trend AS
        WITH base AS (

            SELECT
                localmodel_id,
                update_time,
                local_rmse AS metric_value
            FROM model_performance_metrics
            WHERE local_rmse IS NOT NULL
        ),

        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY localmodel_id
                    ORDER BY datetime(update_time) DESC
                ) AS rn
            FROM base
        ),

        comparison AS (
            SELECT 
                localmodel_id,

                -- latest 6 avg
                AVG(CASE WHEN rn <= 6 THEN metric_value END) AS avg_recent,

                -- past avg
                AVG(CASE WHEN rn > 6 THEN metric_value END) AS avg_past

            FROM ranked
            GROUP BY localmodel_id
        )

       
            SELECT 
                localmodel_id,

                CASE 
                    WHEN avg_past IS NULL THEN 'stable'
                    WHEN avg_recent < avg_past * 0.90 THEN 'improving'
                    WHEN avg_recent > avg_past * 1.10 THEN 'degrading'
                    ELSE 'stable'
                END AS local_rmse_trend

            FROM comparison;
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS 
        idx_mpmt_localmodel_id ON model_performance_metrics_trend (localmodel_id)
    """)

    conn.commit()
    conn.close()
    print("✓ model_performance_metrics_trend table created")

# Feature Importance Table 
def create_feature_sensitivity_top3():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS feature_sensitivity_top3")
    df = pd.read_sql("""SELECT mb.id, att.attribute_sensitivities
                     FROM attributesensitivities att
                     INNER JOIN (SELECT id, attribute_sensitivities_id
                     FROM modelbinary
                     GROUP BY id) mb on mb.attribute_sensitivities_id = att.id
                     WHERE att.attribute_sensitivities IS NOT NULL;""", conn)
    results = []
    for _, row in df.iterrows():
        try:
            attrs = json.loads(row["attribute_sensitivities"])
            if isinstance(attrs, dict):
                sorted_attrs = sorted(attrs.items(), key=lambda x: abs(x[1]) 
                                      if x[1] else 0, reverse=True)[:8]
                results.append({"modelbinary_id": row["id"],
                                "top_feature_1": sorted_attrs[0][0] if len(sorted_attrs) > 0 else None,
                                "importance_1": sorted_attrs[0][1] if len(sorted_attrs) > 0 else None,
                                "top_feature_2": sorted_attrs[1][0] if len(sorted_attrs) > 1 else None,
                                "importance_2": sorted_attrs[1][1] if len(sorted_attrs) > 1 else None,
                                "top_feature_3": sorted_attrs[2][0] if len(sorted_attrs) > 2 else None,
                                "importance_3": sorted_attrs[2][1] if len(sorted_attrs) > 2 else None,
                                "top_feature_4": sorted_attrs[3][0] if len(sorted_attrs) > 3 else None,
                                "importance_4": sorted_attrs[3][1] if len(sorted_attrs) > 3 else None,
                                "top_feature_5": sorted_attrs[4][0] if len(sorted_attrs) > 4 else None,
                                "importance_5": sorted_attrs[4][1] if len(sorted_attrs) > 4 else None,
                                "top_feature_6": sorted_attrs[5][0] if len(sorted_attrs) > 5 else None,
                                "importance_6": sorted_attrs[5][1] if len(sorted_attrs) > 5 else None,
                                "top_feature_7": sorted_attrs[6][0] if len(sorted_attrs) > 6 else None,
                                "importance_7": sorted_attrs[6][1] if len(sorted_attrs) > 6 else None,
                                "top_feature_8": sorted_attrs[7][0] if len(sorted_attrs) > 7 else None,
                                "importance_8": sorted_attrs[7][1] if len(sorted_attrs) > 7 else None})
        except: pass
    pd.DataFrame(results).to_sql("feature_sensitivity_top3", conn, if_exists="replace", index=False)
    
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                    idx_fst_modelbinary ON feature_sensitivity_top3 (modelbinary_id);""")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_top3 table created")

# Tag Model Diagnostics Table 
def create_seedmodel_diagnostics():  
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS seedmodel_diagnostics")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS seedmodel_diagnostics AS
                SELECT
                sm.id AS seedmodel_id,
                sm.tag_id,
                t.key AS tag_key,
                t.value AS tag_value,
                sm.analytics_time,
                sm.performance_score AS performance_score
                FROM seedmodel sm
                LEFT JOIN tag t ON sm.tag_id = t.id;
                """)
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_smd_tag 
                ON seedmodel_diagnostics (tag_id);""")
    conn.commit()
    conn.close()
    print("✓ seedmodel_diagnostics table created")
    
def create_device_tag_diagnostics():  
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS device_tag_diagnostics")
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS device_tag_diagnostics AS

    WITH averaged AS (
        SELECT
            mh.device_id,
            mh.localmodel_id,
            mh.tag_id,
            mh.analytics_time AS analytics_time,
            AVG(mh.rmse) AS rmse,
            AVG(mh.outlier_score_value) AS outlier_score_value

        FROM modelhealth mh

        WHERE mh.outlier_score_fn = 'local_outlier_factor'

        GROUP BY
            mh.device_id,
            mh.localmodel_id,
            mh.tag_id,
            datetime(mh.analytics_time)
    ),

    ranked AS (
        SELECT
            averaged.*,

            ROW_NUMBER() OVER (
                PARTITION BY 
                    device_id,
                    localmodel_id,
                    tag_id
                ORDER BY datetime(analytics_time) DESC
            ) AS rn

        FROM averaged
    )

    SELECT
        r.device_id,
        r.localmodel_id,
        r.tag_id,
        t.key AS tag_key,
        t.value AS tag_value,
        r.analytics_time AS analytics_time_rmse,
        r.rmse AS global_rmse,
        r.outlier_score_value,

        CASE 
            WHEN r.outlier_score_value < -5 THEN 'extreme'
            WHEN r.outlier_score_value < -3.5 THEN 'strong'
            WHEN r.outlier_score_value < -2 THEN 'moderate'
            ELSE 'no_outlier'
        END AS outlier_score

    FROM ranked r

    LEFT JOIN tag t
        ON r.tag_id = t.id

    INNER JOIN active_model_lookup aml
        ON r.localmodel_id = aml.localmodel_id
       AND r.device_id = aml.device_id

    WHERE r.rn = 1
""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_dtd_device 
                ON device_tag_diagnostics (device_id, localmodel_id);""")
    conn.commit()
    conn.close()
    print("✓ device_tag_diagnostics table created")
    
# Cross Tag Analytics Table 
def create_device_cross_tag_summary():
    conn = get_connection()
    rmse = get_rmse()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS device_cross_tag_summary")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS device_cross_tag_summary AS

    WITH base AS (
        SELECT
            device_id,
            localmodel_id,
            tag_id,
            tag_value,
            global_rmse,
            outlier_score_value,
            outlier_score
        FROM device_tag_diagnostics
        WHERE tag_key <> 'All'
    ),

    perf_rank AS (
        SELECT *,
        ROW_NUMBER() OVER(
            PARTITION BY device_id, localmodel_id
            ORDER BY global_rmse DESC
        ) AS perf_rank
        FROM base
    ),

    outlier_rank AS (
        SELECT *,
        ROW_NUMBER() OVER(
            PARTITION BY device_id, localmodel_id
            ORDER BY outlier_score_value ASC
        ) AS out_rank
        FROM base
    ),

    agg AS (
        SELECT
            device_id,
            localmodel_id,

            MAX(global_rmse) AS worst_tag_performance,
            AVG(global_rmse) AS average_tag_performance,

            MIN(outlier_score_value) AS worst_tag_outlier,
            AVG(outlier_score_value) AS average_tag_outlier,

            SUM(CASE WHEN outlier_score IN ('moderate', 'extreme', 'strong') THEN 1 ELSE 0 END) AS outlier_count,
            COUNT(tag_id) AS tag_count

        FROM base
        GROUP BY device_id, localmodel_id
    ),

    worst_perf AS (
        SELECT
            device_id,
            localmodel_id,
            tag_value AS worst_perf_tag
        FROM perf_rank
        WHERE perf_rank = 1
    ),

    worst_out AS (
        SELECT
            device_id,
            localmodel_id,
            tag_value AS worst_outlier_tag
        FROM outlier_rank
        WHERE out_rank = 1
    )

    SELECT
        agg.device_id,
        agg.localmodel_id,

        worst_perf.worst_perf_tag,
        agg.worst_tag_performance,

        worst_out.worst_outlier_tag, 
        agg.worst_tag_outlier,

        CAST(outlier_count AS FLOAT)/tag_count AS outlier_ratio,

        CASE

            /* DEVICE ISSUE
               bad performance across many tags
            */
            WHEN (CAST(outlier_count AS FLOAT)/tag_count) >= 0.5
                 AND agg.average_tag_performance > {rmse['avg']} * 2
            THEN 'device_specific'


            /* SAME TAG worst in both categories */
            WHEN worst_perf.worst_perf_tag = worst_out.worst_outlier_tag
            THEN 'tag_specific'


            /* BAD performance but few outliers */
            WHEN agg.average_tag_performance > {rmse['avg']} * 2
                AND (CAST(outlier_count AS FLOAT)/tag_count) < 0.2
            THEN 'general_performance_specific'


            /* GOOD performance and few outliers */
            WHEN agg.average_tag_performance < {rmse['avg']}
                 AND (CAST(outlier_count AS FLOAT)/tag_count) < 0.2
            THEN 'non_specific'


            /* MANY outliers but predictions still good */
            WHEN agg.average_tag_performance < {rmse['avg']}
                 AND (CAST(outlier_count AS FLOAT)/tag_count) >= 0.4
            THEN 'model_behavior_change'

            ELSE 'uncertain'

        END AS problem_pattern

    FROM agg
    LEFT JOIN worst_perf
        ON agg.device_id = worst_perf.device_id
        AND agg.localmodel_id = worst_perf.localmodel_id
    LEFT JOIN worst_out
        ON agg.device_id = worst_out.device_id
        AND agg.localmodel_id = worst_out.localmodel_id
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_dcts_device
        ON device_cross_tag_summary(device_id)
    """)

    conn.commit()
    conn.close()
    print("✓ device_cross_tag_diagnostics table created")                     

def create_all_optimized_tables():
    print("Creating optimized tables...")
    print("=" * 60)
    
    create_active_model_lookup()
    create_model_performance_pivot()
    create_model_performance_metrics()
    create_model_performance_trend()
    create_model_performance_metrics_trend()
    create_seedmodel_diagnostics()
    create_device_tag_diagnostics()
    create_feature_sensitivity_top3()
    create_device_cross_tag_summary()
    create_outlier_classification_table()
    
    print("=" * 60)
    print("All tables created successfully!")
    
create_all_optimized_tables()