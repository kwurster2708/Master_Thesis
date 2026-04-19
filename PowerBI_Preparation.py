import sqlite3
import pandas as pd
import os

conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# Path setup
output_dir = "parquet_output"
os.makedirs(output_dir, exist_ok=True)

def to_sql_in(values):
    return ",".join(str(v) for v in values)

def get_related_models(conn, device_ids):
    cur = conn.cursor()
    result = {}
    device_list = set()

    for device_id in device_ids:
        device_list.add(device_id)
        
        try:
            # Get country and state for the active device
            cur.execute("""
                SELECT t.key, t.value
                FROM tag t
                JOIN devicetaglink dtl ON t.id = dtl.tag_id
                WHERE dtl.device_id = ?
                  AND t.key IN ('country', 'state')
            """, (device_id,))
            tags = dict(cur.fetchall())

            country = tags.get("country")
            state = tags.get("state")

            if not country:
                result[device_id] = []
                continue

            # Try country + state first if state is available
            rows = []
            if state and state != "Not Applicable":
                cur.execute("""
                    SELECT DISTINCT d.id
                    FROM device d
                    JOIN devicetaglink dtl_country ON d.id = dtl_country.device_id
                    JOIN tag t_country
                        ON dtl_country.tag_id = t_country.id
                    JOIN devicetaglink dtl_state ON d.id = dtl_state.device_id
                    JOIN tag t_state
                        ON dtl_state.tag_id = t_state.id
                    JOIN device_outlier_classification doc
                        ON d.id = doc.device_id
                    WHERE t_country.key = 'country'
                      AND t_country.value = ?
                      AND t_state.key = 'state'
                      AND t_state.value = ?
                      AND doc.outlier_classification = 'No Outlier'
                    ORDER BY d.id
                """, (country, state))
                rows = cur.fetchall()

            # Fallback to country only
            if not rows:
                cur.execute("""
                    SELECT DISTINCT d.id
                    FROM device d
                    JOIN devicetaglink dtl_country ON d.id = dtl_country.device_id
                    JOIN tag t_country
                        ON dtl_country.tag_id = t_country.id
                    JOIN device_outlier_classification doc
                        ON d.id = doc.device_id
                    WHERE t_country.key = 'country'
                      AND t_country.value = ?
                      AND doc.outlier_classification = 'No Outlier'
                    ORDER BY d.id
                """, (country,))
                rows = cur.fetchall()

            result[device_id] = [row[0] for row in rows if row[0] != device_id]
            device_list.update([row[0] for row in rows if row[0] != device_id])

        except sqlite3.Error:
            result[device_id] = []

    device_list = sorted(list(device_list))
    return result, device_list

devices = [88, 131, 1383, 1456]
device_dict, device_list = get_related_models(conn, devices)

device_list_sql = to_sql_in(device_list)
devices_sql = to_sql_in(devices)

# -----------------------
# 1. Device Classification
# -----------------------
device_classification = pd.read_sql(f"""
SELECT DISTINCT device_id, outlier_classification
FROM device_outlier_classification
WHERE device_id IN ({devices_sql})
ORDER BY device_id
""", conn)

device_classification.to_parquet(f"{output_dir}/device_classification.parquet", index=False)
print("✅ Classification table exported to Parquet!")

# -----------------------
# 2. Tags 
# -----------------------
tags = pd.read_sql(f"""
SELECT DISTINCT dtl.device_id, t.key, t.value
FROM devicetaglink dtl
JOIN tag t ON t.id = dtl.tag_id
WHERE t.key <> 'All' AND dtl.device_id IN ({device_list_sql})
""", conn)

tags.to_parquet(f"{output_dir}/tags.parquet", index=False)
print("✅ Tags table exported to Parquet!")

# -----------------------
# 3. Model Health
# -----------------------
modelhealth = pd.read_sql(f"""
SELECT mh.device_id,
       mh.analytics_time,
       mh.rmse AS performance_score
FROM modelhealth mh
JOIN active_model_lookup aml 
    ON mh.localmodel_id = aml.localmodel_id
WHERE mh.device_id IN ({device_list_sql})
AND EXISTS (
    SELECT 1
    FROM devicetaglink dtl
    JOIN tag t on t.id = dtl.tag_id
    WHERE dtl.device_id = mh.device_id
    AND t.key = 'All'
)
ORDER BY mh.analytics_time ASC
""", conn)

modelhealth.to_parquet(f"{output_dir}/modelhealth.parquet", index=False)
print("✅ Model Health table exported to Parquet!")

# -----------------------
# 4. Performance Trend Comparison
# -----------------------
performance_frames = []

for inspected_device, related_devices in device_dict.items():
    comparison_devices = sorted(set([inspected_device] + related_devices))
    comparison_sql = to_sql_in(comparison_devices)

    performance = pd.read_sql(f"""
    SELECT
        {inspected_device} AS inspected_device_id,
        mh.device_id AS comparison_device_id,
        CASE
            WHEN mh.device_id = {inspected_device} THEN 1
            ELSE 0
        END AS is_inspected_device,
        mh.analytics_time,
        mh.rmse AS performance_score
    FROM modelhealth mh
    JOIN active_model_lookup aml
        ON mh.localmodel_id = aml.localmodel_id
    WHERE mh.device_id IN ({comparison_sql})
    ORDER BY mh.analytics_time ASC, mh.device_id ASC
    """, conn)

    performance_frames.append(performance)

performance_trend_comparison = pd.concat(performance_frames, ignore_index=True)

performance_trend_comparison.to_parquet(
    f"{output_dir}/performance_trend_comparison.parquet",
    index=False
)
print("✅ Performance trend comparison exported to Parquet!")

# -----------------------
# 5. Model Performance Pivot
# -----------------------
model_perf = pd.read_sql(f"""
SELECT device_id, version_number, performance_score
FROM model_performance_pivot
WHERE device_id IN ({devices_sql})
""", conn)

model_perf.to_parquet(f"{output_dir}/model_performance_pivot.parquet", index=False)
print("✅ Model Performance Pivot table exported to Parquet!")

# -----------------------
# 6. Feature Sensitivity
# -----------------------
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

# -----------------------
# 8. Device Tag Diagnostics
# -----------------------
diagnostics = pd.read_sql(f"""
SELECT device_id, tag_value, performance, outlier_score_value, outlier_score
FROM device_tag_diagnostics
WHERE device_id IN ({devices_sql})
""", conn)

diagnostics.to_parquet(f"{output_dir}/device_tag_diagnostics.parquet", index=False)
print("✅ Device Tag Diagnostics table exported to Parquet!")

# -----------------------
# 9. Device Cross Tag Summary
# -----------------------
cross_tag = pd.read_sql(f"""
SELECT device_id, problem_pattern, outlier_ratio
FROM device_cross_tag_summary
WHERE device_id IN ({devices_sql})
""", conn)

cross_tag.to_parquet(f"{output_dir}/device_cross_tag_summary.parquet", index=False)
print("✅ Device Cross Tag Summaries table exported to Parquet!")

conn.close()

print("✅ All tables exported to Parquet!")