import sqlite3
import json
from datetime import datetime
#save
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
    try:
        cur.execute("""SELECT DISTINCT device_id 
                    FROM modelhealth 
                    WHERE outlier_score_value < -10
                    ORDER BY device_id, localmodel_id;""")
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
                                WHERE device_id = {device_id});
                    """)
        tags_dict = {r[0]: r[1] for r in cur.fetchall()}
                
        return {
                "tags": tags_dict,
                "target": "Temperature" #There is just one target in the dataset, so no need to query it
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}

# --- 2. Active Model Context --- #       
def get_model_context(conn, device_id):
    """Get model context information"""
    cur = conn.cursor()
    
    try:
        cur.execute(f"""SELECT aml.version_number, aml.last_train_time, 
                    aml.is_valid, aml.is_compatible, 
                    (SELECT MAX(create_time) FROM metric 
                    WHERE localmodel_id = aml.localmodel_id) as last_checked_time
                    FROM active_model_lookup aml
                    WHERE aml.device_id = {device_id};""")
        
        row = cur.fetchone()
        
        if row:
            model_age_days = None
            training_recency_bucket = None
            
            if row[4] and row[1]:
                try:
                    analytics_dt = datetime.strptime(str(row[4]), "%Y-%m-%d %H:%M:%S")
                    train_dt = datetime.strptime(str(row[1]), "%Y-%m-%d %H:%M:%S")
                    model_age_days = (analytics_dt - train_dt).days
                    
                    if model_age_days < 7:
                        training_recency_bucket = "fresh"
                    elif model_age_days < 30:
                        training_recency_bucket = "recent"
                    elif model_age_days < 90:
                        training_recency_bucket = "stale"
                    else:
                        training_recency_bucket = "outdated"
                except:
                    pass
            
            return {
                "version": row[0],
                "is_valid": row[2],
                "is_compatible": row[3],
                "model_age_days": model_age_days,
                "training_recency_bucket": training_recency_bucket
            }
    except sqlite3.Error:
        print(f"Error executing model context query for Device ID {device_id}")
        return {}
   
# --- 3.1 Active Model Performance Context --- #
def get_model_performance(conn, device_id):
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT mpp.mae, mpp.rmse, mpp.mape, mpp.overall_error_score, 
                    mpt.trend, mpt.worst_timestamp, mpt.worst_score
                    FROM active_model_lookup aml
                    JOIN model_performance_pivot mpp
                    ON aml.localmodel_id = mpp.localmodel_id
                    LEFT JOIN model_performance_trend mpt
                    ON aml.localmodel_id = mpt.localmodel_id
                    WHERE aml.device_id = {device_id};""")
        
        row = cur.fetchone()
        
        if row:
            return {
                "average metrics": {
                    "MAE": row[0],
                    "RMSE": row[1],
                    "MAPE": row[2]},
                "overall_error_score": row[3],
                "trend": row[4],
                "worst_performance_error_score": row[6], 
                "worst_time_stamp": row[5] 
            }
    
    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")

# --- 3.2 Model Version History --- #
def get_model_version_history(conn, device_id):
    """Get model version history information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT available_versions, avg_mae, avg_mape, avg_rmse
                    FROM version_history_performance
                    WHERE device_id = {device_id};""")
        
        row = cur.fetchone()
        
        return {
           "versions_available": row[0],
           "performance_trend": { 
               "MAE": row[1],
               "MAPE": row[2],
               "RMSE": row[3]
           }
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
                    fst.top_feature_2, fst.importance_2
                    fst.top_feature_3, fst.importance_3
                    FROM active_model_lookup aml
                    JOIN feature_sensitivity_top3 ON
                    aml.modelbinary_id = fst.modelbinary_id
                    WHERE aml.device_id = {device_id}""")
        row = cur.fetchone()
        
        top_features = []
        
        if row:
            for i in range(3):
                if row[i*2]: top_features.append({row[i*2]: row[i*2+1]})
        
        cur.execute(f"""SELECT fsh.hist_top_1, fsh.hist_sens_1, 
                    fsh.hist_top_2, fsh.hist_sens_2, 
                    fsh.hist_top_3, fsh.hist_sens_3
                    FROM feature_sensitivity_historical fsh
                    WHERE fsh.device_id = {device_id}""")
        row = cur.fetchone()
        hist3 = []
        if row:
            for i in range(3):
                if row[i*2]: hist3.append({row[i*2]: row[i*2+1]})
        
        return {
            "top_3_features": top_features,
            "historical_model_contribution": hist3
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
            result[f"{r[0]}"] = {'performance': r[1],
                               'outlier_score_value': r[2],
                               'outlier_score': r[3],
                               'analytics_time': r[4]
                               }
        
        result['Worst Tag'] = {rows[0][0]}
        return result
    
    except sqlite3.Error:
        return {}
    
# --- 6. Cross Tag Diagnostics --- #
def get_cross_tag_context(conn, device_id):
    """Get outlier context information"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT worst_tag_performance, average_tag_performance, worst_tag_outlier,
                    average_tag_outlier, problem_pattern, 
                    worst_perf_tag, worst_outlier_tag, extreme_ratio
                    FROM device_cross_tag_summary
                    WHERE device_id = {device_id};""")
        row = cur.fetchone()
        
        if not row:
            return {}
        
        return {
            "worst_performance_tag": row[5],
            "worst_performance": row[0],
            "average_performance": row[1],
            "worst_outlier_tag": row[6],
            #"worst_outlier_score": row[2],
            #"average_outlier_score": row[3],
            "problem_pattern": row[4],
            "extreme_outlier_ratio": row[7]
  }
        
    except sqlite3.Error:
        return {}

# --- SCHEMA GENERATION FUNCTION --- #
def get_full_schema(conn, device_id, include_model_performance=True, 
                    include_feature_sensitivity=True):
    """Generate full schema based on selected checkboxes"""
    schema = {
    
    "Device Information": get_device_information(conn, device_id),
    
    "Active Model Context": get_model_context(conn, device_id),
    
    }
    if include_model_performance:
        schema["Model Performance Context"] = get_model_performance(conn, device_id)
        schema["Model Version History"] = get_model_version_history(conn, device_id)
    
    if include_feature_sensitivity:
        schema["Feature Sensitivity"] = get_feature_sensitivity(conn, device_id)
    
    schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
    
    schema["Cross Tag Context"] = get_cross_tag_context(conn, device_id)
    
    return schema



#--- Test Space ---#
conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")
device = 2732

schema = get_full_schema(conn, device)
print(json.dumps(schema, indent=2, default=str))