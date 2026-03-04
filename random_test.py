import sqlite3

conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")

def active_model_id(conn, device_id):
    """Get the active model ID for a given device"""
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT id 
                    FROM localmodel
                    WHERE device_id = {device_id} 
                    ORDER BY version_number DESC LIMIT 1;""")
        row = cur.fetchone()
        return row[0] if row else None
    except sqlite3.Error as e:
        print(f"Error fetching active model ID for Device ID {device_id}: {e}")
        return None


def test1(conn, device_id):
    """Test if tags have different performance for the same device and model"""
    cur = conn.cursor()
    
    local_model_id = active_model_id(conn, device_id)
    
    try:
        cur.execute(f"""SELECT tag_id, modelbinary_id, outlier_score_value, outlier_score_fn, mae, mape, rmse, analytics_time
                    FROM modelhealth 
                    WHERE device_id = {device_id} AND localmodel_id = {local_model_id}
                    ORDER BY analytics_time DESC;""")
        
        results = cur.fetchall()
        
        for row in results:
            print(f"Tag ID: {row[0]}, Model Binary ID: {row[1]}, Outlier Score Value: {row[2]}, Outlier Score Function: {row[3]}, MAE: {row[4]}, MAPE: {row[5]}, RMSE: {row[6]}, Analytics Time: {row[7]}")
    
    except sqlite3.Error as e:
        print(f"Error executing test query: {e}")
        
def test2(conn, device_id):
    """Test if metrics are different for the same device and model across timestamps"""
    cur = conn.cursor()
    
    local_model_id = active_model_id(conn, device_id)
    
    try:
        cur.execute(f"""SELECT name, value, create_time
                    FROM metric 
                    WHERE localmodel_id = {local_model_id}
                    ORDER BY create_time DESC;""")
        
        results = cur.fetchall()
        
        for row in results:
            print(f"{row[0]}: {row[1]}, Create Time: {row[2]}")
    
    except sqlite3.Error as e:
        print(f"Error executing test query: {e}")
        
def test3(conn):
    """Print all tables in the database to check for any issues"""
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        for table in tables:
            print(table[0])
    except sqlite3.Error as e:
        print(f"Error retrieving table names: {e}")

device = 50   
#test1(conn, device)
#test2(conn, device)
test3(conn)


{
  "Device Information": {
    "tags": {
      "All": "All",
      "country": "Russian Federation",
      "terrain": "lowland",
      "station_id": "RSI0000UHMA",
      "city": "Anadyr",
      "tz": "UTC+12",
      "urbanization": "town",
      "state": "Chukotka",
      "name": "UGOLNY"
    },
    "target": "Temperature"
  },
  "Active Model Context": {
    "version": 37,
    "is_valid": 1,
    "is_compatible": 1,
    "model_age_days": null,
    "training_recency_bucket": null
  },
  "Model Performance Context": {
    "average metrics": {
      "MAE": 7.846823160464947,
      "RMSE": 2.9339656035105386,
      "MAPE": 8.593677795850313
    },
    "overall_error_score": 6.314171549965012,
    "trend": "degrading",
    "worst_performance_error_score": "2025-01-30 11:08:22",
    "worst_time_stamp": 6.603918053883438
  },
  "Model Version History": {
    "versions_available": 35,
    "performance_trend": {
      "MAE": 4.123225484575544,
      "MAPE": 5.056853021894183,
      "RMSE": null
    }
  },
  "Feature Sensitivity": {},
  "Tag Diagnostics": {
    "UTC+12": {
      "performance": 6.277248585087852,
      "outlier_score_value": -10.153536436984563,
      "outlier_score": "extreme",
      "analytics_time": "2024-06-22 22:00:00.000000"
    },
    "town": {
      "performance": 3.016869316223862,
      "outlier_score_value": -1.0824139690334018,
      "outlier_score": "moderate",
      "analytics_time": "2024-06-22 22:00:00.000000"
    },
    "All": {
      "performance": 2.9972391603832618,
      "outlier_score_value": -1.1073992866289661,
      "outlier_score": "moderate",
      "analytics_time": "2024-06-22 22:00:00.000000"
    },
    "lowland": {
      "performance": 2.5180594557200333,
      "outlier_score_value": -1.1297778478984046,
      "outlier_score": "moderate",
      "analytics_time": "2024-06-22 22:00:00.000000"
    },
    "Worst Tag": "{'UTC+12'}"
  },
  "Cross Tag Context": {
    "worst_performance_tag": "UTC+12",
    "worst_performance": 6.277248585087852,
    "average_performance": 3.7023541293537523,
    "worst_outlier_tag": "UTC+12",
    "problem_pattern": "tag_specific",
    "extreme_outlier_ratio": 0.25
  }
}