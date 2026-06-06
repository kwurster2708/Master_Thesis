"""
Preparing the data for PowerBI visualizations by extracting relevant tables from the SQLite database, 
performing necessary transformations, and exporting them as Parquet files for efficient loading into PowerBI. 
"""

import sqlite3
import pandas as pd
import os
from math import exp

conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# Path setup
output_dir = "parquet_output"
os.makedirs(output_dir, exist_ok=True)

def to_sql_in(values):
    return ",".join(str(v) for v in values)

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

devices = [131, 393, 1456, 3235] # Just using devices actually used in thesis to reduce runtime

device_dict = {}
device_list = set(devices)
for dev in devices:
    best_refs = find_best_reference_devices(conn, dev)
    device_dict[dev] = best_refs
    device_list.update(best_refs)

device_list = sorted(device_list)
device_list_sql = to_sql_in(device_list)
devices_sql = to_sql_in(devices)

# Device classification
device_classification = pd.read_sql(f"""
SELECT DISTINCT device_id, outlier_classification
FROM device_outlier_classification
WHERE device_id IN ({devices_sql})
ORDER BY device_id
""", conn)

device_classification.to_parquet(f"{output_dir}/device_classification.parquet", index=False)
print("✅ Classification table exported to Parquet!")

# Tags
tags = pd.read_sql(f"""
SELECT DISTINCT dtl.device_id, t.key, t.value
FROM devicetaglink dtl
JOIN tag t ON t.id = dtl.tag_id
WHERE t.key <> 'All' AND dtl.device_id IN ({devices_sql})
""", conn)

tags.to_parquet(f"{output_dir}/tags.parquet", index=False)
print("✅ Tags table exported to Parquet!")

# Model Health
modelhealth = pd.read_sql(f"""
SELECT
        mh.device_id,
        t.key AS tag_key,
        t.value AS tag_value,
        mh.analytics_time,
        mh.rmse,
        mh.outlier_score_value
    FROM modelhealth mh
    JOIN tag t ON mh.tag_id = t.id
    JOIN active_model_lookup aml
        ON mh.localmodel_id = aml.localmodel_id
    WHERE mh.device_id IN ({devices_sql})
      AND t.value != 'All'
    ORDER BY mh.device_id, t.value, mh.analytics_time ASC
""", conn)

modelhealth.to_parquet(f"{output_dir}/modelhealth.parquet", index=False)
print("✅ Model Health table exported to Parquet!")

# Local RMSE Comparison
local_frames = []
for inspected_device, related_devices in device_dict.items():
    comparison_devices = sorted(set([inspected_device] + related_devices))
    comparison_sql = to_sql_in(comparison_devices)

    local_rmse = pd.read_sql(f"""
        SELECT
            {inspected_device} AS inspected_device_id,
            aml.device_id AS comparison_device_id,
            CASE 
                WHEN aml.device_id = {inspected_device} THEN 'Inspected Weather Station' 
                ELSE 'Reference Weather Stations' 
            END AS device_type,
            mpm.update_time,
            mpm.local_rmse
        FROM active_model_lookup aml
        JOIN model_performance_metrics mpm
            ON aml.localmodel_id = mpm.localmodel_id
        WHERE aml.device_id IN ({comparison_sql})
          AND mpm.local_rmse IS NOT NULL
        ORDER BY mpm.update_time ASC, aml.device_id ASC
    """, conn)
    local_frames.append(local_rmse)
if local_frames:
    local_rmse_comparison = pd.concat(local_frames, ignore_index=True)
    local_rmse_comparison.to_parquet(f"{output_dir}/local_rmse_comparison.parquet", index=False)
    print("✅ Local RMSE Comparison table exported to Parquet!")

# Global RMSE Comparison
global_frames = []
for inspected_device, related_devices in device_dict.items():
    comparison_devices = sorted(set([inspected_device] + related_devices))
    comparison_sql = to_sql_in(comparison_devices)

    global_rmse = pd.read_sql(f"""
        SELECT
            {inspected_device} AS inspected_device_id,
            aml.device_id AS comparison_device_id,
            CASE
                WHEN aml.device_id = {inspected_device} THEN 'Inspected Weather Station'
                ELSE 'Reference Weather Stations'
            END AS device_type,
            mpp.analytics_time,
            mpp.global_rmse
        FROM active_model_lookup aml
        JOIN model_performance_pivot mpp
            ON aml.localmodel_id = mpp.localmodel_id
        WHERE aml.device_id IN ({comparison_sql})
          AND mpp.global_rmse IS NOT NULL
        ORDER BY mpp.analytics_time ASC, aml.device_id ASC
    """, conn)

    global_frames.append(global_rmse)
if global_frames:
    global_rmse_comparison = pd.concat(global_frames, ignore_index=True)

global_rmse_comparison.to_parquet(f"{output_dir}/global_rmse_comparison.parquet", index=False)
print("✅ Global RMSE Comparison table exported to Parquet!")

# Feature Importance
feature_frames = []

for inspected_device, related_devices in device_dict.items():
    if not related_devices:
        continue
    
    related_sql = to_sql_in(related_devices)

    sensitivity_analysis = pd.read_sql(f"""
    WITH active_models AS (
        SELECT device_id, modelbinary_id
        FROM active_model_lookup
        WHERE device_id IN ({inspected_device}, {related_sql})
    ),

    expanded_sensitivity AS (
        SELECT
            am.device_id,
            je.key AS attribute,
            je.value AS sensitivity
        FROM attributesensitivities ats
        JOIN modelbinary mb ON ats.id = mb.attribute_sensitivities_id
        JOIN active_models am ON am.modelbinary_id = mb.id
        JOIN json_each(ats.attribute_sensitivities) je
    ),

    active_sensitivity AS (
        SELECT 
            device_id,
            attribute,
            sensitivity
        FROM expanded_sensitivity es
        WHERE device_id = {inspected_device}
    ),

    related_sensitivity AS (
        SELECT
            attribute,
            AVG(sensitivity) AS avg_related_sensitivity
        FROM expanded_sensitivity
        WHERE device_id IN ({related_sql})
        GROUP BY attribute
    )

    SELECT
        {inspected_device} AS inspected_device_id,
        a.attribute,
        a.sensitivity AS inspected_device_sensitivity,
        r.avg_related_sensitivity
    FROM active_sensitivity a
    LEFT JOIN related_sensitivity r
        ON a.attribute = r.attribute
    ORDER BY a.attribute
    """, conn)

    feature_frames.append(sensitivity_analysis)

feature_importance_comparison = pd.concat(feature_frames, ignore_index=True)

feature_importance_comparison.to_parquet(f"{output_dir}/feature_importance.parquet", index=False)
print("✅ Feature Importance table exported to Parquet!")

# Device Tag Diagnostics
diagnostics = pd.read_sql(f"""
SELECT device_id, tag_value, global_rmse, outlier_score_value, outlier_score
FROM device_tag_diagnostics
WHERE device_id IN ({devices_sql})
""", conn)

diagnostics.to_parquet(f"{output_dir}/device_tag_diagnostics.parquet", index=False)
print("✅ Device Tag Diagnostics table exported to Parquet!")

# Device Cross Tag Summaries
cross_tag = pd.read_sql(f"""
SELECT device_id, problem_pattern, outlier_ratio
FROM device_cross_tag_summary
WHERE device_id IN ({devices_sql})
""", conn)

cross_tag.to_parquet(f"{output_dir}/device_cross_tag_summary.parquet", index=False)
print("✅ Device Cross Tag Summaries table exported to Parquet!")

conn.close()

print("✅ All tables exported to Parquet!")