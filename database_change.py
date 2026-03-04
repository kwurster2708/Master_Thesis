import sqlite3
import pandas as pd
import json
import numpy as np
from datetime import datetime

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# --- Label Active Model in each device --- #
"""Giving the devices/first models lables according to the outliers

Underperforming (49): Skill score below 1.0 - performing worse than predicting the mean 
Low Accuracy (84): Skill score above 1.0 but high RMSE values 
Partial Outlier (25): Are outliers for some tags but not all
Full Outlier (1): Good RMSE but highly different from other models 
No Outlier: Does not belong to any of the above categories based on the outlier score value

Outlier based on the active model for the device.
"""

# --- CREATING NEW TABLES IN DATABASE --- #

# --- Helper functions ---#
def get_baseline_values():
    """Calculate baseline values (medians) from all models for normalization"""
    conn = get_connection()
    df = pd.read_sql("""
        SELECT name, value FROM metric 
        WHERE name IN ('mae', 'rmse', 'mape')
    """, conn)
    
    baselines = {}
    for name in ['mae', 'rmse', 'mape']:
        vals = df[df['name'] == name]['value']
        baselines[name] = vals.median() if len(vals) > 0 else 1.0
    
    conn.close()
    return baselines  # Returns {'mae': X, 'rmse': Y, 'mape': Z}

BASELINES = None  # Will be populated on first use

def get_baselines():
    global BASELINES
    if BASELINES is None:
        BASELINES = get_baseline_values()
    return BASELINES

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
    baselines = get_baselines()
    
    df = pd.read_sql("""SELECT localmodel_id, name, value
                     FROM metric WHERE name IN ('mae', 'rmse', 'mape')""", conn)
    pivot = df.pivot_table(index="localmodel_id", columns="name", values="value",
                           aggfunc = 'mean').reset_index()
    
    pivot.columns = ["localmodel_id", "mae", "rmse", "mape"]
    pivot['overall_error_score'] = (
        (pivot['mae'].fillna(0) / baselines['mae']) * 0.5 +
        (pivot['rmse'].fillna(0) / baselines['rmse']) * 0.3 +
        (pivot['mape'].fillna(0) / baselines['mape']) * 0.2
    )
    pivot.to_sql("model_performance_pivot", conn, if_exists="replace", index=False)
    cur = conn.cursor()
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                idx_mpp_localmodel_id ON model_performance_pivot (localmodel_id);""")
    conn.commit()
    conn.close()
    print(f"✓ model_performance_pivot table created")

# --- Active Model Performance Summary Table --- #
def create_model_performance_trend():
    """Calculate performance trend based on recent vs older metrics"""
    conn = get_connection()
    
    df = pd.read_sql("""
        SELECT localmodel_id,
            update_time,
            MAX(CASE WHEN name='mae' THEN value END) AS mae,
            MAX(CASE WHEN name='rmse' THEN value END) AS rmse,
            MAX(CASE WHEN name='mape' THEN value END) AS mape
        FROM metric
        WHERE name IN ('mae','rmse','mape')
        GROUP BY localmodel_id, update_time
    """, conn)
    
    results = []
    
    for localmodel_id, group in df.groupby('localmodel_id'):
        group = group.sort_values('update_time')
        
        if len(group) < 2:
            trend = 'stable'
            worst_timestamp = group.iloc[-1]['update_time'] if len(group) > 0 else None
            worst_score = None
        else:
            recent = group.tail(4)
            older = group.head(len(group) - 4)
            
            if len(older) > 0 and len(recent) > 0:
                recent_mae = recent['mae'].mean()
                older_mae = older['mae'].mean()
                
                if pd.notna(recent_mae) and pd.notna(older_mae) and older_mae > 0:
                    if recent_mae > older_mae * 1.1:
                        trend = 'degrading'
                    elif recent_mae < older_mae * 0.9:
                        trend = 'improving'
                    else:
                        trend = 'stable'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            # Calculate worst score
            baselines = get_baselines()
            group['error_score'] = (
                (group['mae'].fillna(0) / baselines['mae']) * 0.5 +
                (group['rmse'].fillna(0) / baselines['rmse']) * 0.3 +
                (group['mape'].fillna(0) / baselines['mape']) * 0.2
            )
            worst_idx = group['error_score'].idxmax()
            worst_timestamp = group.loc[worst_idx, 'update_time']
            worst_score = group.loc[worst_idx, 'error_score']
        
        results.append({
            'localmodel_id': localmodel_id,
            'trend': trend,
            'worst_timestamp': worst_timestamp,
            'worst_score': worst_score
        })
    
    pd.DataFrame(results).to_sql('model_performance_trend', conn, if_exists='replace', index=False)
    
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mpt_localmodel ON model_performance_trend(localmodel_id);")
    conn.commit()
    conn.close()
    print("✓ model_performance_trend table created")

# --- Device Model Version History Table --- #
def create_version_history_performance():
    conn = get_connection()
    # Get all models EXCEPT the active one per device
    df = pd.read_sql("""
        SELECT 
            lm.device_id,
            mpp.mae,
            mpp.mape,
            mpp.rmse
        FROM localmodel lm
        JOIN model_performance_pivot mpp ON lm.id = mpp.localmodel_id
        WHERE NOT EXISTS (
            SELECT 1 FROM active_model_lookup aml 
            WHERE aml.device_id = lm.device_id AND aml.localmodel_id = lm.id
        )
    """, conn)
    
    results = df.groupby('device_id').agg({
        'mae': 'mean',
        'mape': 'mean', 
        'rmse': 'mean'
    }).reset_index()
    
    results.columns = ['device_id', 'avg_mae', 'avg_mape', 'avg_rmse']
    
    # Add version count
    version_count = df.groupby('device_id').size().reset_index(name='available_versions')
    results = results.merge(version_count, on='device_id')
    
    results.to_sql('version_history_performance', conn, if_exists='replace', index=False)
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vhp_device ON version_history_performance(device_id);")
    conn.commit()
    conn.close()
    print("✓ version_history_performance table created (excludes active model, uses metric table)")

# --- Model Feature Importance Table --- #
def create_feature_sensitivity_top3():
    conn = get_connection()
    df = pd.read_sql("""SELECT id, attribute_sensitivities
                     FROM attributesensitivities WHERE 
                     attribute_sensitivities IS NOT NULL;""", conn)
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
    cur = conn.cursor()
    cur.execute("""CREATE INDEX IF NOT EXISTS 
                    idx_fst_modelbinary ON feature_sensitivity_top3 (modelbinary_id);""")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_top3 table created")
    
# --- Historical Feature Sensitivity Table --- #
def create_feature_sensitivity_historical():
    """Average feature sensitivity across all previous (non-active) versions"""
    conn = get_connection()
    
    df = pd.read_sql("""
        SELECT 
            lm.device_id,
            mb.attribute_sensitivities_id,
            as_attr.attribute_sensitivities AS attr_json
        FROM localmodel lm
        JOIN modelbinary mb ON lm.modelbinary_id = mb.id
        JOIN attributesensitivities as_attr ON mb.attribute_sensitivities_id = as_attr.id
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
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fsh_device ON feature_sensitivity_historical(device_id);")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_historical table created")

# --- Device Tag Model Diagnostics Table --- #
def create_device_tag_diagnostics():  
    conn = get_connection()
    cur = conn.cursor()
    baselines = get_baselines()
    
    cur.execute("""CREATE TABLE IF NOT EXISTS device_tag_diagnostics AS
                WITH ranked AS (
                SELECT mh.device_id, mh.localmodel_id, mh.tag_id,
                mh.analytics_time, mh.mae, mh.mape, mh.rmse,
                mh.mae, mh.mape, mh.rmse, mh.outlier_score_value,
                
                ROW_NUMBER() OVER (
                PARTITION BY mh.device_id, mh.localmodel_id, mh.tag_id
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
                mh.outlier_score_value,
                
                ((mh.mae / {}) * 0.5 + 
                (COALESCE(mh.rmse, 0) / {}) * 0.3 + 
                (COALESCE(mh.mape, 0) / {}) * 0.2) 
                AS performance,
                CASE 
                    WHEN mh.outlier_score_value < -5 THEN 'extreme'
                    WHEN mh.outlier_score_value < -2 THEN 'strong'
                    WHEN mh.outlier_score_value < -1 THEN 'moderate'
                    ELSE 'no_outlier'
                END AS outlier_score
                
                FROM ranked mh
                
                INNER JOIN active_model_lookup aml ON mh.localmodel_id = aml.localmodel_id
                AND mh.device_id = aml.device_id
                LEFT JOIN tag t ON mh.tag_id = t.id
                
                WHERE mh.rn = 1;
                """.format(baselines['mae'], baselines['rmse'], baselines['mape']))
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_dtd_device 
                ON device_tag_diagnostics (device_id, localmodel_id);""")
    conn.commit()
    conn.close()
    print("✓ device_tag_diagnostics table created")
    
# --- Device Tag Cross Analytics Table --- #
def create_device_cross_tag_summary():
    conn = get_connection()
    cur = conn.cursor()
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
            mae,
            mape,
            rmse,
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

            SUM(CASE WHEN outlier_score='extreme' THEN 1 ELSE 0 END) AS extreme_count,
            SUM(CASE WHEN outlier_score IN ('strong','moderate') THEN 1 ELSE 0 END) AS warning_count,
            COUNT(tag_id) AS tag_count

        FROM base
        GROUP BY device_id, localmodel_id
    ),

    worst_perf AS (
        SELECT
            device_id,
            localmodel_id,
            tag_value AS worst_perf_tag,
            mae AS worst_perf_mae,
            rmse AS worst_perf_rmse,
            mape AS worst_perf_mape
        FROM perf_rank
        WHERE perf_rank = 1
    ),

    worst_out AS (
        SELECT
            device_id,
            localmodel_id,
            tag_value AS worst_outlier_tag,
            mae AS worst_out_mae,
            rmse AS worst_out_rmse,
            mape AS worst_out_mape
        FROM outlier_rank
        WHERE out_rank = 1
    )

    SELECT
        agg.device_id,
        agg.localmodel_id,

        agg.worst_tag_performance,
        agg.average_tag_performance,

        agg.worst_tag_outlier,
        agg.average_tag_outlier,

        worst_perf.worst_perf_tag,
        worst_perf.worst_perf_mae,
        worst_perf.worst_perf_rmse,
        worst_perf.worst_perf_mape,

        worst_out.worst_outlier_tag,
        worst_out.worst_out_mae,
        worst_out.worst_out_rmse,
        worst_out.worst_out_mape,

        CAST(extreme_count AS FLOAT)/tag_count AS extreme_ratio,

        CASE

            /* DEVICE ISSUE
               bad performance across many tags
            */
            WHEN (CAST(extreme_count AS FLOAT)/tag_count) >= 0.5
                 AND agg.average_tag_performance > 1.0
            THEN 'device_specific'


            /* SAME TAG worst in both categories */
            WHEN worst_perf.worst_perf_tag = worst_out.worst_outlier_tag
            THEN 'tag_specific'


            /* BAD performance but few outliers */
            WHEN agg.average_tag_performance > 1.0
                 AND (CAST(extreme_count AS FLOAT)/tag_count) < 0.2
            THEN 'tag_specific'


            /* GOOD performance and few outliers */
            WHEN agg.average_tag_performance < 1.0
                 AND (CAST(extreme_count AS FLOAT)/tag_count) < 0.2
            THEN 'non_specific'


            /* MANY outliers but predictions still good */
            WHEN agg.average_tag_performance < 1.0
                 AND (CAST(extreme_count AS FLOAT)/tag_count) >= 0.3
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
                

#def create_all_optimized_tables():
    #print("Creating optimized tables...")
    #print("=" * 60)
    
    #create_active_model_lookup()
    #create_model_performance_pivot()
    #create_model_performance_trend()
    #create_device_tag_diagnostics()
    #create_feature_sensitivity_top3()
    #create_feature_sensitivity_historical()
    #create_device_cross_tag_summary()
    #create_version_history_performance()
    
    #print("=" * 60)
    #print("All tables created successfully!")
    
#create_all_optimized_tables()