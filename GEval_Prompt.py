"""
Generating evaluation prompts for G-Eval human evaluation based on experiment outputs and input prompts.
"""
from pathlib import Path
import json
from docx import Document
from docx.shared import Inches, Pt, RGBColor

BASE_DIR = Path(__file__).parent
NUM_EXPERIMENTS = 4

CONFIGURATIONS = ["FeatureImportance", "Performance", "Combination"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

MODELS_EXP_1_2_3 = 3
MODELS_EXP_4 = 2

PICTURES_DIR = BASE_DIR / "pictures"
EXPECTED_OUTPUTS_DIR = BASE_DIR / "Expected_Outputs"
OUTPUT_DIR = BASE_DIR / "Generated_Evaluation_Prompts_DOCX"

def read_input_file(path: Path) -> str:
    """Read input JSON file and return the full prompt text."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)

def read_experiment_file(path: Path) -> dict:
    """Read experiment output JSON and return parsed dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_device_id(device_name: str) -> str:
    """Extract numeric device ID from folder name (e.g., 'Device_88' -> '88')."""
    return device_name.replace("Device_", "")

def read_expected_explanation(device: str) -> str:
    """Read expected explanation text for a device."""
    expected_file = EXPECTED_OUTPUTS_DIR / f"{device}.txt"
    if expected_file.exists():
       return expected_file.read_text(encoding="utf-8")
    return "[Expected explanation file not found]"

def find_input_file(input_folder: Path, device: str, configuration: str) -> Path:
    """Find the input prompt file for a device/configuration."""
    device_id = get_device_id(device)
    pattern = f"{device_id}_{configuration}.json"
    matches = list((input_folder / device).glob(pattern))
    if not matches:
        raise FileNotFoundError(f"Input file not found: {input_folder}/{device}/{pattern}")
    return matches[0]

def find_experiment_files(experiment_folder: Path, device: str, configuration: str) -> list[Path]:
    """Find all model output files for a device/configuration in an experiment."""
    config_dir = experiment_folder / device / configuration
    if not config_dir.exists():
        return []
    return sorted(config_dir.glob("*.json"))

def find_device_pictures(exp_num: int, device_id: str, configuration: str) -> list[Path]:
    """Find associated pictures for a device/configuration/experiment."""
    pictures = []
    if exp_num == 4:
        if configuration == "FeatureImportance":
            fi_path = PICTURES_DIR / "feature_importance" / f"d{device_id}_feature_importance.png"
            outlier_path = PICTURES_DIR / "tag_outliers" / f"d{device_id}_outliers.png"
            if fi_path.exists():
                pictures.append(fi_path)
            if outlier_path.exists():
                pictures.append(outlier_path)
        elif configuration == "Performance":
            perf_path = PICTURES_DIR / "performance" / f"d{device_id}_performance.png"
            tagperf_path = PICTURES_DIR / "tag_performance" / f"d{device_id}_tag_performance.png"
            outlier_path = PICTURES_DIR / "tag_outliers" / f"d{device_id}_outliers.png"
            if perf_path.exists():
                pictures.append(perf_path)
            if tagperf_path.exists():
                pictures.append(tagperf_path)
            if outlier_path.exists():
                pictures.append(outlier_path)
        elif configuration == "Combination":
            fi_path = PICTURES_DIR / "feature_importance" / f"d{device_id}_feature_importance.png"
            perf_path = PICTURES_DIR / "performance" / f"d{device_id}_performance.png"
            tagperf_path = PICTURES_DIR / "tag_performance" / f"d{device_id}_tag_performance.png"
            outlier_path = PICTURES_DIR / "tag_outliers" / f"d{device_id}_outliers.png"
            if fi_path.exists():
                pictures.append(fi_path)
            if perf_path.exists():
                pictures.append(perf_path)
            if tagperf_path.exists():
                pictures.append(tagperf_path)
            if outlier_path.exists():
                pictures.append(outlier_path)
    return pictures

def extract_model_name(output_file: Path) -> str:
    """Extract model identifier from filename."""
    stem = output_file.stem
    parts = stem.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:])
    return stem

def add_title(doc, device, exp_num, configuration):
    doc.add_heading(
        f"Evaluation Prompts — {device} — Experiment {exp_num} — {configuration}",
        level=0,
    )

def add_processing_instruction(doc, num_models):
    p = doc.add_paragraph()
    run = p.add_run("Processing Instructions:")
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    doc.add_paragraph(
        f"This document contains {num_models} model evaluations to process sequentially. "
        f"Please process each evaluation one by one, in order. "
        f"After completing the evaluation for one model, proceed to the next. "
        f"Return your score for each model in the specified JSON format."
    )
    
def add_master_prompt(doc):
    """Add the full evaluation instructions once at the beginning."""
    doc.add_heading("Task Description:", level=1)
    doc.add_paragraph(
        "You are an expert evaluator for natural language generated interpretations for anomaly detection or bad "
        "performance in edge machine learning systems. You will get a source text and the generated interpretation "
        "that was created based on the source text. Additionally there will be a list of points that should be "
        "included in the LLM-generated explanation to make it a good and complete explanation.\n"
        "Your task is to evaluate the quality of the generated interpretations using the G-Eval methodology "
        "on 5 metrics (Evaluation Criteria).\n"
        "Think step-by-step internally before answering.\n"
        "Please make sure you read and understand these instructions carefully. "
        "Please keep this document open while reviewing and refer to it as needed."
    )
    
def add_evaluation_criteria(doc):
    """Add the 5 evaluation criteria."""
    doc.add_heading("Evaluation Criteria:", level=1)
    criteria = [
        (
            "Soundness (Likert Scale: 1-5; Weight: 25%) - the correctness of the information included "
            "in the narrative",
            "The explanation must be technically correct.\n"
            "It should be accurate in the context of federated learning, explainable AI, weather stations "
            "and machine learning.\n"    
            "The explanation should only make claims that are supported by the input data or by domain "
            "knowledge.\n"
            "Assumptions taken based on the diagnostic input should be acknowledged and presented as such. \n"
            "It should not include statements that only sound plausible but are factually wrong.\n"
            "The reasoning must be based on the diagnostic information provided in the prompt.\n"
            "A high score means the explanation is scientifically correct, logically valid and grounded in "
            "the available information. There are no errors or misleading statements in the explanation.\n"
            "A low score means that the narrative includes objective errors, such as reporting an incorrect "
            "contribution.\n",
        ),
        (
            "Fluency (Likert Scale: 1-5; Weight: 10%) - The extent to which the narrative sounds “natural” "
            "or like it was generated by a human peer in conversation.",
            "The explanation should be easy to read and well organized.\n"
            "It should follow a clear structure. Each sentence should connect naturally to the next sentence. \n"
            "The explanation should not be a loose collection of related facts.\n"
            "The language should be clear, simple, and written in good English.\n"
            "The explanation should be understandable for a non-expert end user.\n"
            "Technical terms should be explained in plain language when they are important for understanding "
            "the answer.\n"
            "A high score means the explanation is coherent, readable, and accessible to users without "
            "technical knowledge. It appears to be written by a human expert.\n"
            "A low score means that the narrative is very unnatural or confusingly worded, or directly "
            "repeats the given feature names and values without any narrative flow.\n",
        ),
        (
            "Completeness (Likert Scale: 1-5; Weight: 30%) - The amount of information included in the "
            "narrative",
            "The explanation should answer the question of why the specific weather station is behaving "
            "unusually or is performing bad.\n"
            "The explanation should include actionable recommendations on future steps that are helpful for "
            "the non-technical end user and support the decision making.\n"
            "The explanation should include  the expected points.\n"
            "It should include all important information from the source text that is needed to answer the "
            "questions.\n"
            "Relevant information should be used to generate the interpretation. This includes general model "
            "information or other diagnostic details when they help explain the situation.\n"
            "For Feature Importance Configurations this means incorporating Feature Importance in the answer "
            "if it helps explain the situation.\n"
            "For Performance Configurations this means incorporating Performance in the answer if it helps "
            "explain the situation.\n"
            "For Combination Configurations this means incorporating Feature Importance AND Performance in "
            "the answer if it helps explain the situation.\n"
            "The explanation should not ignore important evidence from the input.\n"
            "The explanation should provide useful and actionable insights.\n"
            "It should help an engineer understand what is happening and decide what to do next.\n"
            "A high score means the explanation covers all relevant points, uses the available evidence well, "
            "and supports practical decision-making by recommending actionable insights. All feature values are "
            "given, and all contributions are described with directions and either exact values or descriptions "
            "(“contributed slightly”).\n"
            "A low score means that some features given were missed entirely, or the direction of their "
            "contributions was not specified.",
        ),
        (
            "Context-Awareness (Likert Scale: 1-5; Weight: 25%) - The degree to which the narrative “explains "
            "the explanation” by providing external context",
            "The explanation should connect claims to the given context.\n"
            "Each important claim should be justified using the source text, the diagnostic data, or relevant "
            "domain knowledge.\n"
            "The explanation should not simply repeat values or sentences from the source text.\n"
            "It should explain what the data means and why it matters.\n"
            "Different pieces of information should be connected to each other.\n"
            "The explanation should lead to a sensible conclusion based on clear reasoning.\n"
            "A high score means the explanation interprets the evidence in context and explains the reasoning "
            "behind its conclusions.  The answer includes further explanations of what may cause a specific "
            "contribution.\n" 
            "A low score means that no context information is provided.\n",
        ),
        (
            "Length (Likert Scale: 1-5; Weight: 10%)",
            "The explanation should be concise.\n"
            "It should include only information that helps answer the users questions.\n"
            "It should avoid unnecessary repetition.\n"
            "It should not restate source text unless the information is needed for the explanation.\n"
            "It should not include irrelevant background information or filler sentences.\n"
            "A high score means the explanation is focused, efficient, and contains no unnecessary content.\n",
        ),
    ]
    for name, description in criteria:
        p = doc.add_paragraph()
        run = p.add_run(f"{name}: ")
        run.bold = True
        p.add_run(description)

def add_evaluation_steps(doc):
    """Add the step-by-step evaluation process."""
    doc.add_heading("Evaluation Steps:", level=1)
    steps = [
        ("Read the source text carefully.",
         "Identify the weather station, the reported anomaly or bad performance issue, the diagnostic "
         "information, and any model-related evidence such as feature importance, performance metrics, "
         "federated learning behavior, explainable AI outputs, or contextual weather-station details."),
        ("Read the list of expected points.",
         "Determine which facts, explanations, feature contributions, performance observations, causes, and "
         "recommendations are required for a complete answer."),
        ("Read the generated interpretation carefully.",
         "Identify the main claims made by the generated explanation, including:\n"
         "* why the station is behaving unusually or performing poorly,\n"
         "* which features or performance indicators it discusses,\n"
         "* whether it gives recommendations,\n"
         "* whether it explains the diagnostic evidence in user-friendly language.\n"
         ),
        ("Evaluate Soundness:",
         "Check whether the generated interpretation is technically correct and grounded in the provided source text. "
         "Verify that it does not invent unsupported facts, misreport feature contributions, reverse contribution "
         "directions, exaggerate evidence, or make scientifically incorrect claims about federated learning, machine "
         "learning, explainable AI, weather stations, or anomaly/performance diagnostics. Penalize unsupported "
         "speculation unless it is clearly marked as an assumption."),
        ("Evaluate Fluency:",
         "Assess whether the explanation reads naturally and coherently. Check whether it is well structured, written in "
         "clear English, and understandable for a non-expert end user. Penalize responses that are fragmented, overly "
         "technical without explanation, repetitive, awkwardly phrased, or merely list feature names and values without "
         "narrative flow."),
        ("Evaluate Completeness:",
         "Compare the generated interpretation against the source text and expected points. Check whether it explains why the "
         "specific station is anomalous or performing badly, includes all important diagnostic evidence, covers all required "
         "feature values and contribution directions, and provides useful actionable recommendations. For feature-importance "
         "cases, verify that relevant feature importance information is included. For performance cases, verify that relevant "
         "performance evidence is included. For combined cases, verify that both are used when relevant."),
        ("Evaluate Context-Awareness:",
         "Determine whether the interpretation explains what the evidence means rather than simply repeating values. Check "
         "whether it connects feature contributions, performance signals, station behavior, weather context, and model behavior "
         "into a meaningful explanation. Reward answers that justify their conclusions using the source text, diagnostic data, "
         "and relevant domain knowledge. Penalize answers that provide no interpretation, no causal or contextual explanation, "
         "or disconnected facts."),
        ("Evaluate Length:",
         "Judge whether the explanation is concise and focused. Check whether it includes only information that helps answer the "
         "users question and avoids filler, irrelevant background, excessive repetition, or unnecessary restatement of the source "
         "text. Penalize answers that are too short to be useful or too long and unfocused."),
        ("Assign a Likert score from 1 to 5 for each metric:",
         "Use the full scale consistently:\n"
         "1 = very poor; major issues or missing required information\n"
         "2 = weak; several important problems\n"
         "3 = acceptable but incomplete or partially flawed\n"
         "4 = good; minor issues only\n"
         "5 = excellent; fully satisfies the criterion\n"
         ),

        ("Apply the metric weights:",
         "Weight the five scores as follows:\n"
         "Soundness: 25%\n"
         "Fluency: 10%\n"
         "Completeness: 30%\n"
         "Context-Awareness: 25%\n"
         "Length: 10%\n"
         ),
        ("Calculate the weighted final score:",
         "Multiply each metric score by its weight and sum the results:\n"
         "Final Score = (Soundness * 0.25) + (Fluency * 0.10) + (Completeness * 0.30) + (Context-Awareness * 0.25) + (Length * 0.10)"),
        ("Final judgment:",
         "Summarize the overall quality of the interpretation, noting the strongest and weakest aspects."),
    ]
    for i, (title, body) in enumerate(steps, start=1):
        p = doc.add_paragraph()
        run = p.add_run(f"{i}. {title}")
        run.bold = True
        doc.add_paragraph(body)
        
def add_output_instructions(doc):
    """Add the JSON output format specification."""
    doc.add_heading("Output Instructions:", level=1)
    doc.add_paragraph(
        "At the beginning, add what interpretation is being evaluated "
        "(Experiment_Device_Configuration_Model). Return the score for each metric and an overall "
        "score using the average. At the end, add a short statement for your score reasoning. "
        "Return your answer ONLY in the following JSON format:"
    )
    json_format = (
        '{\n'
        '  "interpretation": "ExperimentX_DeviceX_Configuration_ModelX",\n'
        '  "soundness": X,\n'
        '  "fluency": X,\n'
        '  "completeness": X,\n'
        '  "context-awareness": X,\n'
        '  "length": X,\n'
        '  "overall_score": X,\n'
        '  "reasoning": "Short statement explaining your score reasoning"\n'
        '}'
    )
    p = doc.add_paragraph(json_format)
    #p.style = doc.styles.get_style_by_name("No Spacing")
    run = p.runs[0]
    run.font.name = "Courier New"
    run.font.size = Pt(10)

def add_model_evaluation_section(doc, exp_num, device, configuration, model_name,
                                  source_text, expected_explanation, llm_output, image_paths=None):
    """Add a single model evaluation section with source text, LLM output, and optional image."""
    interpretation_id = f"Experiment{exp_num}_{device}_{configuration}_{model_name}"
    doc.add_heading(f"Evaluation: {interpretation_id}", level=1)
    doc.add_heading("Ignore any previous conversation.", level=2)
    doc.add_paragraph("Please evaluate the following interpretation according to the criteria and steps outlined above.")
    doc.add_heading("Source Text:", level=2)
    doc.add_paragraph(source_text)
    doc.add_heading("Expected Explanation:", level=2)
    doc.add_paragraph(expected_explanation)
    doc.add_heading("LLM-generated explanation:", level=2)
    doc.add_paragraph(llm_output)
    
    if image_paths and any(p.exists() for p in image_paths):
        doc.add_paragraph("")
        for idx, img_path in enumerate(image_paths, start=1):
            if img_path.exists():
                p = doc.add_paragraph()
                run = p.add_run(f"Figure {idx}: {img_path.name}")
                run.bold = True
                run.font.size = Pt(11)
                picture_type = "feature importance" if "feature_importance" in img_path.name else "outliers" if "outliers" in img_path.name else "performance"
                context_p = doc.add_paragraph()
                context_run = context_p.add_run(
                    f"Refer to Figure {idx} above as part of the evaluation for model '{model_name}'. "
                    f"This image shows {picture_type} data for this device. "
                    f"Use the visual patterns shown here to assess whether the LLM-generated explanation "
                    f"accurately incorporates and interprets this visual evidence. "
                    f"Only refer to patterns that are clearly visible in the image."
                )
                context_run.italic = True
                context_run.font.size = Pt(10)
                doc.add_picture(str(img_path), width=Inches(5.5))
                doc.add_paragraph("")
    doc.add_heading(
        "Please evaluate this interpretation according to the criteria above "
        "and return your score in the specified JSON format.",
        level=2,
    )
    doc.add_page_break()

def get_num_models(exp_num: int) -> int:
    """Return the number of models to process for a given experiment."""
    return MODELS_EXP_1_2_3 if exp_num <= 3 else MODELS_EXP_4

def build_document(exp_num: int, device: str, input_folder: Path,
                   experiment_folder: Path, configuration: str) -> Document:
    """Build a complete DOCX document for one device/experiment/configuration."""
    doc = Document()
    num_models = get_num_models(exp_num)
    # Title and processing instructions
    add_title(doc, device, exp_num, configuration)
    add_processing_instruction(doc, num_models)
    doc.add_paragraph("")
    # Master prompt (full instructions once)
    add_master_prompt(doc)
    add_evaluation_criteria(doc)
    add_evaluation_steps(doc)
    add_output_instructions(doc)
    doc.add_page_break()
    # Get input source text
    device_id = get_device_id(device)
    input_file = find_input_file(input_folder, device, configuration)
    source_text = read_input_file(input_file)
    expected_explanation = read_expected_explanation(device)
    # Find experiment output files and limit to num_models
    output_files = find_experiment_files(experiment_folder, device, configuration)
    output_files = output_files[:num_models]
    # Find image if applicable (Exp 4 only)
    image_paths = []
    if exp_num >= 4:
        image_paths = find_device_pictures(exp_num, device_id, configuration)
    for output_file in output_files:
        exp_data = read_experiment_file(output_file)
        model_name = extract_model_name(output_file)
        llm_output = exp_data.get("llm_output", "[No LLM output found]")
        add_model_evaluation_section(
            doc=doc,
            exp_num=exp_num,
            device=device,
            configuration=configuration,
            model_name=model_name,
            source_text=source_text,
            expected_explanation=expected_explanation,
            llm_output=llm_output,
            image_paths=image_paths,
        )
    return doc

def save_document(doc: Document, output_path: Path) -> Path:
    """Save DOCX document and return the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Processing {NUM_EXPERIMENTS} experiments...")
    print()
    documents_created = 0
    for exp_num in range(1, NUM_EXPERIMENTS + 1):
        input_folder = BASE_DIR / f"Input_Folder{exp_num}"
        experiment_folder = BASE_DIR / f"Experiment{exp_num}"
        if not input_folder.exists():
            print(f"  [SKIP] Input_Folder{exp_num} not found")
            continue
        if not experiment_folder.exists():
            print(f"  [SKIP] Experiment{exp_num} not found")
            continue
        print(f"=== Experiment {exp_num} ===")
        for device_dir in sorted(input_folder.iterdir()):
            if not device_dir.is_dir() or not device_dir.name.startswith("Device_"):
                continue
            device = device_dir.name
            for configuration in CONFIGURATIONS:
                try:
                    doc = build_document(exp_num, device, input_folder, experiment_folder, configuration)
                    save_path = (
                        OUTPUT_DIR
                        / device
                        / f"Experiment{exp_num}"
                        / f"{device}_Experiment{exp_num}_{configuration}.docx"
                    )
                    save_document(doc, save_path)
                    documents_created += 1
                    print(f"  [OK] {save_path.relative_to(BASE_DIR)}")
                except FileNotFoundError as e:
                    print(f"  [SKIP] {device}/{configuration}: {e}")
                except Exception as e:
                    print(f"  [ERROR] {device}/{configuration}: {e}")
        print()
    print(f"Done. Created {documents_created} documents in {OUTPUT_DIR.relative_to(BASE_DIR)}")

if __name__ == "__main__":
    main()