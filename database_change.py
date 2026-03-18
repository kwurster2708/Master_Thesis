import sqlite3
import pandas as pd
import json
import numpy as np
from datetime import datetime

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# --- Create Helper Functions --- #
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

Underperforming (49): Overall Error Score above 1.1 - performing worse than predicting the mean (use overall error score from active model)
Low Accuracy (84): Overall Error Score 1.1 or below but high RMSE values (for RMSE value use threshold use baseline if 10% higher than baseline - high RMSE)
Partial Outlier (25): Are outliers for some tags but not all (outlier: warning count above 50% and under 75% and or extreme ratio below 50% and above 25%)
Full Outlier (1): Good RMSE but highly different from other models (extreme ratio above 50% or warning count above 75%)
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
     ORDER BY update_time DESC LIMIT 1) AS local_rmse,

    (SELECT value FROM metric 
     WHERE name = 'cde.std' 
     AND localmodel_id = aml.localmodel_id 
     ORDER BY update_time DESC LIMIT 1) AS local_std

    FROM active_model_lookup aml;
    """)
    
    data = cur.fetchall()
    
    high_rmse_threshold = rmse['avg'] * 3.5 # the multiplicator is chosen by me
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
        device_id, localmodel_id, local_rmse, local_std = row
        
        if local_rmse is None:
            continue
        
        skill_score = (local_rmse/rmse['avg']) * 2.2
        #if local_std is not None:
            #skill_score = local_std/((local_rmse - rmse['min'])/(rmse['max'] - rmse['min'])) #this calculation is chosen by me
        # else:
        #     skill_score = 1.0/((local_rmse - rmse['min'])/(rmse['max'] - rmse['min'])) #this calculation is chosen by me

        total_tags, warning_count = warning_data.get(device_id, (0, 0))
        warning_pct = (warning_count / total_tags) if total_tags > 0 else 0

        classification = "No Outlier"

        if skill_score < skill_threshold:
            classification = "Underperforming"
        elif local_rmse > high_rmse_threshold:
            classification = "Low Accuracy"
        elif 0.5 <= warning_pct < 1.0:
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


# --- CREATING NEW TABLES IN DATABASE --- #

# --- Device Active Model Table --- #
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

# --- Active Model Performance Table --- #
def create_model_performance_pivot():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DROP TABLE IF EXISTS model_performance_pivot")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS model_performance_pivot AS
                SELECT * 
                FROM (
                    SELECT mh.device_id, mh.localmodel_id, mh.mae, mh.rmse, mh.mape, 
                    mh.rmse as performance_score,
                    lm.version_number,
                    ROW_NUMBER() OVER (
                        PARTITION BY mh.localmodel_id 
                        ORDER BY mh.analytics_time DESC
                    ) as rn
                    FROM modelhealth mh
                    JOIN tag t ON mh.tag_id = t.id
                    JOIN  localmodel lm ON mh.localmodel_id = lm.id
                WHERE t.key = 'All' )
                WHERE rn = 1;
                 """)
    
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                idx_mpp_localmodel_id ON model_performance_pivot (localmodel_id);""")
    conn.commit()
    conn.close()
    print(f"✓ model_performance_pivot table created")

# --- Active Model Performance Summary Table --- #
def create_model_performance_trend():
    """Calculate performance trend based on recent vs older metrics"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DROP TABLE IF EXISTS model_performance_trend")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS model_performance_trend AS
    WITH base AS (
        SELECT 
            mh.localmodel_id,
            mh.analytics_time,
            COALESCE(mh.mape, mh.mae) AS metric_value,
        CASE 
            WHEN mh.mape IS NOT NULL THEN 'MAPE'
            ELSE 'MAE'
        END AS metric_used
    FROM modelhealth mh
    WHERE mh.tag_id = (
        SELECT id FROM tag WHERE key = 'All'
    )
),

ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY localmodel_id 
            ORDER BY analytics_time DESC
        ) AS rn
    FROM base
),

comparison AS (
    SELECT 
        localmodel_id,

        -- latest 3 avg
        AVG(CASE WHEN rn <= 3 THEN metric_value END) AS avg_recent,

        -- past avg
        AVG(CASE WHEN rn > 3 THEN metric_value END) AS avg_past

    FROM ranked
    GROUP BY localmodel_id
),

worst AS (
    SELECT 
        localmodel_id,
        analytics_time AS worst_timestamp,
        metric_value AS worst_value,
        metric_used
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY localmodel_id 
                   ORDER BY metric_value DESC
               ) AS rn_worst
        FROM base
    )
    WHERE rn_worst = 1
)

SELECT 
    c.localmodel_id,

    CASE 
        WHEN c.avg_past IS NULL THEN 'stable'
        WHEN c.avg_recent < c.avg_past * 0.90 THEN 'improving'
        WHEN c.avg_recent > c.avg_past * 1.10 THEN 'degrading'
        ELSE 'stable'
    END AS trend,

    w.worst_timestamp,
    w.worst_value,
    w.metric_used

FROM comparison c
JOIN worst w 
    ON c.localmodel_id = w.localmodel_id;
""")
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mpt_localmodel ON model_performance_trend(localmodel_id);")
    conn.commit()
    conn.close()
    print("✓ model_performance_trend table created")

# --- Device Model Version History Table --- #
def create_version_history_performance():
    conn = get_connection()
    
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS version_history_performance")
    cur.execute("""CREATE TABLE IF NOT EXISTS version_history_performance AS
    WITH ranked AS (
        SELECT 
            device_id,
            localmodel_id,
            version_number,
            performance_score,
            ROW_NUMBER() OVER (
                PARTITION BY device_id 
                ORDER BY version_number DESC
            ) AS rn
        FROM model_performance_pivot),

latest AS (
    SELECT * FROM ranked
    WHERE rn = 1
),

historical AS (
    SELECT * FROM ranked
    WHERE rn > 1
),

comparison AS (
    SELECT 
        l.device_id,
        l.performance_score AS recent,
        (
            SELECT AVG(h.performance_score)
            FROM historical h
            WHERE h.device_id = l.device_id
        ) AS avg_past
    FROM latest l
)

SELECT 
    c.device_id,
    c.avg_past,

    CASE 
        WHEN c.avg_past IS NULL THEN 'stable'
        WHEN c.recent < c.avg_past * 0.90 THEN 'improving'
        WHEN c.recent > c.avg_past * 1.10 THEN 'degrading'
        ELSE 'stable'
    END AS trend,
    
    c.recent 

FROM comparison c
""")
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vhp_device ON version_history_performance(device_id);")
    conn.commit()
    conn.close()
    print("✓ version_history_performance table created (excludes active model, uses metric table)")

# --- Model Feature Importance Table --- #
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
                                      if x[1] else 0, reverse=True)[:3]
                results.append({"modelbinary_id": row["id"],
                                "top_feature_1": sorted_attrs[0][0] if len(sorted_attrs) > 0 else None,
                                "importance_1": sorted_attrs[0][1] if len(sorted_attrs) > 0 else None,
                                "top_feature_2": sorted_attrs[1][0] if len(sorted_attrs) > 1 else None,
                                "importance_2": sorted_attrs[1][1] if len(sorted_attrs) > 1 else None,
                                "top_feature_3": sorted_attrs[2][0] if len(sorted_attrs) > 2 else None,
                                "importance_3": sorted_attrs[2][1] if len(sorted_attrs) > 2 else None})
        except: pass
    pd.DataFrame(results).to_sql("feature_sensitivity_top3", conn, if_exists="replace", index=False)
    
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                    idx_fst_modelbinary ON feature_sensitivity_top3 (modelbinary_id);""")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_top3 table created")
    
# --- Historical Feature Sensitivity Table --- #
def create_feature_sensitivity_historical():
    """Average feature sensitivity across all previous (non-active) versions"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS feature_sensitivity_historical")
    
    df = pd.read_sql("""
        SELECT 
            device_id,
            attribute_sensitivities_id,
            attr_json
        FROM (SELECT 
            lm.device_id,
            lm.version_number,
            mb.attribute_sensitivities_id,
            as_attr.attribute_sensitivities AS attr_json,
            ROW_NUMBER() OVER (
            PARTITION BY lm.device_id 
            ORDER BY lm.version_number DESC
            ) AS rn
        FROM localmodel lm
        JOIN modelbinary mb ON lm.modelbinary_id = mb.id
        JOIN attributesensitivities as_attr ON mb.attribute_sensitivities_id = as_attr.id)
        WHERE rn > 1
    """, conn)
    
    all_attrs = {}
    for _, row in df.iterrows():
        try:
            attrs = json.loads(row['attr_json'])
            if row['device_id'] not in all_attrs:
                all_attrs[row['device_id']] = {}
            for feat, val in attrs.items():
                if feat not in all_attrs[row['device_id']]:
                    all_attrs[row['device_id']][feat] = []
                all_attrs[row['device_id']][feat].append(val)
        except: pass
    
    results = []
    for device_id, feat_vals in all_attrs.items():
        avg_attrs = {k: np.mean(v) for k, v in feat_vals.items()}
        sorted_attrs = sorted(avg_attrs.items(), key=lambda x: abs(x[1]) if x[1] else 0, reverse=True)[:3]
        results.append({
            'device_id': device_id,
            'hist_top_1': sorted_attrs[0][0] if len(sorted_attrs) > 0 else None, 
            'hist_sens_1': sorted_attrs[0][1] if len(sorted_attrs) > 0 else None,
            'hist_top_2': sorted_attrs[1][0] if len(sorted_attrs) > 1 else None, 
            'hist_sens_2': sorted_attrs[1][1] if len(sorted_attrs) > 1 else None,
            'hist_top_3': sorted_attrs[2][0] if len(sorted_attrs) > 2 else None, 
            'hist_sens_3': sorted_attrs[2][1] if len(sorted_attrs) > 2 else None
        })
    
    pd.DataFrame(results).to_sql('feature_sensitivity_historical', conn, if_exists='replace', index=False)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fsh_device ON feature_sensitivity_historical(device_id);")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_historical table created")

# --- Device Tag Model Diagnostics Table --- #
def create_device_tag_diagnostics():  
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS device_tag_diagnostics")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS device_tag_diagnostics AS
                WITH ranked AS (
                SELECT mh.device_id, mh.localmodel_id, mh.tag_id,
                mh.analytics_time, mh.mae, mh.mape, mh.rmse, mh.outlier_score_value,
                
                ROW_NUMBER() OVER (
                PARTITION BY mh.device_id, mh.tag_id
                ORDER BY mh.analytics_time DESC
                ) AS rn

                FROM modelhealth mh)
                
                SELECT
                mh.device_id,
                mh.localmodel_id,
                mh.tag_id,
                t.value AS tag_value,
                mh.analytics_time,
                mh.mae,
                mh.mape,
                mh.rmse,
                
                mh.rmse AS performance,
                
                mh.outlier_score_value,
                
                CASE 
                    WHEN mh.outlier_score_value < -10 THEN 'extreme'
                    WHEN mh.outlier_score_value < -5 THEN 'strong'
                    WHEN mh.outlier_score_value < -2 THEN 'moderate'
                    ELSE 'no_outlier'
                END AS outlier_score
                
                FROM ranked mh
                
                INNER JOIN active_model_lookup aml ON mh.localmodel_id = aml.localmodel_id
                AND mh.device_id = aml.device_id
                LEFT JOIN tag t ON mh.tag_id = t.id
                
                WHERE mh.rn = 1 AND t.value IS NOT 'All';
                """)
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_dtd_device 
                ON device_tag_diagnostics (device_id, localmodel_id);""")
    conn.commit()
    conn.close()
    print("✓ device_tag_diagnostics table created")
    
# --- Device Tag Cross Analytics Table --- #
def create_device_cross_tag_summary():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS device_cross_tag_summary")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_cross_tag_summary AS

    WITH base AS (
        SELECT
            device_id,
            localmodel_id,
            tag_id,
            tag_value,
            performance,
            outlier_score_value,
            outlier_score
        FROM device_tag_diagnostics
    ),

    perf_rank AS (
        SELECT *,
        ROW_NUMBER() OVER(
            PARTITION BY device_id, localmodel_id
            ORDER BY performance DESC
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

            MAX(performance) AS worst_tag_performance,
            AVG(performance) AS average_tag_performance,

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
                 AND agg.average_tag_performance > 1.2
            THEN 'device_specific'


            /* SAME TAG worst in both categories */
            WHEN worst_perf.worst_perf_tag = worst_out.worst_outlier_tag
            THEN 'tag_specific'


            /* BAD performance but few outliers */
            WHEN agg.average_tag_performance > 1.2
                 AND (CAST(outlier_count AS FLOAT)/tag_count) < 0.2
            THEN 'tag_specific'


            /* GOOD performance and few outliers */
            WHEN agg.average_tag_performance < 1.2
                 AND (CAST(outlier_count AS FLOAT)/tag_count) < 0.2
            THEN 'non_specific'


            /* MANY outliers but predictions still good */
            WHEN agg.average_tag_performance < 1.2
                 AND (CAST(outlier_count AS FLOAT)/tag_count) >= 0.3
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
    
    # create_active_model_lookup()
    # create_model_performance_pivot()
    # create_model_performance_trend()
    # create_device_tag_diagnostics()
    # create_feature_sensitivity_top3()
    # create_feature_sensitivity_historical()
    # create_device_cross_tag_summary()
    # create_version_history_performance()
    create_outlier_classification_table()
    
    print("=" * 60)
    print("All tables created successfully!")
    
create_all_optimized_tables()