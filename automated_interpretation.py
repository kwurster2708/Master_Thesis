import re
import json
import argparse
from pathlib import Path
from datetime import datetime

import ollama
from schema_4 import get_full_schema, get_connection


# -----------------------------
# Configuration
# -----------------------------
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

CONFIGURATIONS = [
    {
        "name": "Performance",
        "include_performance": True,
        "include_feature_sensitivity": False,
    },
    {
        "name": "FeatureImportance",
        "include_performance": False,
        "include_feature_sensitivity": True,
    },
    {
        "name": "Combination",
        "include_performance": True,
        "include_feature_sensitivity": True,
    },
]


# -----------------------------
# Helper functions
# -----------------------------
def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", str(name))


def create_logging(model_used, schema, device_id):
    log = {
        "model_used": model_used,
        "included_information": list(schema["to_be_evaluated_weather_station"].keys()),
        "anomaly_id": f"d{device_id}",
    }
    return log

# def create_logging(model_used, schema, device_id):
#     log = {
#         "model_used": model_used,
#         "included_information": list(schema.keys()),
#         "anomaly_id": f"d{device_id}",
#     }
#     return log

def save_experiment_output(llm_output, logging_info, device_id, model_tag, config_name, base_dir="Experiment3"):
    base_path = Path(base_dir)

    safe_model_tag = sanitize_filename(model_tag)
    folder = base_path / f"Device_{device_id}" / config_name
    folder.mkdir(parents=True, exist_ok=True)

    filepath = folder / f"{device_id}_{config_name}_{safe_model_tag}.json"

    data = {
        "logging_info": logging_info,
        "llm_output": llm_output,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(filepath)


def generate_prompt(schema_data, device_id):    
    prompt = f"""
Schema:
{json.dumps(schema_data, indent=2, default=list)}

You are helping users understand the behaviour of a machine learning model. Based on the information provided in the schema and additional information that helps to provide a good answer, provide an easy to understand interpretation for why the weather station {device_id} is an anomaly. What does that mean for future predictions of the weather station? 

Special rules:
* Important information regarding the data in the schema at hand:
* The data has entries up until July 2024 treat the data as if today is the 1st July 2024.
* The data consists of multiple local models that are running on the weather station to predict the temperature.
* The local model on each weather station is continuously updated using federated learning.
* Every weather station has multiple tags that show the attributes of the device.  For each of these tags an outlier score exists that signalizes how different the weather station performance is compared to weather stations with the same tag.

Chain of thought instructions:
Step 1: Read and understand the schema carefully.
Step 2: Identify the most important signals and determine which parts of the schema are most relevant for explaining the unusual behaviour.
Step 3: Analyze relationships between the different pieces of information and think about how the different inputs relate to each other.
Step 4: Put the weather station {device_id} into context (interpret the station not in isolation).
Step 5: Use additional background knowledge when helpful (domain knowledge, environmental conditions etc.).
Step 6: Generate possible reasons for the unusual behaviour.
Step 7: Check your reasoning critically.
Step 8: Create practical recommendations.
Step 9: Write the final explanation for a non-expert industrial user based on the previous steps.

Output Instructions:
The answer has to be provided in an easy language that a user without a data background can understand. Make sure to provide short and concise answers that answer the questions at hand without unnecessary information. 

What is important:
* Clarity: Deliver straightforward and easily comprehensible summaries. 
* Relevance: Ensure insights are directly applicable to the end user. 
* Actionability: Focus on providing practical suggestions or conclusions. 
* Use these images together with the schema.
* Only refer to what is clearly visible in the images.

Do not include obvious elements (numbers, text) from the given input unless needed.

The output should have the following structure:
1. Interpretation: Why is this weather station {device_id} behaving unusually? Explain to the engineer why the weather station is showcasing this unusual behaviour!
2. Future Predictions: What does this mean for future predictions of the weather station {device_id}? Give recommendations on what the engineer should do!
3. Reasoning: Provide a short statement of reasoning to justify your answer, but keep it concise and non-technical.
"""
    return prompt.strip()


def run_llm(model_tag, prompt, think=True, temperature=0):
    response = ollama.chat(
        model=model_tag,
        messages=[{"role": "user", "content": prompt}],
        think=think,
        stream=False,
        options={
            "temperature": temperature,
        },
    )
    return response["message"]["content"]


def generate_for_device(conn, device_id, model_key, config, output_dir="Experiment3"):
    model_cfg = MODELS[model_key]
    model_tag = model_cfg["tag"]
    config_name = config["name"]

    schema_data = get_full_schema(
        conn,
        device_id,
        include_model_performance=config["include_performance"],
        include_feature_sensitivity=config["include_feature_sensitivity"],
    )

    prompt = generate_prompt(schema_data, device_id)
    logging_info = create_logging(model_tag, schema_data, device_id)

    try:
        llm_output = run_llm(
            model_tag=model_tag,
            prompt=prompt,
            think=model_cfg.get("think", True),
            temperature=0,
        )
        logging_info["status"] = "success"
    except Exception as e:
        llm_output = f"Error: {str(e)}"
        logging_info["status"] = "error"
        logging_info["error_message"] = str(e)

    saved_path = save_experiment_output(
        llm_output=llm_output,
        logging_info=logging_info,
        device_id=device_id,
        model_tag=model_tag,
        config_name=config_name,
        base_dir=output_dir,
    )

    return {
        "device_id": device_id,
        "model": model_tag,
        "configuration": config_name,
        "status": logging_info["status"],
        "saved_path": saved_path,
    }


def run_batch(device_ids, selected_models=None, output_dir="Experiment3"):
    conn = get_connection()
    results = []

    model_keys = selected_models if selected_models else list(MODELS.keys())

    for device_id in device_ids:
        for model_key in model_keys:
            if model_key not in MODELS:
                print(f"Skipping unknown model key: {model_key}")
                continue

            for config in CONFIGURATIONS:
                print(
                    f"Running device={device_id}, model={MODELS[model_key]['tag']}, config={config['name']}"
                )
                result = generate_for_device(
                    conn=conn,
                    device_id=device_id,
                    model_key=model_key,
                    config=config,
                    output_dir=output_dir,
                )
                results.append(result)
                print(f"Saved: {result['saved_path']} ({result['status']})")

    return results


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-generate LLM interpretations for anomaly weather stations."
    )
    parser.add_argument(
        "--devices",
        nargs="+",
        type=int,
        required=True,
        help="List of device IDs, e.g. --devices 101 205 309",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(MODELS.keys()),
        default=list(MODELS.keys()),
        help="Subset of models to run, e.g. --models deepseek qwen",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="Experiment3",
        help="Base output directory for JSON files.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    results = run_batch(
        device_ids=args.devices,
        selected_models=args.models,
        output_dir=args.output_dir,
    )

    summary_path = Path(args.output_dir) / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nBatch finished. Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()