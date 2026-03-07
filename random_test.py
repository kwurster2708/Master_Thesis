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

#save
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
        
def test4(conn):
  cur = conn.cursor()
  classification_list = ("Underperforming", "Low Accuracy", "Partial Outlier", "Full Outlier")
  try:
      cur.execute(f"""SELECT device_id, outlier_classification
                    FROM device_outlier_classification 
                    WHERE outlier_classification IN {classification_list}
                    ORDER BY device_id;""")
      rows = cur.fetchall()
      print(rows)
      return cur.fetchall()
  except sqlite3.Error:
        return []

device = 50   
#test1(conn, device)
#test2(conn, device)
#test3(conn)
test4(conn)