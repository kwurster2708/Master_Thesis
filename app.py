#-- Importing necessary libraries --
from schema_2 import get_full_schema, get_all_outlier_devices, get_connection
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
    structure =f"""
    Schema:
{json.dumps(schema_data, indent=2, default=list)}

Based on the information provided in the schema and additional information that helps to provide a good answer, provide an easy to understand interpretation for why this weather station is an anomaly. 
What does that mean for future predictions of the weather station? 

Important information regarding the data at hand:
* The data has entries up until July 2024 treat the data as if today is the 1st July 2024.
* The data consists of multiple local models that are running on the weather station to predict the temperature.
* The local model on each weather station is continuously updated using incremental learning. The data provided is always for the active local model on the weather station (except for the Model Version History and the Historical Feature Importance).
* Every weather station has multiple tags that show the attributes of the device.  For each of these tags an outlier score exists that signalizes how different the weather station performance is compared to weather stations with the same tag.

The answer has to be provided in an easy language that a user without a data background can understand. The output should have the following structure:
1. Interpretation: Why is this weather station behaving like an anomaly? (max. 150 words)
2. What does this mean for future predictions of the device? (max. 100 words)
"""
    
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
include_feature_sensitivity = st.sidebar.checkbox("Feature Importance", value=True)

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
