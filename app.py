#-- Importing necessary libraries --
import re
from schema_3 import get_full_schema, get_all_outlier_devices, get_connection
import streamlit as st
import sqlite3
import ollama
import json
from pathlib import Path
from datetime import datetime

#-- Helper Functions --
def create_logging (model_used, schema, device_id):
    log ={"model_used": model_used,
        "included_information": list(schema["to_be_evaluated_weather_station"].keys()),
        "anomaly_id": f"d{device_id}"}
    return log

def get_configuration_name(include_performance, include_feature_sensitivity):
    if include_performance and include_feature_sensitivity:
        return "Combination"
    elif include_feature_sensitivity:
        return "FeatureImportance"
    elif include_performance:
        return "Performance"
    return "Default"

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", str(name))

def save_experiment_output(llm_output, logging_info, device_id, model_tag, config_name):
    base_path = Path("Experiment2")
    
    #sanitize model names
    safe_model_tag = sanitize_filename(model_tag)
    
    folder = base_path / safe_model_tag / f"Device_{device_id}"
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / f"{device_id}_{config_name}.json"
    
    data = {
        "logging_info": logging_info,
        "llm_output": llm_output}
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    return str(filepath)

MODELS = {
    "deepseek": {
        "tag": "deepseek-v3.2:cloud",
        "supports_images": False,
        "think": True,
    },
    "qwen": {
        "tag": "qwen3.5:cloud",
        "supports_images": True,
        "think": True,
    },
    "kimi": {
        "tag": "kimi-k2.5:cloud",
        "supports_images": True,
        "think": True,
    },
}

# def get_ollama_models():
#     try:
#         response = ollama.list()
#         models = response.get("models", [])
        
#         if not models:
#             st.warning("No Ollama models found. Install one using: ollama pull <model_name>")
        
#         return [model["model"] for model in models]
    
#     except Exception as e:
#         st.error(f"Ollama connection failed: {str(e)}")
#         return []

def generate_prompt(schema_data, device_id):
    """Generate prompt based on selected structure and schema data"""     
    structure =f"""
    Schema:
{json.dumps(schema_data, indent=2, default=list)}

Based on the information provided in the schema and additional information that helps to provide a good answer, provide an easy to understand interpretation for why the weather station {device_id} is an anomaly. 
What does that mean for future predictions of the weather station? 

Important information regarding the data at hand:
* The data has entries up until July 2024 treat the data as if today is the 1st July 2024.
* The data consists of multiple local models that are running on the weather station to predict the temperature.
* The local model on each weather station is continuously updated using incremental learning. The data provided is always for the active local model on the weather station (except for the Model Version History and the Historical Feature Importance).
* Every weather station has multiple tags that show the attributes of the device.  For each of these tags an outlier score exists that signalizes how different the weather station performance is compared to weather stations with the same tag.
* The schema represents multiple different weather stations in the same state or country.

Chain of thought instructions:
1. Briefly analyze what the explanation is saying.
2. Check whether it correctly answers why the anomaly occurred.
3. Assess whether it uses feature importance and performance information correctly.
4. Evaluate clarity, completeness, and usefulness for a non-expert user.
5. Based on your reasoning, assign scores.
Think step-by-step internally before answering, but do NOT include your reasoning in the final output.

The answer has to be provided in an easy language that a user without a data background can understand. Make sure to provide short and concise answers that answer the questions at hand without unnecessary information. The output should have the following structure:
1. Interpretation: Why is the weather station {device_id} behaving like an anomaly?
2. What does this mean for future predictions of the weather station {device_id}?
3. Provide a short statement of reasoning to justify your answer, but keep it concise and non-technical.
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

# Initialize session state for tracking changes
if 'prev_outlier' not in st.session_state:
    st.session_state['prev_outlier'] = selected_outlier
if 'prev_performance' not in st.session_state:
    st.session_state['prev_performance'] = include_performance
if 'prev_feature' not in st.session_state:
    st.session_state['prev_feature'] = include_feature_sensitivity

# Check if device or schema changed
device_changed = st.session_state['prev_outlier'] != selected_outlier
schema_changed = (st.session_state['prev_performance'] != include_performance or 
                  st.session_state['prev_feature'] != include_feature_sensitivity)

# Clear LLM output if device or schema changed
if device_changed or schema_changed:
    st.session_state.pop('llm_output', None)
    st.session_state.pop('logging_info', None)

# Update tracking variables
st.session_state['prev_outlier'] = selected_outlier
st.session_state['prev_performance'] = include_performance
st.session_state['prev_feature'] = include_feature_sensitivity

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
        prompt_preview = generate_prompt(schema_data, selected_outlier)
        
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
    ollama_models = [MODELS[model_key]["tag"] for model_key in MODELS.keys()]
    if ollama_models:
        selected_model = st.selectbox("Select Ollama Model", options=ollama_models)
    else:
        selected_model = st.text_input("Enter Ollama Model Name", value="llama3.1: latest")
    
    # Button to run LLM
    if st.button("Generate LLM Output"):
        if schema_data:
            prompt_preview = generate_prompt(schema_data, selected_outlier)
            
            #-- Logging Information --
            logs =create_logging(selected_model, schema_data, selected_outlier)
                         
            #-- Generate LLM Output --
            try:
                response = ollama.chat(
                    model=selected_model,
                    messages=[{"role": "user", "content": prompt_preview}],
                    think=True,
                    stream=False,
                    #tools=[{"type": "web_search"}],
                    options={
                        "temperature": 0,
                    },     
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
        
        # Save Output button
        config_name = get_configuration_name(include_performance, include_feature_sensitivity)
        if st.button("Save Output"):
            saved_path = save_experiment_output(
                llm_output=st.session_state['llm_output'],
                logging_info=st.session_state['logging_info'],
                device_id=selected_outlier,
                model_tag=selected_model,
                config_name=config_name
            )
            st.success(f"Saved to: {saved_path}")
    else:
        st.info("LLM output will appear here after clicking 'Generate LLM Output'")
