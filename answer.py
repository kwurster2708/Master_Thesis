import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# =============================================================================
# HELPER: Get baseline values from database for normalized error scoring
# =============================================================================
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

# =============================================================================
# TABLE 1: active_model_lookup - Fast lookup of active model per device
# =============================================================================
def create_active_model_lookup():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_model_lookup AS
        SELECT 
            lm.device_id, lm.id AS localmodel_id, lm.version_number,
            lm.last_train_time, lm.is_valid, lm.is_compatible, lm.modelbinary_id
        FROM localmodel lm
        INNER JOIN (
            SELECT device_id, MAX(version_number) AS max_version
            FROM localmodel GROUP BY device_id
        ) latest ON lm.device_id = latest.device_id AND lm.version_number = latest.max_version;
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_aml_device ON active_model_lookup(device_id);")
    conn.commit()
    conn.close()
    print("✓ active_model_lookup table created")

# =============================================================================
# TABLE 2: model_performance_pivot - Pivoted metrics with normalized error
# =============================================================================
def create_model_performance_pivot():
    conn = get_connection()
    baselines = get_baselines()
    
    df = pd.read_sql("SELECT localmodel_id, name, value FROM metric WHERE name IN ('mae','rmse','mape')", conn)
    pivot = df.pivot_table(index='localmodel_id', columns='name', values='value', aggfunc='mean').reset_index()
    pivot.columns = ['localmodel_id', 'mae', 'mape', 'rmse']
    
    # Normalized error score: divide by baseline first, then weight
    pivot['overall_error_score'] = (
        (pivot['mae'].fillna(0) / baselines['mae']) * 0.5 +
        (pivot['rmse'].fillna(0) / baselines['rmse']) * 0.3 +
        (pivot['mape'].fillna(0) / baselines['mape']) * 0.2
    )
    
    pivot['update_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pivot.to_sql('model_performance_pivot', conn, if_exists='replace', index=False)
    
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mpp_localmodel ON model_performance_pivot(localmodel_id);")
    conn.commit()
    conn.close()
    print(f"✓ model_performance_pivot table created (baselines: mae={baselines['mae']:.3f}, rmse={baselines['rmse']:.3f}, mape={baselines['mape']:.3f})")

# =============================================================================
# TABLE 3: model_performance_trend - Performance trend & worst timestamp
# =============================================================================
def create_model_performance_trend():
    """Calculate performance trend based on recent vs older metrics"""
    conn = get_connection()
    
    df = pd.read_sql("""
        SELECT mh.localmodel_id, mh.analytics_time, mh.mae, mh.rmse, mh.mape
        FROM modelhealth mh
    """, conn)
    
    results = []
    
    for localmodel_id, group in df.groupby('localmodel_id'):
        group = group.sort_values('analytics_time')
        
        if len(group) < 2:
            trend = 'stable'
            worst_timestamp = group.iloc[-1]['analytics_time'] if len(group) > 0 else None
            worst_score = None
        else:
            recent = group.tail(7)
            older = group.head(len(group) - 7)
            
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
            worst_timestamp = group.loc[worst_idx, 'analytics_time']
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

# =============================================================================
# TABLE 4: device_tag_diagnostics - Tag-level performance with tag value
# =============================================================================
def create_device_tag_diagnostics():
    conn = get_connection()
    cur = conn.cursor()
    baselines = get_baselines()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_tag_diagnostics AS
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
            (
                (mh.mae / {}) * 0.5 + 
                (COALESCE(mh.rmse, 0) / {}) * 0.3 + 
                (COALESCE(mh.mape, 0) / {}) * 0.2
            ) AS performance,
            CASE 
                WHEN mh.outlier_score_value < -5 THEN 'extreme'
                WHEN mh.outlier_score_value < -2 THEN 'strong'
                WHEN mh.outlier_score_value < -1 THEN 'moderate'
                ELSE 'no_outlier'
            END AS outlier_score
        FROM modelhealth mh
        INNER JOIN active_model_lookup aml 
            ON mh.localmodel_id = aml.localmodel_id 
            AND mh.device_id = aml.device_id
        LEFT JOIN tag t ON mh.tag_id = t.id;
    """.format(baselines['mae'], baselines['rmse'], baselines['mape']))
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dtd_device ON device_tag_diagnostics(device_id, localmodel_id);")
    conn.commit()
    conn.close()
    print("✓ device_tag_diagnostics table created")

# =============================================================================
# TABLE 5: feature_sensitivity_top3 - Top 3 features per modelbinary
# =============================================================================
def create_feature_sensitivity_top3():
    conn = get_connection()
    df = pd.read_sql("SELECT id, attribute_sensitivities FROM attributesensitivities WHERE attribute_sensitivities IS NOT NULL", conn)
    results = []
    for _, row in df.iterrows():
        try:
            attrs = json.loads(row['attribute_sensitivities'])
            if isinstance(attrs, dict):
                sorted_attrs = sorted(attrs.items(), key=lambda x: abs(x[1]) if x[1] else 0, reverse=True)[:3]
                results.append({
                    'modelbinary_id': row['id'],
                    'top_feat_1': sorted_attrs[0][0] if len>0 else None, 'sens_1': sorted_attrs[0][1] if len>0 else None,
                    'top_feat_2': sorted_attrs[1][0] if len>1 else None, 'sens_2': sorted_attrs[1][1] if len>1 else None,
                    'top_feat_3': sorted_attrs[2][0] if len>2 else None, 'sens_3': sorted_attrs[2][1] if len>2 else None
                })
        except: pass
    pd.DataFrame(results).to_sql('feature_sensitivity_top3', conn, if_exists='replace', index=False)
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fst_modelbinary ON feature_sensitivity_top3(modelbinary_id);")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_top3 table created")

# =============================================================================
# TABLE 6: feature_sensitivity_historical - Historical avg across versions
# =============================================================================
def create_feature_sensitivity_historical():
    """Average feature sensitivity across all previous (non-active) versions"""
    conn = get_connection()
    
    df = pd.read_sql("""
        SELECT 
            mh.device_id,
            mb.attribute_sensitivities_id,
            as_attr.attribute_sensitivities AS attr_json
        FROM modelhealth mh
        JOIN modelbinary mb ON mh.modelbinary_id = mb.id
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
            'hist_top_1': sorted_attrs[0][0] if len>0 else None, 'hist_sens_1': sorted_attrs[0][1] if len>0 else None,
            'hist_top_2': sorted_attrs[1][0] if len>1 else None, 'hist_sens_2': sorted_attrs[1][1] if len>1 else None,
            'hist_top_3': sorted_attrs[2][0] if len>2 else None, 'hist_sens_3': sorted_attrs[2][1] if len>2 else None
        })
    
    pd.DataFrame(results).to_sql('feature_sensitivity_historical', conn, if_exists='replace', index=False)
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fsh_device ON feature_sensitivity_historical(device_id);")
    conn.commit()
    conn.close()
    print("✓ feature_sensitivity_historical table created")

# =============================================================================
# TABLE 7: device_cross_tag_summary - Cross-tag with differentiated problem patterns
# =============================================================================
def create_device_cross_tag_summary():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_cross_tag_summary AS
        SELECT 
            device_id,
            localmodel_id,
            MAX(performance) AS worst_tag_performance,
            AVG(performance) AS average_tag_performance,
            MIN(outlier_score_value) AS worst_tag_outlier,
            AVG(outlier_score_value) AS average_tag_outlier,
            CAST(SUM(CASE WHEN outlier_score = 'extreme' THEN 1 ELSE 0 END) AS FLOAT) / 
                CAST(COUNT(DISTINCT tag_id) AS FLOAT) AS extreme_ratio,
            CASE 
                WHEN CAST(SUM(CASE WHEN outlier_score = 'extreme' THEN 1 ELSE 0 END) AS FLOAT) / 
                     CAST(COUNT(DISTINCT tag_id) AS FLOAT) > 0.5 THEN 'strongly_device_specific'
                WHEN CAST(SUM(CASE WHEN outlier_score = 'extreme' THEN 1 ELSE 0 END) AS FLOAT) / 
                     CAST(COUNT(DISTINCT tag_id) AS FLOAT) > 0.25 THEN 'moderately_device_specific'
                WHEN CAST(SUM(CASE WHEN outlier_score = 'extreme' THEN 1 ELSE 0 END) AS FLOAT) / 
                     CAST(COUNT(DISTINCT tag_id) AS FLOAT) = 0
                     AND SUM(CASE WHEN outlier_score IN ('strong', 'moderate') THEN 1 ELSE 0 END) > 0
                     THEN 'moderately_tag_specific'
                WHEN CAST(SUM(CASE WHEN outlier_score = 'extreme' THEN 1 ELSE 0 END) AS FLOAT) / 
                     CAST(COUNT(DISTINCT tag_id) AS FLOAT) = 1.0 THEN 'strongly_tag_specific'
                ELSE 'no_specific_issue'
            END AS problem
        FROM device_tag_diagnostics
        GROUP BY device_id, localmodel_id;
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dcts_device ON device_cross_tag_summary(device_id);")
    conn.commit()
    conn.close()
    print("✓ device_cross_tag_summary table created")

# =============================================================================
# TABLE 8: version_history_performance - Excludes active model, uses metric table
# =============================================================================
def create_version_history_performance():
    conn = get_connection()
    baselines = get_baselines()
    
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

# =============================================================================
# MASTER FUNCTION
# =============================================================================
def create_all_optimized_tables():
    print("Creating optimized tables... This may take a while.")
    print("=" * 60)
    
    create_active_model_lookup()
    create_model_performance_pivot()
    create_model_performance_trend()
    create_device_tag_diagnostics()
    create_feature_sensitivity_top3()
    create_feature_sensitivity_historical()
    create_device_cross_tag_summary()
    create_version_history_performance()
    
    print("=" * 60)
    print("All tables created successfully!")

# =============================================================================
# SCHEMA.PY FUNCTIONS - Updated to use pre-calculated tables
# =============================================================================

def get_active_model(conn, device_id):
    """Get the active local model for a given device"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT localmodel_id FROM active_model_lookup 
                    WHERE device_id = {device_id};""")
        row = cur.fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None

def get_device_information(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT key, value FROM tag
        WHERE id IN (SELECT tag_id FROM devicetaglink WHERE device_id = {device_id})""")
    tags_dict = {r[0]: r[1] for r in cur.fetchall()}
    return {"tags": tags_dict}

def get_model_context(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT aml.version_number, aml.is_valid, aml.is_compatible, aml.last_train_time,
        (SELECT MAX(analytics_time) FROM modelhealth WHERE device_id={device_id} AND localmodel_id=aml.localmodel_id) as latest_at
        FROM active_model_lookup aml WHERE aml.device_id = {device_id}""")
    row = cur.fetchone()
    if not row: return {}
    
    model_age_days = None
    training_recency_bucket = "unknown"
    if row[3] and row[4]:
        try:
            analytics_dt = datetime.strptime(str(row[4]), "%Y-%m-%d %H:%M:%S")
            train_dt = datetime.strptime(str(row[3]), "%Y-%m-%d %H:%M:%S")
            model_age_days = (analytics_dt - train_dt).days
            if model_age_days < 7: training_recency_bucket = "fresh"
            elif model_age_days < 30: training_recency_bucket = "recent"
            elif model_age_days < 90: training_recency_bucket = "stale"
            else: training_recency_bucket = "outdated"
        except: pass
    
    return {"version": row[0], "is_valid": row[1], "is_compatible": row[2],
            "model_age_days": model_age_days, "training_recency_bucket": training_recency_bucket}

def get_model_performance(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT mpp.mae, mpp.rmse, mpp.mape, mpp.overall_error_score, mpt.trend, mpt.worst_timestamp, mpt.worst_score
        FROM active_model_lookup aml
        JOIN model_performance_pivot mpp ON aml.localmodel_id = mpp.localmodel_id
        LEFT JOIN model_performance_trend mpt ON aml.localmodel_id = mpt.localmodel_id
        WHERE aml.device_id = {device_id}""")
    row = cur.fetchone()
    if not row: return {}
    return {
        "metrics": {"MAE": row[0], "RMSE": row[1], "MAPE": row[2]},
        "trend": row[4], "overall_error_score": row[3],
        "worst_performance_error_score": row[6], "worst_time_stamp": row[5]
    }

def get_version_history_performance(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT available_versions, avg_mae, avg_mape, avg_rmse 
        FROM version_history_performance WHERE device_id = {device_id}""")
    row = cur.fetchone()
    if not row: return {}
    return {
        "available_versions": row[0], 
        "performance_trend": {"MAE": row[1], "MAPE": row[2], "RMSE": row[3]}
    }

def get_feature_sensitivity(conn, device_id):
    cur = conn.cursor()
    # Current top 3
    cur.execute(f"""SELECT fst.top_feat_1, fst.sens_1, fst.top_feat_2, fst.sens_2, fst.top_feat_3, fst.sens_3
        FROM active_model_lookup aml 
        JOIN feature_sensitivity_top3 fst ON aml.modelbinary_id = fst.modelbinary_id
        WHERE aml.device_id = {device_id}""")
    row = cur.fetchone()
    top3 = []
    if row:
        for i in range(3):
            if row[i*2]: top3.append({row[i*2]: row[i*2+1]})
    
    # Historical top 3
    cur.execute(f"""SELECT fsh.hist_top_1, fsh.hist_sens_1, fsh.hist_top_2, fsh.hist_sens_2, fsh.hist_top_3, fsh.hist_sens_3
        FROM feature_sensitivity_historical fsh
        WHERE fsh.device_id = {device_id}""")
    row = cur.fetchone()
    hist3 = []
    if row:
        for i in range(3):
            if row[i*2]: hist3.append({row[i*2]: row[i*2+1]})
    
    return {
        "Top 3 features": {"top features + sensitivity": top3},
        "Historical Top 3": {"top historical features": hist3}
    }

def get_tag_diagnostics(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT tag_id, tag_value, performance, outlier_score_value, outlier_score, analytics_time
        FROM device_tag_diagnostics WHERE device_id = {device_id}
        ORDER BY analytics_time DESC LIMIT 10""")
    rows = cur.fetchall()
    result = {}
    for r in rows:
        result[f"Tag_{r[0]}_{r[1]}"] = {
            "performance": r[2], 
            "outlier_score_value": r[3], 
            "outlier_score": r[4], 
            "analytics_timeframe": r[5]
        }
    return result

def get_cross_tag_diagnostics(conn, device_id):
    cur = conn.cursor()
    cur.execute(f"""SELECT worst_tag_performance, average_tag_performance, worst_tag_outlier, 
        average_tag_outlier, problem, extreme_ratio
        FROM device_cross_tag_summary WHERE device_id = {device_id}""")
    row = cur.fetchone()
    if not row: return {}
    return {
        "worst_tag_performance": row[0], 
        "average_tag_performance": row[1],
        "worst_tag_outlier": row[2], 
        "average_tag_outlier": row[3], 
        "problem": row[4],
        "extreme_ratio": row[5]
    }

def get_full_schema(conn, device_id, include_model_performance=True, include_feature_sensitivity=True):
    localmodel_id = get_active_model(conn, device_id)
    schema = {
        "Device Information": get_device_information(conn, device_id),
        "Active Model Context": get_model_context(conn, device_id),
    }
    if include_model_performance:
        schema["Active Model Performance"] = get_model_performance(conn, device_id)
        schema["Version History Performance"] = get_version_history_performance(conn, device_id)
    if include_feature_sensitivity:
        schema["Feature Sensitivity"] = get_feature_sensitivity(conn, device_id)
    schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
    schema["Cross Tag Diagnostics"] = get_cross_tag_diagnostics(conn, device_id)
    return schema


if __name__ == "__main__":
    create_all_optimized_tables()
