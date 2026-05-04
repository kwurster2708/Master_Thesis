import sqlite3
from datetime import datetime
from pathlib import Path

PICTURE_BASE_DIR = Path(r"\Users\Kim_W\Ekkono_Code\pictures")

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

def get_country_state(conn, device_id):
    """Extract country and state from device tags"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT key, value
                    FROM tag
                    WHERE id IN (SELECT tag_id
                                FROM devicetaglink
                                WHERE device_id = {device_id})""")
        tags = {r[0]: r[1] for r in cur.fetchall()}
        country = tags.get('country')
        state = tags.get('state')
        return country, state
    except sqlite3.Error:
        return None, None

# --- Pictures --- #

def get_performance_pictures(device_id):
    return PICTURE_BASE_DIR/f"performance/d{device_id}_performance.png"

def get_feature_importance_pictures(device_id):
    return PICTURE_BASE_DIR/f"feature_importance/d{device_id}_feature_importance.png"

def get_pictures(device_id, include_performance=True, include_feature_importance=True):
    pictures = {}
    if include_performance:
        pictures["performance"] = str(get_performance_pictures(device_id))
    if include_feature_importance:
        pictures["feature_importance"] = str(get_feature_importance_pictures(device_id))
    return pictures

# --- 1. Weather Station Information --- #
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
                "tags": tags_dict,
                "weather_station_id": f"d{device_id}"
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}

def get_functioning_information(conn, device_id):
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

# --- 4. Tag Diagnostics --- #
def get_tag_diagnostics(conn, device_id):
    """Get performance context including current, rolling averages, and trends"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT tag_value, performance, outlier_score  
                    FROM device_tag_diagnostics WHERE device_id = {device_id}
                    ORDER BY performance DESC;""")
        rows = cur.fetchall()
        result = {}
        
        for r in rows: #every tag just once
            result[f"{r[0]}"] = {'error_score': r[1],
                               'outlier_score': r[2]
                               }
        return result
    
    except sqlite3.Error:
        return {}
    
# --- 5. Cross Tag Diagnostics --- #
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

# --- Get functioning stations (No Outliers) --- #
def get_functioning_stations(conn, country, state):
    cur = conn.cursor()
    
    # First attempt: match both country and state
    if state != "Not Applicable":
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN devicetaglink dtl_state ON d.id = dtl_state.device_id
            JOIN tag t_state ON dtl_state.tag_id = t_state.id AND t_state.key = 'state' AND t_state.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country, state))
        rows = cur.fetchall()
        
        # Fallback to country-only if no results
        if not rows:
            cur.execute(f"""
                SELECT DISTINCT d.id
                FROM device d
                JOIN devicetaglink dtl ON d.id = dtl.device_id
                JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
                JOIN device_outlier_classification doc ON d.id = doc.device_id
                WHERE doc.outlier_classification = 'No Outlier'
                ORDER BY d.id;
            """, (country,))
            rows = cur.fetchall()
    else:
        # No state tag: match country only
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country,))
        rows = cur.fetchall()
    
    functioning_stations = []
    for (device_id,) in rows:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "tag_diagnostics": get_tag_diagnostics(conn, device_id)
        }
        functioning_stations.append(station_schema)
    
    return functioning_stations

def get_functioning_stations_FI(conn, country, state):
    cur = conn.cursor()
    
    # First attempt: match both country and state
    if state != "Not Applicable":
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN devicetaglink dtl_state ON d.id = dtl_state.device_id
            JOIN tag t_state ON dtl_state.tag_id = t_state.id AND t_state.key = 'state' AND t_state.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country, state))
        rows = cur.fetchall()
        
        # Fallback to country-only if no results
        if not rows:
            cur.execute(f"""
                SELECT DISTINCT d.id
                FROM device d
                JOIN devicetaglink dtl ON d.id = dtl.device_id
                JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
                JOIN device_outlier_classification doc ON d.id = doc.device_id
                WHERE doc.outlier_classification = 'No Outlier'
                ORDER BY d.id;
            """, (country,))
            rows = cur.fetchall()
    else:
        # No state tag: match country only
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country,))
        rows = cur.fetchall()
    
    functioning_stations = []
    for (device_id,) in rows:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id)
        }
        functioning_stations.append(station_schema)
    
    return functioning_stations

def get_functioning_stations_P(conn, country, state):
    cur = conn.cursor()
    
    # First attempt: match both country and state
    if state != "Not Applicable":
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN devicetaglink dtl_state ON d.id = dtl_state.device_id
            JOIN tag t_state ON dtl_state.tag_id = t_state.id AND t_state.key = 'state' AND t_state.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country, state))
        rows = cur.fetchall()
        
        # Fallback to country-only if no results
        if not rows:
            cur.execute(f"""
                SELECT DISTINCT d.id
                FROM device d
                JOIN devicetaglink dtl ON d.id = dtl.device_id
                JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
                JOIN device_outlier_classification doc ON d.id = doc.device_id
                WHERE doc.outlier_classification = 'No Outlier'
                ORDER BY d.id;
            """, (country,))
            rows = cur.fetchall()
    else:
        # No state tag: match country only
        cur.execute(f"""
            SELECT DISTINCT d.id
            FROM device d
            JOIN devicetaglink dtl ON d.id = dtl.device_id
            JOIN tag t_country ON dtl.tag_id = t_country.id AND t_country.key = 'country' AND t_country.value = ?
            JOIN device_outlier_classification doc ON d.id = doc.device_id
            WHERE doc.outlier_classification = 'No Outlier'
            ORDER BY d.id;
        """, (country,))
        rows = cur.fetchall()
    
    functioning_stations = []
    for (device_id,) in rows:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "tag_diagnostics": get_tag_diagnostics(conn, device_id)
        }
        functioning_stations.append(station_schema)
    
    return functioning_stations

# --- SCHEMA GENERATION FUNCTION --- #
def get_full_schema(conn, device_id, include_model_performance=True, 
                    include_feature_sensitivity=True):
    """Generate full schema based on selected checkboxes"""
    country, state = get_country_state(conn, device_id)
    
    schema = {
    "Weather Station Information": get_device_information(conn, device_id)
    }

    if include_model_performance:
        schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
        
    schema["Cross Tag Context"] = get_cross_tag_context(conn, device_id)
    
    if include_feature_sensitivity and not include_model_performance:
        functioning_schema = get_functioning_stations_FI(conn, country, state)
        
    if include_model_performance and not include_feature_sensitivity:
        functioning_schema = get_functioning_stations_P(conn, country, state)
    
    if include_model_performance and include_feature_sensitivity:
        functioning_schema = get_functioning_stations(conn, country, state)
    
    full_schema = {
        "pictures": get_pictures(device_id, include_model_performance, include_feature_sensitivity),
        "to_be_evaluated_weather_station": schema,
        "functioning_weather_stations": functioning_schema
    } 
    
    return full_schema
