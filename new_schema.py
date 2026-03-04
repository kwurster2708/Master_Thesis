import sqlite3, json

conn = sqlite3.connect(
        r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite"
    )

def test(conn):
    cur = conn.cursor()
    
    try: 
        cur.execute("""SELECT outlier_score_value, outlier_score_fn, mae, mape, rmse 
                    FROM modelhealth 
                    WHERE outlier_score_value < -21;
                    """)
        
        anomalies = {}
        outlier_information = cur.fetchall()
        
        for i, row in enumerate(outlier_information, start=1):
            anomalies[f"Anomaly {i}"] = {
                "Outlier Score Value": row[0],
                "Outlier Score Function": row[1],
                "MAE": row[2],
                "MAPE": row[3],
                "RMSE": row[4]
            }

        return anomalies, list(anomalies.keys())
        
        #anomalies = {}
        #Count = 0
        #outlier_information = cur.fetchall()
        #for row in outlier_information:
        #    anomaly = {
        #        "Outlier Score Value": row[0],
        #        "Outlier Score Function": row[1],
        #        "MAE": row[2],
        #        "MAPE": row[3],
        #        "RMSE": row[4]
        #    }
        #    Count += 1
        #    anomalies[f"Anomaly {Count}"] = anomaly
        #return anomalies, outlier_information
            
    except sqlite3.Error as e:
        print(f"Error executing outlier query: {e}")
        return []

def outlier_information(conn, tag_id, device_id, localmodel_id, modelbinary_id, outlier_score_value):
    """Query outlier important information from modelhealth table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT update_time, outlier_score_value, outlier_score_fn, mae, mape, rmse 
                    FROM modelhealth 
                    WHERE tag_id = {tag_id} AND device_id = {device_id} AND localmodel_id = {localmodel_id} AND modelbinary_id = {modelbinary_id} AND outlier_score_value = {outlier_score_value};
                    """)
        
        outlier_information = cur.fetchall()
        
        timestamp = None
        anomaly = None
        performance = None
        
        for row in outlier_information:
            timestamp = row[0]
            anomaly = {"Outlier Score Value": row[1], "Outlier Score Function": row[2]}
            performance = {"MAE": row[3], "MAPE": row[4], "RMSE": row[5]}
        return timestamp, anomaly, performance
    
    except sqlite3.Error as e:
        print(f"Error executing outlier query: {e}")
        return None, None, None


def tag_information(conn, tag_id):
    """Query tag information from tag table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT key, value
                    FROM tag
                    WHERE id = {tag_id};
                    """)
        
        tag_information = cur.fetchall()
        
        tags = {}
        for row in tag_information:
            tags[f"{row[0]}"] = row[1]
        return tags
    
    except sqlite3.Error as e:
        print(f"Error executing tag information query: {e}")
        return {}

def other_tag_information(conn, tag_id, device_id):
    """Query tag information from tag table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT key, value
                    FROM tag
                    WHERE id IN (SELECT tag_id
                                FROM devicetaglink
                                WHERE device_id = {device_id} AND tag_id != {tag_id} AND tag_id != 1);
                    """)
        
        tag_information = cur.fetchall()
        other_tags = {}
        
        for row in tag_information:
            other_tags[f"{row[0]}"] = row[1]
        return other_tags
    
    except sqlite3.Error as e:
        print(f"Error executing tag information query: {e}")
        return {}

def metric_information(conn, localmodel_id):
    """Query metric information from metric table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT name, value
                    FROM metric
                    WHERE localmodel_id = {localmodel_id}; 
                    """)
        
        metric_information = cur.fetchall()
        metric = {}
        
        for row in metric_information:
            metric[row[0]] = row[1]
        return metric

    except sqlite3.Error as e:
        print(f"Error executing metric information query: {e}")
        return {}
        
def localmodel_information(conn, localmodel_id):
    """Query local model information from local model table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT last_train_time, is_compatible, is_valid
                    FROM localmodel
                    WHERE id = {localmodel_id}; 
                    """)
        
        localmodel_information = cur.fetchall()

        last_train_time = None
        is_compatible = None
        is_valid = None
        
        for row in localmodel_information:
            last_train_time = row[0]
            is_compatible = row[1]
            is_valid = row[2]
        return last_train_time, is_compatible, is_valid
    
    except sqlite3.Error as e:
        print(f"Error executing local model information query: {e}")
        return None, None, None

def modelbinary_information(conn, modelbinary_id):
    """Query modelbinary information from modelbinary table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT is_deserializable, contains_statistics, is_single_target,
                    is_producing_predictions, attribute_sensitivities_id
                    FROM modelbinary
                    WHERE id = {modelbinary_id};
                    """)
        
        modelbinary_information = cur.fetchall()

        modelbinary = None
        attributes_sensitivities_id = None
        
        for row in modelbinary_information:
            modelbinary = {"Is Deserializable": row[0], "Contains Statistics": row[1], "Is Single Target": row[2], "Is Producing Predictions": row[3]}
            attributes_sensitivities_id = row[4]   
        return modelbinary, attributes_sensitivities_id
    
    except sqlite3.Error as e:
        print(f"Error executing modelbinary information query: {e}")
        return None, None
        
def attributes_information(conn, attributes_sensitivities_id):
    """Query attributes information from attributesensitivities table"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT json(attribute_sensitivities)
                    FROM attributesensitivities
                    WHERE id = {attributes_sensitivities_id};
                    """)
        
        attributes_information = cur.fetchall()

        attributes = None
        
        for row in attributes_information:
            attributes = json.loads(row[0])
        return attributes
    
    except sqlite3.Error as e:
        print(f"Error executing attributes information query: {e}")
        return None



def find_all_outlier_devices(conn):
    """Query outliers from modelhealth table"""
    cur = conn.cursor()

    try:
        cur.execute("""SELECT device_id, localmodel_id, COUNT(*) as device_count
                    FROM modelhealth
                    WHERE outlier_score_value < -5
                    GROUP BY device_id, localmodel_id
                    ORDER BY device_count DESC;""")
        outliers = cur.fetchall()
        
        return outliers
    except sqlite3.Error as e:
        print(f"Error finding all the outliers: {e}")
        return []
        
def create_single_schema(conn, tag_id, device_id, localmodel_id, modelbinary_id, outlier_score_value):
    """Create a JSON schema of the database"""
    timestamp, anomaly, performance = outlier_information(conn, tag_id, device_id, localmodel_id, modelbinary_id, outlier_score_value)
    tags = tag_information(conn, tag_id) or {}
    other_tags = other_tag_information(conn, tag_id, device_id) or {}
    metrics = metric_information(conn, localmodel_id) or {}
    last_train_time, is_compatible, is_valid = localmodel_information(conn, localmodel_id) or (None, None, None)
    modelbinary, attributes_sensitivities_id = modelbinary_information(conn, modelbinary_id) or (None, None)
    attributes = attributes_information(conn, attributes_sensitivities_id) if attributes_sensitivities_id else {}
    schema = {
        "Tag ID": tag_id,
        "Local Model ID": localmodel_id,
        "Model Binary ID": modelbinary_id,
        "Timestamp": timestamp,
        "Anomaly": anomaly,
        "Performance": performance,
        "Tag Information": {
            "Outlier Tag": tags,
            "Other Device Tags": other_tags
            },
        "Local Model Information": {
            "Metrics": metrics,
            "Last Train Time": last_train_time,
            "Is Compatible": is_compatible,
            "Is Valid": is_valid
        },
        "Model Binary Information": modelbinary,
        "Attributes Information": attributes
    }
    return schema

def create_big_schema(conn, device_id, localmodel_id):
    """Create a JSON schema for all the outliers in the database"""
    cur = conn.cursor()

    try:
        cur.execute(f"""SELECT tag_id, modelbinary_id, outlier_score_value
                    FROM modelhealth
                    WHERE device_id = {device_id} AND localmodel_id = {localmodel_id};""")
        outliers = cur.fetchall()
        
        count_outlier = 0
        count_normal = 0
        
        schema = {
            "Device ID": device_id,
            "Local Model ID": localmodel_id,
            "Outliers": {},
            "Normal Data Points": {}
        }
        
        for row in outliers:
            if row[2] < -5:
                count_outlier += 1
                key = f"Outlier {count_outlier}"
                value = create_single_schema(conn, row[0], device_id, localmodel_id, row[1], row[2])
                schema["Outliers"][key] = value
            else:
                count_normal += 1
                key = f"Normal data point {count_normal}"
                value = create_single_schema(conn, row[0], device_id, localmodel_id, row[1], row[2])
                schema["Normal Data Points"][key] = value
        return schema
    
    except sqlite3.Error as e:
        print(f"Error creating big schema: {e}")
        return {}
