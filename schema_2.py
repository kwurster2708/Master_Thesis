import sqlite3
from datetime import datetime

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

#--- Helper functions to get all outlier devices ---#
"""Giving the devices/first models lables according to the outliers

Underperforming (49): Skill score below 1.0 - performing worse than predicting the mean 
Low Accuracy (84): Skill score above 1.0 but high RMSE values 
Partial Outlier (25): Are outliers for some tags but not all
Full Outlier (1): Good RMSE but highly different from other models 
No Outlier: Does not belong to any of the above categories based on the outlier score value

Outlier based on the active model for the device.
"""

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
    

# --- FUNCTIONS TO CREATE SCHEMA ---#

# --- 1. Device Information --- #
def get_device_information(conn, device_id):
    """Get diagnostic event information"""
    cur = conn.cursor()
    
    try:
        cur.execute(f"""SELECT key, value
                    FROM tag
                    WHERE id IN (SELECT tag_id
                                FROM devicetaglink
                                WHERE device_id = {device_id}) AND key <> 'All';
                    """)
        tags_dict = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.execute(f"""SELECT outlier_classification 
                    FROM device_outlier_classification
                    WHERE device_id = {device_id}
                    """)
        classification = cur.fetchone()[0]
                
        return {
                "weather_station_classification": classification,
                "tags": tags_dict
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}
   
# --- 3.1 Active Model Performance Context --- #
def get_model_performance(conn, device_id):
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT mpp.performance_score, mpp.analytics_time
                    FROM active_model_lookup aml
                    JOIN model_performance_pivot mpp
                    ON aml.localmodel_id = mpp.localmodel_id
                    WHERE aml.device_id = {device_id};""")
        rows = cur.fetchall()
        performance_dict = {
            f"{analytics_time}": performance_score
            for performance_score, analytics_time in rows
        }
        
        cur.execute(f"""SELECT mpt.trend
                    FROM active_model_lookup aml
                    JOIN model_performance_trend mpt
                    ON aml.localmodel_id = mpt.localmodel_id
                    WHERE aml.device_id = {device_id};""")
        row = cur.fetchone()
        
        if row:
            return {
                "model_performance_trend": row[0],
                "performance": performance_dict
            }
    
    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")

# --- 3.2 Model Version History --- #
def get_model_version_history(conn, device_id):
    """Get model version history information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT avg_past, trend, recent
                    FROM version_history_performance
                    WHERE device_id = {device_id};""")
        
        row = cur.fetchone()
        
        return {
           "trend": row[1],
           "active_model_error_score": row[2],
           "historical_models_error_score": row[0]
        }
        
    except sqlite3.Error:
        print(f"Error executing model version history query for Device ID {device_id}")
        return []

# --- 4. Feature Sensitivity Context --- #
def get_feature_sensitivity(conn, device_id):
    """Get feature sensitivity information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT fst.top_feature_1, fst.importance_1, 
                    fst.top_feature_2, fst.importance_2,
                    fst.top_feature_3, fst.importance_3
                    FROM active_model_lookup aml
                    JOIN feature_sensitivity_top3 fst ON
                    aml.modelbinary_id = fst.modelbinary_id
                    WHERE aml.device_id = {device_id}""")
        row = cur.fetchone()
        
        top_features = []
        
        if row:
            for i in range(3):
                if row[i*2+1]: top_features.append({row[i*2]: row[i*2+1]})
        
        cur.execute(f"""SELECT hist_top_1, hist_sens_1, 
                    hist_top_2, hist_sens_2, 
                    hist_top_3, hist_sens_3
                    FROM feature_sensitivity_historical
                    WHERE device_id = {device_id}""")
        row = cur.fetchone()
        
        hist_features = []
        if row:
            for i in range(3):
                if row[i*2+1]: hist_features.append({row[i*2]: row[i*2+1]})
        
        top3 = {k: v for d in top_features for k, v in d.items()}
        hist3 = {k: v for d in hist_features for k, v in d.items()}
        
        return {
            "top_3_features_active_model": top3,
            "top_3_features_average_historical_models": hist3
        }
    except sqlite3.Error:
        return {}

# --- 5. Tag Diagnostics --- #
def get_tag_diagnostics(conn, device_id):
    """Get performance context including current, rolling averages, and trends"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT tag_value, performance, 
                    outlier_score_value, outlier_score, analytics_time  
                    FROM device_tag_diagnostics WHERE device_id = {device_id}
                    ORDER BY performance DESC;""")
        rows = cur.fetchall()
        result = {}
        
        #just put out one tag per bllablb
        
        for r in rows: #every tag just once
            result[f"{r[0]}"] = {'error_score': r[1],
                               #'outlier_score_value': r[2],
                               'outlier_score': r[3],
                               #'analytics_time': r[4]
                               }
        
        #result['Worst Tag'] = {rows[0][0]}
        return result
    
    except sqlite3.Error:
        return {}
    
# --- 6. Cross Tag Diagnostics --- #
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

# --- SCHEMA GENERATION FUNCTION --- #
def get_full_schema(conn, device_id, include_model_performance=True, 
                    include_feature_sensitivity=True):
    """Generate full schema based on selected checkboxes"""
    schema = {
    
    "Weather Station Information": get_device_information(conn, device_id),
    
    #"Active Model Context": get_model_context(conn, device_id),
    
    }
    if include_model_performance:
        schema["Model Performance Context"] = get_model_performance(conn, device_id)
        schema["Model Version History"] = get_model_version_history(conn, device_id)
    
    if include_feature_sensitivity:
        schema["Feature Importance"] = get_feature_sensitivity(conn, device_id)
    
    if include_model_performance:
        schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
        
    schema["Cross Tag Context"] = get_cross_tag_context(conn, device_id)
    
    return schema
