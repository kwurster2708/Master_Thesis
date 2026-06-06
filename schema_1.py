"""
Creating the first schema for the weather station diagnostics with mainy numerical data representation.
"""
import sqlite3

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# Generate Helper functions
def get_all_outlier_devices(conn):
    """Get all available device_ids """
    cur = conn.cursor()
    classification_list = ("Underperforming", "Low Accuracy", "Partial Outlier", "Full Outlier")
    try:
        cur.execute(f"""SELECT DISTINCT device_id 
                    FROM device_outlier_classification 
                    WHERE outlier_classification IN {classification_list}
                    ORDER BY device_id;""")
        return cur.fetchall()
    except sqlite3.Error:
        return []

def get_modelhealth_outlier_history(conn, device_id):
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT DISTINCT mh.tag_id, t.value
                    FROM modelhealth mh
                    JOIN tag t ON mh.tag_id = t.id
                    WHERE mh.device_id = {device_id} AND t.value != 'All'""")
        result = {}
        for tag_id, tag_value in cur.fetchall():
            mh = get_modelhealth_diagnostics(conn, device_id, tag_id)
            if mh and mh.get("outlier_score_value"):
                result[tag_value] = mh["outlier_score_value"]
        return result
    except sqlite3.Error:
        return {} 

# FUNCTIONS TO CREATE SCHEMA
# Weather Station Information
def get_device_information(conn, device_id):
    """Get diagnostic event information"""
    cur = conn.cursor()
    
    try:
        cur.execute(f"""SELECT key, value
                    FROM tag
                    WHERE id IN (SELECT tag_id
                                FROM devicetaglink
                                WHERE device_id = {device_id}) AND key NOT IN ('All', 'name', 'station_id');
                    """)
        tags_dict = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.execute(f"""SELECT outlier_classification 
                    FROM device_outlier_classification
                    WHERE device_id = {device_id}
                    """)
        classification = cur.fetchone()[0]
                
        return {
                "weather_station_classification": classification,
                "tags": tags_dict,
                "weather_station_id": f"d{device_id}"
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}
   
# Model Performance Context
def get_global_rmse(conn, device_id):
    """Get global RMSE value"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT mpp.global_rmse, mpp.analytics_time
                    FROM active_model_lookup aml
                    JOIN model_performance_pivot mpp
                    ON aml.localmodel_id = mpp.localmodel_id
                    WHERE aml.device_id = {device_id}
                    ORDER BY datetime(mpp.analytics_time) DESC
                    LIMIT 10;""")
        rows = cur.fetchall()
        performance_dict = {
            str(analytics_time): performance_score
            for performance_score, analytics_time in rows
        }
        
        cur.execute(f"""SELECT mpt.global_rmse_trend
                    FROM active_model_lookup aml
                    JOIN model_performance_trend mpt
                    ON aml.localmodel_id = mpt.localmodel_id
                    WHERE aml.device_id = {device_id};""")
        row = cur.fetchone()
        
        if row:
            return {
                "global_rmse_trend": row[0],
                "global_rmse_performance": performance_dict
            }
    
    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")
        
def get_local_rmse(conn, device_id):
    """Get local RMSE value"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT mpm.local_rmse, mpm.update_time
                    FROM active_model_lookup aml
                    JOIN model_performance_metrics mpm
                    ON aml.localmodel_id = mpm.localmodel_id
                    WHERE aml.device_id = {device_id} AND mpm.local_rmse IS NOT NULL
                    ORDER BY datetime(mpm.update_time) DESC
                    LIMIT 10;""")
        rows = cur.fetchall()
        performance_dict = {
            str(update_time): performance_score
            for performance_score, update_time in rows
        }
        
        cur.execute(f"""SELECT mpmt.local_rmse_trend
                    FROM active_model_lookup aml
                    JOIN model_performance_metrics_trend mpmt
                    ON aml.localmodel_id = mpmt.localmodel_id
                    WHERE aml.device_id = {device_id};""")
        row = cur.fetchone()
        
        if row:
            return {
                "local_rmse_trend": row[0],
                "local_rmse_performance": performance_dict
            }
    
    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")

def get_model_performance(conn, device_id):
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT 
            CASE
                WHEN m.name = 'cde.mean' THEN m.value 
            END AS "concept_drift_mean"
                FROM metric m
                JOIN active_model_lookup aml ON m.localmodel_id = aml.localmodel_id
                WHERE aml.device_id = {device_id} AND m.name = 'cde.mean'""")
        
        row = cur.fetchone()
    
    
        return {"Concept Drift": row[0] if row else None,
                "Global RMSE": get_global_rmse(conn, device_id),
                "Local RMSE": get_local_rmse(conn, device_id)
                }
    
    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")

# Feature Importance
def get_feature_sensitivity(conn, device_id):
    """Get feature sensitivity information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT fst.top_feature_1, fst.importance_1, 
                    fst.top_feature_2, fst.importance_2,
                    fst.top_feature_3, fst.importance_3,
                    fst.top_feature_4, fst.importance_4,
                    fst.top_feature_5, fst.importance_5,
                    fst.top_feature_6, fst.importance_6,
                    fst.top_feature_7, fst.importance_7,
                    fst.top_feature_8, fst.importance_8
                    FROM active_model_lookup aml
                    JOIN feature_sensitivity_top3 fst ON
                    aml.modelbinary_id = fst.modelbinary_id
                    WHERE aml.device_id = {device_id}""")
        row = cur.fetchone()
        
        top_features = []
        
        if row:
            for i in range(8):
                if row[i*2+1]: top_features.append({row[i*2]: row[i*2+1]})
        
        features = {k: v for d in top_features for k, v in d.items()}
        
        return features 
    except sqlite3.Error:
        return {}

# Tag Diagnostics   
def get_tag_diagnostics(conn, device_id):
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT DISTINCT mh.tag_id, t.value, t.key
                    FROM modelhealth mh
                    JOIN tag t ON mh.tag_id = t.id
                    WHERE mh.device_id = {device_id}""")
        rows = cur.fetchall()
        result = {}
        for row in rows:
            if row[1] == 'All': 
                result[row[1]] = {
                "latest_diagnostics": get_current_diagnostics(conn, device_id, row[0]),
                "seedmodel_performance_score": get_seedmodel_diagnostics(conn, row[0])
            }
            else:
                result[row[1]] = {
                "latest_diagnostics": get_current_diagnostics(conn, device_id, row[0]),
                "seedmodel_performance_score": get_seedmodel_diagnostics(conn, row[0]),
                "modelhealth_information": get_modelhealth_diagnostics(conn, device_id, row[0])
                }
        return result
    except sqlite3.Error:
        return {}

def get_current_diagnostics(conn, device_id, tag_id):
    """Get current diagnostics information for each tag"""
    cur = conn.cursor()
    try:
        cur.execute("""
                SELECT
                    dtd.analytics_time_rmse,
                    dtd.global_rmse,
                    dtd.outlier_score_value,
                    dtd.outlier_score

                FROM device_tag_diagnostics dtd
                WHERE dtd.device_id = ? AND dtd.tag_id = ?
                ORDER BY dtd.global_rmse DESC;
        """, (device_id, tag_id))

        row = cur.fetchone()
        if not row:
            return "No data available for this tag" 
        result ={
                "analytics_time": str(row[0]),
                "global_rmse": row[1],
                "outlier_score_value": row[2],
                "outlier_score": row[3]
                }
        return result
    
    except sqlite3.Error:
        return {}

def get_modelhealth_diagnostics(conn, device_id, tag_id):
    """Get modelhealth diagnostics information for each tag"""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                mh.analytics_time,
                AVG(mh.rmse) AS rmse,
                AVG(mh.outlier_score_value) AS outlier_score_value

            FROM modelhealth mh
            LEFT JOIN tag t 
                ON mh.tag_id = t.id
                
            JOIN active_model_lookup aml
                ON mh.localmodel_id = aml.localmodel_id

            WHERE mh.device_id = ? AND mh.tag_id = ?
              AND mh.outlier_score_fn = 'local_outlier_factor'
              AND t.value != 'All'

            GROUP BY
                mh.device_id,
                mh.localmodel_id,
                mh.tag_id,
                t.value,
                mh.analytics_time

            ORDER BY datetime(mh.analytics_time) DESC
            LIMIT 10;
        """, (device_id, tag_id))

        rows = cur.fetchall()
        if not rows:
            return {"global_rmse": "No data available for this tag",
                    "outlier_score_value": "No data available for this tag"}
        rmse = {
            str(analytics_time): rmse
            for analytics_time, rmse, outlier_score_value in rows
        }
        
        outlier_score_value = {
            str(analytics_time): outlier_score_value
            for analytics_time, rmse, outlier_score_value in rows
        }

        result = {
                "global_rmse": rmse,
                "outlier_score_value": outlier_score_value
            }
        return result
    
    except sqlite3.Error:
        return {}

def get_seedmodel_diagnostics(conn, tag_id):
    """Get seed model diagnostics information for each tag"""
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                smd.analytics_time,
                AVG(smd.performance_score) AS performance_score

            FROM seedmodel_diagnostics smd

            WHERE smd.tag_id = ?

            GROUP BY
                smd.tag_id,
                smd.analytics_time

            ORDER BY
                smd.tag_value,
                datetime(smd.analytics_time)
        """, (tag_id,))

        rows = cur.fetchall()
        result = {
            str(analytics_time): performance_score
            for analytics_time, performance_score in rows
        }
        return result
    
    except sqlite3.Error:
        return {}
    
# Cross Tag Diagnostics
def get_cross_tag_context(conn, device_id):
    """Get outlier context information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT 
                    worst_perf_tag, worst_tag_performance, 
                    worst_outlier_tag, worst_tag_outlier, 
                    problem_pattern, outlier_ratio
                    FROM device_cross_tag_summary
                    WHERE device_id = {device_id};""")
        row = cur.fetchone()
        
        if not row:
            return {}
        
        return {
            "worst_performance_tag": row[0],
            #"worst_performance": row[1],
            "worst_outlier_tag": row[2],
            #"worst_outlier_score": row[3],
            "problem_pattern": row[4],
            "outlier_ratio": row[5]
  }
        
    except sqlite3.Error:
        return {}

# SCHEMA GENERATION 
def get_full_schema(conn, device_id, include_model_performance=True, 
                    include_feature_sensitivity=True):
    """Generate full schema based on selected checkboxes"""
    schema = {
    "Weather Station Information": get_device_information(conn, device_id)
    }
    if include_model_performance:
        schema["Model Performance Context"] = get_model_performance(conn, device_id)
        
    if include_feature_sensitivity:
        schema["Feature Importance"] = get_feature_sensitivity(conn, device_id)
    
    if include_feature_sensitivity and not include_model_performance:
        schema["Modelhealth Outlier History"] = get_modelhealth_outlier_history(conn, device_id)
        
    if include_model_performance:
        schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
        
    schema["Latest Cross Tag Context"] = get_cross_tag_context(conn, device_id)
    
    return schema

