#-- Importing necessary libraries --
from schema import get_full_schema, get_all_outlier_devices, get_connection
import streamlit as st
import sqlite3
import ollama
import json

#-- Helper Functions --
def create_logging (model_used, schema, device_id):
    log ={"model_used": model_used,
        "included_information": list(schema.keys()),
        "anomaly_id": f"d{device_id}"}
    return log

def get_ollama_models():
    try:
        response = ollama.list()
        models = response.get("models", [])
        
        if not models:
            st.warning("No Ollama models found. Install one using: ollama pull <model_name>")
        
        return [model["model"] for model in models]
    
    except Exception as e:
        st.error(f"Ollama connection failed: {str(e)}")
        return []

def generate_prompt(schema_data):
    """Generate prompt based on selected structure and schema data"""     
    structure =f"""Provide an easy explanation on why the following Weather Station is classified as an outlier that an engineer working with the Weather Station can understand. 
    It is the 22nd June 2024 and the target variable for the machine learning model is the temperature. Each Weather Station has one active model which is indicated by having the highest version number. 
    There is also data on the previous models regarding feature sensitivity and performance. Every device has multiple tags that show the attributes of the device. 
    For each tag on the device a exists to different timestamps that show how different it is to the devices with the same tag. 

Provide an explanation based on the following Schema:
{json.dumps(schema_data, indent=2, default=list)}

Please explain why this anomaly occurred and what it means for the weather station's prediction model."""
    
    return structure
#-- The Dashboard --

# 1. Data Layer
conn = get_connection()

# 2. Anomaly Detection Layer

st.set_page_config(page_title="🤖 Master Thesis Project", layout="wide")

st.title("🤖 Master Thesis Project")
st.markdown("An interactive dashboard for using LLMs to explain anomalies in time series weather station data.")

# Sidebar for filters
st.sidebar.header("Filters")

# Filter 1: Outlier selection based on test function
all_outliers = get_all_outlier_devices(conn)
outliers = all_outliers if all_outliers else []

outlier_options = [f"Device {o[0]}" for o in outliers] if outliers else ["No outliers found"]
outlier = st.sidebar.selectbox("Select Device ID", options= ["All"] + outlier_options)

# Get selected outlier info
selected_outlier = None
if outlier != "No outliers found" and outlier != "All":
    parts = outlier.replace("Device ", "")
    selected_outlier = int(parts)

# Schema selection checkboxes
st.sidebar.header("Schema Selection")
include_performance = st.sidebar.checkbox("Performance Context", value=True)
include_feature_sensitivity = st.sidebar.checkbox("Feature Sensitivity", value=True)

# Generate schema based on selection
schema_data = None
if selected_outlier:
    schema_data = get_full_schema(
        conn, 
        selected_outlier,
        include_model_performance=include_performance,
        include_feature_sensitivity=include_feature_sensitivity 
    )

# 3. Create columns for layout
left_col, right_col = st.columns([2,2])

# Middle column: Prompt Preview
with left_col:
    st.subheader("Prompt Preview")
    if schema_data:
        prompt_preview = generate_prompt(schema_data)
        
        # Force update of session state
        st.session_state["prompt_preview"] = prompt_preview

        st.text_area(
            "Generated Prompt",
            value=prompt_preview,
            key="prompt_preview",
            height=400
        )
    else:
        st.info("Select an anomaly to generate the prompt preview")

# Right column: LLM Model Selection and Output
with right_col:
    st.subheader("LLM Configuration")
    
    # Get available Ollama models
    ollama_models = get_ollama_models()
    if ollama_models:
        selected_model = st.selectbox("Select Ollama Model", options=ollama_models)
    else:
        selected_model = st.text_input("Enter Ollama Model Name", value="llama3.1: latest")
    
    # Button to run LLM
    if st.button("Generate LLM Output"):
        if schema_data:
            prompt_preview = generate_prompt(schema_data)
            
            #-- Logging Information --
            logs =create_logging(selected_model, schema_data, selected_outlier)
                         
            #-- Generate LLM Output --
            try:
                response = ollama.chat(
                    model=selected_model,
                    messages=[{"role": "user", "content": prompt_preview}]
                )
                llm_output = response['message']['content']
            
            except Exception as e:
                llm_output = f"Error: {str(e)}"
            
            st.session_state["logging_info"] = logs
            st.session_state['llm_output'] = llm_output
        else:
            st.warning("Please select an outlier first")
    
    # Display LLM output
    st.subheader("LLM Output and Logging Information")
    if 'llm_output' in st.session_state:
        
        formatted_display = f""" 
Logging Information:
{json.dumps(st.session_state.get('logging_info', {}), indent=2)}  
        
LLM Output:     
{st.session_state['llm_output']}"""
        
        st.text_area("Output", value=formatted_display, height=500, key="llm_output_display")
    else:
        st.info("LLM output will appear here after clicking 'Generate LLM Output'")
