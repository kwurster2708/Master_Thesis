import pandas as pd
import pingouin as pg
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# -----------------------------
# Load data
# -----------------------------
df = pd.read_excel("Evaluation_Schema.xlsx", sheet_name="Statistical_Analysis")

df.columns = df.columns.str.strip()
df["station"] = df["station"].astype(str)
df["model"] = df["model"].astype(str)
df["experiment"] = df["experiment"].astype(str)
df["input"] = df["input"].astype(str)
df["human_eval"] = pd.to_numeric(df["human_eval"], errors="coerce")
df = df.dropna(subset=["human_eval"])

# Output folder
out_dir = Path("anova_outputs")
out_dir.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid")

# -----------------------------
# Descriptive overview plot
# -----------------------------
plt.figure(figsize=(10, 6))
sns.barplot(
    data=df,
    x="experiment",
    y="human_eval",
    hue="model",
    errorbar="se"
)
plt.title("Mean Human Evaluation Scores by Experiment and Model")
plt.ylabel("Mean Score")
plt.xlabel("Experiment")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig(out_dir / "overview_experiment_model_scores.png", dpi=300)
plt.show()

# -----------------------------
# ANOVA per experiment
# -----------------------------
all_anova_results = []
all_posthoc_results = []

for exp in df["experiment"].unique():

    print("\n" + "="*80)
    print(f"ANOVA for {exp}")
    print("="*80)

    exp_df = df[df["experiment"] == exp].copy()

    expected_conditions = (
        exp_df["model"].nunique() * exp_df["input"].nunique()
    )

    valid_datasets = (
        exp_df.groupby("station")
        .size()
        .loc[lambda x: x == expected_conditions]
        .index
    )

    exp_df = exp_df[exp_df["station"].isin(valid_datasets)]

    print(f"Datasets included: {list(valid_datasets)}")
    print(f"Number of observations: {len(exp_df)}")

    if exp_df["station"].nunique() < 2:
        print("Not enough repeated datasets for ANOVA. Skipping.")
        continue

    # -----------------------------
    # Plot 1: Model x Input interaction
    # -----------------------------
    plt.figure(figsize=(8, 5))
    sns.pointplot(
        data=exp_df,
        x="input",
        y="human_eval",
        hue="model",
        errorbar="se",
        dodge=True,
        markers="o",
        linestyles="-"
    )
    plt.title(f"Interaction Plot: Model × Input — {exp}")
    plt.ylabel("Mean Human Evaluation Score")
    plt.xlabel("Input Configuration")
    plt.ylim(1, 5)
    plt.tight_layout()
    plt.savefig(out_dir / f"{exp}_interaction_model_input.png", dpi=300)
    plt.show()

    # -----------------------------
    # Plot 2: Barplot by Model and Input
    # -----------------------------
    plt.figure(figsize=(8, 5))
    sns.barplot(
        data=exp_df,
        x="model",
        y="human_eval",
        hue="input",
        errorbar="se"
    )
    plt.title(f"Mean Scores by Model and Input — {exp}")
    plt.ylabel("Mean Human Evaluation Score")
    plt.xlabel("Model")
    plt.ylim(1, 5)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / f"{exp}_barplot_model_input.png", dpi=300)
    plt.show()

    # -----------------------------
    # Plot 3: Heatmap of means
    # -----------------------------
    heatmap_data = exp_df.pivot_table(
        index="model",
        columns="input",
        values="human_eval",
        aggfunc="mean"
    )

    plt.figure(figsize=(6, 4))
    sns.heatmap(
        heatmap_data,
        annot=True,
        fmt=".2f",
        cmap="Blues",
        vmin=1,
        vmax=5
    )
    plt.title(f"Mean Score Heatmap — {exp}")
    plt.tight_layout()
    plt.savefig(out_dir / f"{exp}_heatmap_model_input.png", dpi=300)
    plt.show()

    # -----------------------------
    # Plot 4: Distribution / spread
    # -----------------------------
    plt.figure(figsize=(8, 5))
    sns.boxplot(
        data=exp_df,
        x="model",
        y="human_eval",
        hue="input"
    )
    plt.title(f"Score Distribution by Model and Input — {exp}")
    plt.ylabel("Human Evaluation Score")
    plt.xlabel("Model")
    plt.ylim(1, 5)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / f"{exp}_boxplot_model_input.png", dpi=300)
    plt.show()

    # -----------------------------
    # Two-way repeated-measures ANOVA
    # -----------------------------
    aov = pg.rm_anova(
        data=exp_df,
        dv="human_eval",
        within=["model", "input"],
        subject="station",
        detailed=True
    )

    aov["experiment"] = exp
    all_anova_results.append(aov)

    print("\nRepeated Measures ANOVA")
    print(aov)

    # -----------------------------
    # Post-hoc: Model
    # -----------------------------
    posthoc_model = pg.pairwise_tests(
        data=exp_df,
        dv="human_eval",
        within="model",
        subject="station",
        padjust="bonf"
    )
    posthoc_model["experiment"] = exp
    posthoc_model["Posthoc_Type"] = "Model"
    all_posthoc_results.append(posthoc_model)

    print("\nPost-hoc: Model")
    print(posthoc_model)

    # -----------------------------
    # Post-hoc: Input
    # -----------------------------
    posthoc_input = pg.pairwise_tests(
        data=exp_df,
        dv="human_eval",
        within="input",
        subject="station",
        padjust="bonf"
    )
    posthoc_input["experiment"] = exp
    posthoc_input["Posthoc_Type"] = "Input"
    all_posthoc_results.append(posthoc_input)

    print("\nPost-hoc: Input")
    print(posthoc_input)

    # -----------------------------
    # Interaction post-hoc:
    # Model differences within each input
    # -----------------------------
    for input_type in exp_df["input"].unique():

        subset = exp_df[exp_df["input"] == input_type]

        ph = pg.pairwise_tests(
            data=subset,
            dv="human_eval",
            within="model",
            subject="station",
            padjust="bonf"
        )

        ph["experiment"] = exp
        ph["Posthoc_Type"] = f"Model within {input_type}"
        all_posthoc_results.append(ph)

        print(f"\nPost-hoc: Model within Input = {input_type}")
        print(ph)
        
# ============================================================
# SECONDARY ANALYSIS:
# Experiment × Input ANOVA
# Averaged across models
# ============================================================

print("\n" + "="*80)
print("SECONDARY ANOVA: Experiment × Input")
print("="*80)

# Average across models first
exp_input_df = (
    df.groupby(["station", "experiment", "input"], as_index=False)
    ["human_eval"]
    .mean()
)

# Keep only datasets that have all Experiment × Input combinations
expected_conditions = (
    exp_input_df["experiment"].nunique() * exp_input_df["input"].nunique()
)

valid_datasets = (
    exp_input_df.groupby("station")
    .size()
    .loc[lambda x: x == expected_conditions]
    .index
)

exp_input_df = exp_input_df[exp_input_df["station"].isin(valid_datasets)]

print(f"Datasets included: {list(valid_datasets)}")
print(f"Number of observations: {len(exp_input_df)}")

if exp_input_df["station"].nunique() >= 2:

    # -----------------------------
    # Experiment × Input ANOVA
    # -----------------------------
    exp_input_aov = pg.rm_anova(
        data=exp_input_df,
        dv="human_eval",
        within=["experiment", "input"],
        subject="station",
        detailed=True
    )

    print("\nRepeated Measures ANOVA: Experiment × Input")
    print(exp_input_aov)

    # -----------------------------
    # Post-hoc: Experiment
    # -----------------------------
    exp_posthoc = pg.pairwise_tests(
        data=exp_input_df,
        dv="human_eval",
        within="experiment",
        subject="station",
        padjust="bonf"
    )

    print("\nPost-hoc: Experiment")
    print(exp_posthoc)

    # -----------------------------
    # Post-hoc: Input
    # -----------------------------
    input_posthoc_global = pg.pairwise_tests(
        data=exp_input_df,
        dv="human_eval",
        within="input",
        subject="station",
        padjust="bonf"
    )

    print("\nPost-hoc: Input")
    print(input_posthoc_global)

    # -----------------------------
    # Plot 1: Experiment × Input interaction
    # -----------------------------
    plt.figure(figsize=(9, 5))
    sns.pointplot(
        data=exp_input_df,
        x="experiment",
        y="human_eval",
        hue="input",
        errorbar="se",
        dodge=True,
        markers="o",
        linestyles="-"
    )
    plt.title("Interaction Plot: Experiment × Input Configuration")
    plt.ylabel("Mean Human Evaluation Score")
    plt.xlabel("Experiment")
    plt.ylim(1, 5)
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "secondary_experiment_input_interaction.png", dpi=300)
    plt.show()

    # -----------------------------
    # Plot 2: Heatmap Experiment × Input
    # -----------------------------
    heatmap_exp_input = exp_input_df.pivot_table(
        index="experiment",
        columns="input",
        values="human_eval",
        aggfunc="mean"
    )

    plt.figure(figsize=(7, 4))
    sns.heatmap(
        heatmap_exp_input,
        annot=True,
        fmt=".2f",
        cmap="Blues",
        vmin=1,
        vmax=5
    )
    plt.title("Mean Scores: Experiment × Input")
    plt.tight_layout()
    plt.savefig(out_dir / "secondary_experiment_input_heatmap.png", dpi=300)
    plt.show()

    # -----------------------------
    # Save to same Excel file
    # -----------------------------
    with pd.ExcelWriter(
        out_dir / "anova_results.xlsx",
        mode="a",
        engine="openpyxl",
        if_sheet_exists="replace"
    ) as writer:
        exp_input_aov.to_excel(
            writer,
            sheet_name="Exp_Input_ANOVA",
            index=False
        )
        exp_posthoc.to_excel(
            writer,
            sheet_name="Exp_Posthoc",
            index=False
        )
        input_posthoc_global.to_excel(
            writer,
            sheet_name="Global_Input_Posthoc",
            index=False
        )

else:
    print("Not enough complete datasets for Experiment × Input ANOVA.")

# -----------------------------
# Save results to Excel
# -----------------------------
anova_results = pd.concat(all_anova_results, ignore_index=True)
posthoc_results = pd.concat(all_posthoc_results, ignore_index=True)

with pd.ExcelWriter(out_dir / "anova_results.xlsx") as writer:
    anova_results.to_excel(writer, sheet_name="ANOVA", index=False)
    posthoc_results.to_excel(writer, sheet_name="Posthoc", index=False)

print("\nSaved results and figures in:", out_dir)