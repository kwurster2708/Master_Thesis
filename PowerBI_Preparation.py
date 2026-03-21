import sqlite3
import pandas as pd
import os

conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

# query = """
# WITH tag_filtered AS (
#     SELECT dtl.device_id, t.key, t.value
#     FROM devicetaglink dtl
#     JOIN tag t ON t.tag_id = dtl.tag_id
# ),

# modelhealth_filtered AS (
#     SELECT mh.device_id,
#            mh.analytics_time,
#            mh.rmse AS performance_score
#     FROM modelhealth mh
#     JOIN active_model_lookup aml 
#         ON mh.localmodel_id = aml.localmodel_id
#     JOIN devicetaglink dtl 
#         ON mh.device_id = dtl.device_id
#     JOIN tag t 
#         ON t.tag_id = dtl.tag_id
#     WHERE t.key = 'All'
# ),

# feature_sensitivity_filtered AS (
#     SELECT fst.device_id,
#            fst.top_feature_1,
#            fst.importance_1,
#            fst.top_feature_2,
#            fst.importance_2,
#            fst.top_feature_3,
#            fst.importance_3
#     FROM feature_sensitivity_top3 fst
#     JOIN active_model_lookup aml
#         ON fst.modelbinary_id = aml.modelbinary_id
# )

# SELECT 
#     dc.device_id,
#     dc.classification,

#     -- Tag info
#     tf.key,
#     tf.value,

#     -- Active model lookup
#     aml.is_valid AS no_nan_predictions,
#     aml.is_compatible AS is_compatible_with_existing_localmodels,

#     -- Model health
#     mh.analytics_time,
#     mh.performance_score,

#     -- Model performance
#     mpp.version_number,
#     mpp.performance_score AS model_performance_score,

#     -- Feature sensitivity (top 3)
#     fs.top_feature_1,
#     fs.importance_1,
#     fs.top_feature_2,
#     fs.importance_2,
#     fs.top_feature_3,
#     fs.importance_3,

#     -- Feature sensitivity historical
#     fsh.hist_top_1,
#     fsh.hist_sens_1,
#     fsh.hist_top_2,
#     fsh.hist_sens_2,
#     fsh.hist_top_3,
#     fsh.hist_sens_3,

#     -- Diagnostics
#     dtd.tag_value,
#     dtd.performance,
#     dtd.outlier_score_value,
#     dtd.outlier_score,

#     -- Cross tag summary
#     dcts.problem_pattern,
#     dcts.outlier_ratio

# FROM device_classification dc

# LEFT JOIN tag_filtered tf 
#     ON dc.device_id = tf.device_id

# LEFT JOIN active_model_lookup aml 
#     ON dc.device_id = aml.device_id

# LEFT JOIN modelhealth_filtered mh 
#     ON dc.device_id = mh.device_id

# LEFT JOIN model_performance_pivot mpp 
#     ON dc.device_id = mpp.device_id

# LEFT JOIN feature_sensitivity_filtered fs 
#     ON dc.device_id = fs.device_id

# LEFT JOIN feature_sensitivity_historical fsh 
#     ON dc.device_id = fsh.device_id

# LEFT JOIN device_tag_diagnostics dtd 
#     ON dc.device_id = dtd.device_id

# LEFT JOIN device_cross_tag_summary dcts 
#     ON dc.device_id = dcts.device_id
# """

# # Read into pandas
# df = pd.read_sql(query, conn)

# df.to_parquet("Database.parquet", index = False)


# Path setup
output_dir = "parquet_output"
os.makedirs(output_dir, exist_ok=True)

device_filter = """SELECT device_id
FROM device_classification
WHERE outlier_classification IN (
    'Underperforming',
    'Low Accuracy',
    'Partial Outlier',
    'Full Outlier')"""

# -----------------------
# 1. Device Classification (Dimension)
# -----------------------
device_classification = pd.read_sql("""
SELECT DISTINCT device_id, classification
FROM device_outlier_classification
WHERE device_id IN ({device_filter})
ORDER BY device_id
""", conn)

device_classification.to_parquet(f"{output_dir}/device_classification.parquet", index=False)
print("✅ Classification table exported to Parquet!")

# -----------------------
# 2. Tags (Bridge / Dimension) #maybe add active model!
# -----------------------
tags = pd.read_sql("""
SELECT DISTINCT dtl.device_id, t.key, t.value
FROM devicetaglink dtl
JOIN tag t ON t.id = dtl.tag_id
WHERE t.key <> 'All' AND dtl.device_id IN ({device_filter})
""", conn)

tags.to_parquet(f"{output_dir}/tags.parquet", index=False)
print("✅ Tags table exported to Parquet!")

# -----------------------
# 3. Active Model Lookup
# -----------------------
# active_model = pd.read_sql("""
# SELECT device_id,
#        is_valid AS no_nan_predictions,
#        is_compatible AS is_compatible_with_existing_localmodels,
#        localmodel_id
# FROM active_model_lookup
# WHERE device_id IN ({device_filter})
# """, conn)

# active_model.to_parquet(f"{output_dir}/active_model_lookup.parquet", index=False)
# print("✅ Active Model Lookup table exported to Parquet!")

# -----------------------
# 4. Model Health (filtered)
# -----------------------
modelhealth = pd.read_sql("""
SELECT mh.device_id,
       mh.analytics_time,
       mh.rmse AS performance_score
FROM modelhealth mh
JOIN active_model_lookup aml 
    ON mh.localmodel_id = aml.localmodel_id
WHERE mh.device_id IN ({device_filter})
AND EXISTS (
    SELECT 1
    FROM devicetaglink dtl
    JOIN tag t on t.id = dtl.tag_id
    WHERE dtl.device_id = mh.device_id
    AND t.key = 'All'
)
""", conn)

modelhealth.to_parquet(f"{output_dir}/modelhealth.parquet", index=False)
print("✅ Model Health table exported to Parquet!")

# -----------------------
# 5. Model Performance Pivot
# -----------------------
model_perf = pd.read_sql("""
SELECT device_id, version_number, performance_score
FROM model_performance_pivot
WHERE device_id IN ({device_filter})
""", conn)

model_perf.to_parquet(f"{output_dir}/model_performance_pivot.parquet", index=False)
print("✅ Model Performance Pivot table exported to Parquet!")

# -----------------------
# 6. Feature Sensitivity Top 3
# -----------------------
feature_top3 = pd.read_sql("""
SELECT aml.device_id,
       fst.top_feature_1,
       fst.importance_1,
       fst.top_feature_2,
       fst.importance_2,
       fst.top_feature_3,
       fst.importance_3
FROM feature_sensitivity_top3 fst
JOIN active_model_lookup aml
    ON fst.modelbinary_id = aml.modelbinary_id
WHERE aml.device_id IN ({device_filter})
""", conn)

feature_top3.to_parquet(f"{output_dir}/feature_sensitivity_top3.parquet", index=False)
print("✅ Feature Sensitivity Top 3 table exported to Parquet!")

# -----------------------
# 7. Feature Sensitivity Historical
# -----------------------
feature_hist = pd.read_sql("""
SELECT *
FROM feature_sensitivity_historical
WHERE device_id IN ({device_filter})
""", conn)

feature_hist.to_parquet(f"{output_dir}/feature_sensitivity_historical.parquet", index=False)
print("✅ Feature Sensitivity Historical table exported to Parquet!")

# -----------------------
# 8. Device Tag Diagnostics
# -----------------------
diagnostics = pd.read_sql("""
SELECT device_id, tag_value, performance, outlier_score_value, outlier_score
FROM device_tag_diagnostics
WHERE device_id IN ({device_filter})
""", conn)

diagnostics.to_parquet(f"{output_dir}/device_tag_diagnostics.parquet", index=False)
print("✅ Device Tag Diagnostics table exported to Parquet!")

# -----------------------
# 9. Device Cross Tag Summary
# -----------------------
cross_tag = pd.read_sql("""
SELECT device_id, problem_pattern, outlier_ratio
FROM device_cross_tag_summary
WHERE device_id IN ({device_filter})
""", conn)

cross_tag.to_parquet(f"{output_dir}/device_cross_tag_summary.parquet", index=False)
print("✅ Device Cross Tag Summaries table exported to Parquet!")

conn.close()

print("✅ All tables exported to Parquet!")