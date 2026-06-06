import sqlite3
import matplotlib.pyplot as plt
import numpy as np

conn = sqlite3.connect('Original_DB.sqlite')
cursor = conn.cursor()

# Count of devices
cursor.execute("SELECT COUNT(*) FROM device")
device_count = cursor.fetchone()[0]
print(f"Total devices: {device_count}")

# different tags
cursor.execute("SELECT DISTINCT key FROM tag")
tags = cursor.fetchall()
print(f"Distinct tag keys: {tags}")

# different feature sensitivities 
cursor.execute("""
    SELECT DISTINCT json_each.key AS feature
    FROM attributesensitivities,
         json_each(attributesensitivities.attribute_sensitivities)
    ORDER BY feature
""")
features = [row[0] for row in cursor.fetchall()]
features = sorted(features)
print(f"Distinct features in attribute sensitivities: {features}")

# Distribution of global RMSE values
cursor.execute("SELECT mh.rmse FROM modelhealth mh WHERE mh.rmse IS NOT NULL")
global_rmse_values = [row[0] for row in cursor.fetchall()]
plt.hist(global_rmse_values, bins=30, alpha=0.7, color='blue')
plt.xlabel('Global RMSE')
plt.ylabel('Frequency')
plt.title('Distribution of Global RMSE Values')
plt.show()

# different metrics for local performance
cursor.execute("SELECT DISTINCT name FROM metric")
metrics = cursor.fetchall()
print(f"Distinct metric names: {metrics}")

# Distribution of local RMSE values
cursor.execute("SELECT m.value FROM metric m WHERE m.name = 'rmse' AND m.value IS NOT NULL")
local_rmse_values = [row[0] for row in cursor.fetchall()]
percentile_value = np.percentile(local_rmse_values, 95)

print(f"95th percentile value: {percentile_value:.2f}")

plt.hist(local_rmse_values, bins=30, alpha=0.7, color='green')
plt.xlabel('Local RMSE')
plt.ylabel('Frequency')
plt.title('Distribution of Local RMSE Values')
plt.axvline(percentile_value, color='red', linestyle='--', linewidth=2,
            label=f'95th Percentile = {percentile_value:.2f}')
plt.show()

# Distribution of Concept Drift values
cursor.execute("SELECT m.value FROM metric m WHERE m.name = 'cde.mean' AND m.value IS NOT NULL")
concept_drift_values = [row[0] for row in cursor.fetchall()]
plt.hist(concept_drift_values, bins=30, alpha=0.7, color='green')
plt.xlabel('Concept Drift')
plt.ylabel('Frequency')
plt.title('Distribution of Concept Drift Values')
plt.show()

# Distribution of outlier values (vertical line at -2.0)
cursor.execute("SELECT mh.outlier_score_value FROM modelhealth mh WHERE mh.outlier_score_value IS NOT NULL")
outlier_values = [row[0] for row in cursor.fetchall()]
plt.hist(outlier_values, bins=30, alpha=0.7, color='red')
plt.xlabel('Outlier Score Value')
plt.ylabel('Frequency')
plt.title('Distribution of Outlier Values')
plt.axvline(x=-2.0, color='black', linestyle='--', linewidth=2)
plt.show()

conn.close()

# Distibution of seed model performance scores
cursor.execute("SELECT performance_score FROM seedmodel WHERE performance_score IS NOT NULL")
performance_scores = [row[0] for row in cursor.fetchall()]
percentile_value = np.percentile(performance_scores, 85)

print(f"85th percentile value: {percentile_value:.2f}")

plt.hist(performance_scores, bins=30, alpha=0.7, color='purple')
plt.xlabel('Seed Model Performance Score')
plt.ylabel('Frequency')
plt.axvline(percentile_value, color='red', linestyle='--', linewidth=2,
            label=f'85th Percentile = {percentile_value:.2f}')
plt.title('Distribution of Seed Model Performance Scores')
plt.show()

### Additional EDA after database augmentation ###

# Classification distribution
conn2 = sqlite3.connect('WeatherData.sqlite')
cur2 = conn2.cursor()
cur2.execute("""SELECT outlier_classification, COUNT(*) 
        FROM device_outlier_classification 
        GROUP BY outlier_classification
        WHERE outlier_classification = 'Functioning'""")
classifications = cur2.fetchall()
plt.bar([row[0] for row in classifications], [row[1] for row in classifications], color=['green', 'orange', 'red'])
plt.xlabel('Outlier Classification')
plt.ylabel('Count')
plt.title('Distribution of Outlier Classifications')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

conn2.close()
