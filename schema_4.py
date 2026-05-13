import sqlite3
from datetime import datetime
from pathlib import Path
from math import exp

PICTURE_BASE_DIR = Path(r"\Users\Kim_W\Ekkono_Code\pictures")

def get_connection():
    return sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

#--- Helper functions to get all outlier devices ---#

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

def label_seedmodel(value):
    if value > 4:
        return "bad prediction in comparison with other seedmodels"
    if value > 2.49:
        return "moderate performance"
    return "good performance"

def merge_label_windows(sorted_items, label_fn):
    if not sorted_items:
        return []
    windows = []
    start_month = sorted_items[0][0]
    avg_value = sum(sorted_items[0][1]) / len(sorted_items[0][1])
    current_label = label_fn(avg_value)
    prev_month = start_month
    for month, scores in sorted_items[1:]:
        avg_value = sum(scores) / len(scores)
        label = label_fn(avg_value)
        if label == current_label:
            prev_month = month
        else:
            windows.append((start_month, prev_month, current_label))
            start_month = month
            prev_month = month
            current_label = label
    windows.append((start_month, prev_month, current_label))
    return windows

# --- Pictures --- #
def get_performance_pictures(device_id):
    return PICTURE_BASE_DIR/f"performance/d{device_id}_performance.png"

def get_feature_importance_pictures(device_id):
    return PICTURE_BASE_DIR/f"feature_importance/d{device_id}_feature_importance.png"

def get_tag_performance_pictures(device_id):
    return PICTURE_BASE_DIR/f"tag_performance/d{device_id}_tag_performance.png"

def get_tag_outliers_pictures(device_id):
    return PICTURE_BASE_DIR/f"tag_outliers/d{device_id}_outliers.png"

def get_pictures(device_id, include_performance=True, include_feature_importance=True):
    pictures = {}
    
    if include_performance:
        pictures["performance"] = str(get_performance_pictures(device_id))
        pictures["tag_performance"] = str(get_tag_performance_pictures(device_id))
    if include_feature_importance:
        pictures["feature_importance"] = str(get_feature_importance_pictures(device_id))

    pictures["tag_outliers"] = str(get_tag_outliers_pictures(device_id))
    
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
                                WHERE device_id = {device_id}) AND key NOT IN ('All', 'name', 'station_id');
                    """)
        tags_dict = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.execute(f"""SELECT outlier_classification 
                    FROM device_outlier_classification
                    WHERE device_id = {device_id}
                    """)
        classification = cur.fetchone()[0]
        
        cur = conn.cursor()

        cur.execute(f"""SELECT 
            CASE
                WHEN m.name = 'cde.mean' THEN m.value 
            END AS "concept_drift_mean"
                FROM metric m
                JOIN active_model_lookup aml ON m.localmodel_id = aml.localmodel_id
                WHERE aml.device_id = {device_id} AND m.name = 'cde.mean'""")
        row = cur.fetchone()
                
        return {
                "weather_station_classification": classification,
                "tags": tags_dict,
                "weather_station_id": f"d{device_id}",
                "concept_drift_mean": row[0] if row else None   
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
                                WHERE device_id = {device_id}) AND key NOT IN ('All', 'name', 'station_id');
                    """)
        tags_dict = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.execute(f"""SELECT outlier_classification 
                    FROM device_outlier_classification
                    WHERE device_id = {device_id}
                    """)
        classification = cur.fetchone()[0]
        
        cur.execute(f"""SELECT 
            CASE
                WHEN m.name = 'cde.mean' THEN m.value 
            END AS "concept_drift_mean"
                FROM metric m
                JOIN active_model_lookup aml ON m.localmodel_id = aml.localmodel_id
                WHERE aml.device_id = {device_id} AND m.name = 'cde.mean'""")
        row = cur.fetchone()
                
                
        return {
                "weather_station_classification": classification,
                "tags": tags_dict,
                "concept_drift_mean": row[0] if row else None
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}

# --- 4. Tag Diagnostics --- #
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
                result[row[1]] = {
                "latest_diagnostics": get_current_diagnostics(conn, device_id, row[0]),
                "seedmodel_performance_score": get_seedmodel_diagnostics(conn, row[0])
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
                #"analytics_time": str(row[0]),
                #"global_rmse": row[1],
                #"outlier_score_value": row[2],
                "outlier_score": row[3]
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
        monthly_scores = {}

        for analytics_time, performance_score in rows:
            dt = datetime.fromisoformat(str(analytics_time))
            month_key = dt.strftime("%Y_%B")
            
            if month_key not in monthly_scores:
                monthly_scores[month_key] = []
            monthly_scores[month_key].append(performance_score)
        
        sorted_months = sorted(monthly_scores.items())
        windows = merge_label_windows(sorted_months, label_seedmodel)
        performance_dict = {}
        for start_month, end_month, label in windows:
            if start_month == end_month:
                performance_dict[f"{start_month}"] = label
            else:
                performance_dict[f"{start_month} - {end_month}"] = label
        return performance_dict
    
    except sqlite3.Error:
        return {}
    
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
def find_best_reference_devices(conn, device_id):
    cur = conn.cursor()
    # Get evaluated devicetags (exclude 'All')
    cur.execute("""
        SELECT DISTINCT mh.tag_id, t.value
        FROM modelhealth mh
        JOIN tag t ON mh.tag_id = t.id
        WHERE mh.device_id = ?
          AND mh.outlier_score_fn = 'local_outlier_factor'
          AND t.value != 'All'
    """, (device_id,))
    device_tags = {row[0]: row[1] for row in cur.fetchall()}
    if not device_tags:
        return []
    
    cur.execute("""
        SELECT key, value FROM tag
        WHERE id IN (
            SELECT tag_id FROM devicetaglink WHERE device_id = ?
        ) AND key IN ('state', 'urbanization')
    """, (device_id,))
    meta = dict(cur.fetchall())
    exclude_state = meta.get('state') == 'Not Applicable'
    exclude_urbanization = meta.get('urbanization') == 'unknown'
    
    
    exclude_conditions = []
    if exclude_state:
        exclude_conditions.append("(t.key = 'state' AND t.value = 'Not Applicable')")
    if exclude_urbanization:
        exclude_conditions.append("(t.key = 'urbanization' AND t.value = 'unknown')")
    exclude_sql = ""
    if exclude_conditions:
        exclude_sql = f"""AND dtd.device_id NOT IN (
            SELECT dtl.device_id
            FROM devicetaglink dtl
            JOIN tag t ON dtl.tag_id = t.id
            WHERE {' OR '.join(exclude_conditions)}
        )"""
    
    tag_ids = list(device_tags.keys())
    placeholders = ','.join('?' * len(tag_ids))
    
    # Find models with >= 2 same tags and an active model
    params = tag_ids + [device_id]
    cur.execute(f"""
        SELECT dtd.device_id
        FROM device_tag_diagnostics dtd
        JOIN active_model_lookup aml ON dtd.device_id = aml.device_id
        WHERE dtd.tag_id IN ({placeholders})
            AND dtd.device_id != ?
            {exclude_sql}
        GROUP BY dtd.device_id
        HAVING COUNT(DISTINCT dtd.tag_id) >= 2
    """, params)
    candidate_ids = [row[0] for row in cur.fetchall()]
    if not candidate_ids:
        return []
    c_placeholders = ','.join('?' * len(candidate_ids))
    all_params = candidate_ids + tag_ids
    
    # Per-tag metrics for candidates
    cur.execute(f"""
        SELECT dtd.device_id, dtd.tag_id, dtd.global_rmse, dtd.outlier_score_value
        FROM device_tag_diagnostics dtd
        WHERE dtd.device_id IN ({c_placeholders})
          AND dtd.tag_id IN ({placeholders})
    """, all_params)
    tag_metrics = {}
    for dev_id, tag_id, g_rmse, os_val in cur.fetchall():
        tag_metrics.setdefault(dev_id, {})[tag_id] = {
            "global_rmse": g_rmse,
            "outlier_score_value": os_val
        }
    
    # Latest local RMSE per candidate
    cur.execute(f"""
        SELECT aml.device_id, mpm.local_rmse
        FROM active_model_lookup aml
        JOIN model_performance_metrics mpm ON aml.localmodel_id = mpm.localmodel_id
        WHERE aml.device_id IN ({c_placeholders})
          AND mpm.local_rmse IS NOT NULL
        ORDER BY mpm.update_time DESC
    """, candidate_ids)
    local_rmse_map = {}
    for dev_id, l_rmse in cur.fetchall():
        if dev_id not in local_rmse_map:
            local_rmse_map[dev_id] = l_rmse

    # Concept drift per candidate
    cur.execute(f"""
        SELECT aml.device_id, m.value
        FROM active_model_lookup aml
        JOIN metric m ON aml.localmodel_id = m.localmodel_id
        WHERE aml.device_id IN ({c_placeholders})
          AND m.name = 'cde.mean'
    """, candidate_ids)
    cd_map = {row[0]: row[1] for row in cur.fetchall()}
    
    # For each tag, collect candidate data and score
    best_devices = set()
    for tag_id in tag_ids:
        tag_candidates = []
        for cid in candidate_ids:
            tm = tag_metrics.get(cid, {}).get(tag_id)
            if not tm or tm["global_rmse"] is None:
                continue
            lr = local_rmse_map.get(cid)
            cd = cd_map.get(cid)
            if lr is None or cd is None:
                continue
            tag_candidates.append({
                "device_id": cid,
                "rmse_l": lr,
                "rmse_g": tm["global_rmse"],
                "outlier_score": tm["outlier_score_value"],
                "concept_drift": cd
            })
        if not tag_candidates:
            continue
        # Normalize rmse_l, rmse_g, cd to [0, 1]
        for key in ("rmse_l", "rmse_g", "concept_drift"):
            vals = [c[key] for c in tag_candidates]
            mn, mx = min(vals), max(vals)
            if mx == mn:
                for c in tag_candidates:
                    c[f"{key}_norm"] = 0.5
            else:
                for c in tag_candidates:
                    c[f"{key}_norm"] = (c[key] - mn) / (mx - mn)
        
        # Compute WMS for each candidate
        for c in tag_candidates:
            os = c["outlier_score"]
            exp_term = min(-(os + 1), 1.5)
            c["wms"] = (exp(exp_term) *
                        (0.5 * c["rmse_l_norm"] +
                         0.4 * c["rmse_g_norm"] +
                         0.1 * c["concept_drift_norm"]))
        
        # Pick best: prefer outlier_score > -1.5, fallback to all
        eligible = [c for c in tag_candidates if c["outlier_score"] > -1.5]
        pool = eligible if eligible else tag_candidates
        best = min(pool, key=lambda c: c["wms"])
        best_devices.add(best["device_id"])
    return list(best_devices)

def get_functioning_stations(conn, best_ids):
    functioning_stations = {}
    for device_id in best_ids:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "tag_diagnostics": get_tag_diagnostics(conn, device_id)
            
        }
        functioning_stations[device_id] = station_schema
    
    return functioning_stations

def get_functioning_stations_FI(conn, best_ids):
    functioning_stations = {}
    for device_id in best_ids:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id)
        }
        functioning_stations[device_id] = station_schema
    
    return functioning_stations

def get_functioning_stations_P(conn, best_ids):  
    functioning_stations = {}
    for device_id in best_ids:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "tag_diagnostics": get_tag_diagnostics(conn, device_id)
        }
        functioning_stations[device_id] = station_schema
    
    return functioning_stations

# --- SCHEMA GENERATION FUNCTION --- #
def get_full_schema(conn, device_id, include_model_performance=True, 
                    include_feature_sensitivity=True):
    
    schema = {
    "Weather Station Information": get_device_information(conn, device_id)
    }

    if include_model_performance:
        schema["Tag Diagnostics"] = get_tag_diagnostics(conn, device_id)
        
    schema["Latest Cross Tag Context"] = get_cross_tag_context(conn, device_id)
    
    best_ids = find_best_reference_devices(conn, device_id)
    
    if include_feature_sensitivity and not include_model_performance:
        functioning_schema = get_functioning_stations_FI(conn, best_ids)
        
    if include_model_performance and not include_feature_sensitivity:
        functioning_schema = get_functioning_stations_P(conn, best_ids)
    
    if include_model_performance and include_feature_sensitivity:
        functioning_schema = get_functioning_stations(conn, best_ids)
    
    full_schema = {
        "pictures": get_pictures(device_id, include_model_performance, include_feature_sensitivity),
        "inspected_weather_station": schema,
        "reference_weather_stations": functioning_schema
    } 
    
    return full_schema
