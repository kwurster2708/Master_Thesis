#-- Importing necessary libraries --
from Diagnostic_Schema import find_outlier_devices, create_big_schema
import streamlit as st
import sqlite3

#-- The Dashboard --

# 1. Data Layer
conn = sqlite3.connect(
        r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite"
    )

# 2. Anomaly Detection Layer

st.set_page_config(page_title="Master Thesis Project", layout="wide")

st.title("📊 Master Thesis Project")
st.markdown("An interactive dashboard for using LLms to explain anomalies in time series weather station data.")
# Sidebar for filters
st.sidebar.header("Filters")
outlier = st.sidebar.selectbox("Select Device ID and Local Model ID Combo", options=find_outlier_devices(conn))
# When an option is selected, create the big schema and display it
if outlier:
    create_big_schema(conn, outlier[0], outlier[1])
       
# 3. Prompt Builder Layer
