import sqlite3
from datetime import datetime
from pathlib import Path
from math import exp

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

def _label_rmse(value):
    if value > 15:
        return "extreme rmse error (more than 15)"
    if value > 11.20:
        return "high rmse error (between 11.20 and 15)"
    if value > 10:
        return "moderate rmse error (between 10 and 11.20)"
    return "low rmse error (less than 10)"

def _label_outlier_score(value):
    if value < -5:
        return "extreme outlier score"
    if value < -3.5:
        return "strong outlier score"
    if value < -2:
        return "moderate outlier score"
    return "no outlier"

def _label_seedmodel(value):
    if value > 4:
        return "bad prediction in comparison with other seedmodels"
    if value > 2.49:
        return "moderate performance"
    return "good performance"

def _merge_label_windows(sorted_items, label_fn):
    if not sorted_items:
        return []
    
    windows = []
    
    start_month, start_data = sorted_items[0]
    start_label = start_data["label"]
    prev_label = start_label
    
    avg_value = sum(start_data["scores"]) / len(start_data["scores"])
    current_label = label_fn(avg_value)
    
    for month, data in sorted_items[1:]:
        month_label = data["label"]
        scores = data["scores"]
        
        avg_value = sum(scores) / len(scores)
        label = label_fn(avg_value)
        
        if label == current_label:
            prev_label = month_label
        else:
            windows.append((start_label, prev_label, current_label))
            
            start_label = month_label
            prev_label = month_label
            current_label = label
    windows.append((start_label, prev_label, current_label))
    return windows

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
                "tags": tags_dict
            }
    except sqlite3.Error:
        print(f"Error executing diagnostic event query for Device ID {device_id}")
        return {}

# --- 2. Model Performance Context --- #
def get_global_rmse(conn, device_id):
    """Get global RMSE value"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT mpp.global_rmse, mpp.analytics_time
                    FROM active_model_lookup aml
                    JOIN model_performance_pivot mpp
                    ON aml.localmodel_id = mpp.localmodel_id
                    WHERE aml.device_id = {device_id}
                    ORDER BY datetime(mpp.analytics_time) DESC;""")
        rows = cur.fetchall()
        monthly_scores = {}

        for global_rmse, analytics_time in rows:
            dt = datetime.fromisoformat(str(analytics_time))
            month_key = dt.strftime("%Y_%m")
            month_label = dt.strftime("%Y_%B")
            
            if month_key not in monthly_scores:
                monthly_scores[month_key] = {"scores": [], "label": month_label}
            monthly_scores[month_key]["scores"].append(float(global_rmse))
        
        sorted_months = sorted(monthly_scores.items())
        windows = _merge_label_windows(sorted_months, _label_rmse)
        performance_dict = {}
        for start_month, end_month, label in windows:
            if start_month == end_month:
                performance_dict[f"{start_month}"] = label
            else:
                performance_dict[f"{start_month} - {end_month}"] = label
        
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
                    ORDER BY datetime(mpm.update_time) DESC;""")
        rows = cur.fetchall()
        
        monthly_scores = {}

        for local_rmse, update_time in rows:
            dt = datetime.fromisoformat(str(update_time))
            month_key = dt.strftime("%Y_%m")
            month_label = dt.strftime("%Y_%B")
            
            if month_key not in monthly_scores:
                monthly_scores[month_key] = {"scores": [], "label": month_label}
            monthly_scores[month_key]["scores"].append(float(local_rmse))

        sorted_months = sorted(monthly_scores.items())
        windows = _merge_label_windows(sorted_months, _label_rmse)
        performance_dict = {}
        for start_month, end_month, label in windows:
            if start_month == end_month:
                performance_dict[f"{start_month}"] = label
            else:
                performance_dict[f"{start_month} - {end_month}"] = label
        
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

# --- 3. Feature Importance --- #
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
        
        top_features = {
            "Top Feature 1": row[0],
            "Top Feature 2": row[2],
            "Top Feature 3": row[4],
            "Top Feature 4": row[6],
            "Top Feature 5": row[8]
        }
        return top_features
    
    except sqlite3.Error:
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
        rmse = _label_rmse(row[1]) if row[1] is not None else "No RMSE data"
        
        result ={
                #"analytics_time": str(row[0]),
                "global_rmse": rmse,
                #"outlier_score_value": row[2],
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

            ORDER BY datetime(mh.analytics_time) DESC;
        """, (device_id, tag_id))
        rows = cur.fetchall()
        if not rows:
            return {"global_rmse": "No data available for this tag",
                    "outlier_score_value": "No data available for this tag"}
        monthly_rmse = {}
        monthly_os = {}
        
        for analytics_time, rmse, outlier_score_value in rows:
            dt = datetime.fromisoformat(str(analytics_time))
            month_key = dt.strftime("%Y_%m")
            month_label = dt.strftime("%Y_%B")
            
            
            if month_key not in monthly_rmse:
                monthly_rmse[month_key] = {"scores": [], "label": month_label}
            if month_key not in monthly_os:
                monthly_os[month_key] = {"scores": [], "label": month_label}
            monthly_rmse[month_key]["scores"].append(float(rmse))
            monthly_os[month_key]["scores"].append(float(outlier_score_value))

        def build_label_dict(monthly_data, label_fn):
            sorted_items = sorted(monthly_data.items())
            result = {}
            windows = _merge_label_windows(sorted_items, label_fn)
            for start_month, end_month, label in windows:
                if start_month == end_month:
                    result[start_month] = label
                else:
                    result[f"{start_month} - {end_month}"] = label
            return result
        
        rmse_dict = build_label_dict(monthly_rmse, _label_rmse)
        os_dict = build_label_dict(monthly_os, _label_outlier_score)
        if not rmse_dict and not os_dict:
            return {}
        return {
            "global_rmse": rmse_dict,
            "outlier_score_value": os_dict
        }
    
    except sqlite3.Error:
        return {}

def get_seedmodel_diagnostics(conn, tag_id):
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
            month_key = dt.strftime("%Y_%m")
            month_label = dt.strftime("%Y_%B")
            
            if month_key not in monthly_scores:
                monthly_scores[month_key] = {"scores": [], "label": month_label}
            monthly_scores[month_key]["scores"].append(float(performance_score))
        
        sorted_months = sorted(monthly_scores.items())
        windows = _merge_label_windows(sorted_months, _label_seedmodel)
        performance_dict = {}
        for start_month, end_month, label in windows:
            if start_month == end_month:
                performance_dict[f"{start_month}"] = label
            else:
                performance_dict[f"{start_month} - {end_month}"] = label
        return performance_dict
    
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
            "model_performance_context": get_model_performance(conn, device_id),
            "feature_importance": get_feature_sensitivity(conn, device_id),
            "tag_diagnostics": get_tag_diagnostics(conn, device_id)
        }
        functioning_stations[device_id] = station_schema
    
    return functioning_stations

def get_functioning_stations_FI(conn, best_ids):
    functioning_stations = {}
    for device_id in best_ids:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "feature_importance": get_feature_sensitivity(conn, device_id),
            "Modelhealth Outlier History": get_modelhealth_outlier_history(conn, device_id)
        }
        functioning_stations[device_id] = station_schema
    
    return functioning_stations

def get_functioning_stations_P(conn, best_ids):
    functioning_stations = {}
    for device_id in best_ids:
        station_schema = {
            "weather_station_information": get_functioning_information(conn, device_id),
            "model_performance_context": get_model_performance(conn, device_id),
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
        schema["Model Performance Context"] = get_model_performance(conn, device_id)
        
    if include_feature_sensitivity:
        schema["Feature Importance"] = get_feature_sensitivity(conn, device_id)
        
    if include_feature_sensitivity and not include_model_performance:
        schema["Modelhealth Outlier History"] = get_modelhealth_outlier_history(conn, device_id)
    
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
        "inspected_weather_station": schema,
        "reference_weather_stations": functioning_schema
    } 
    
    return full_schema
