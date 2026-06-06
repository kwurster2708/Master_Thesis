"""Statistical analysis for thesis experiments.
This script performs the following analyses:
1. Descriptive statistics by input, experiment, and model
2. ANOVA to test the effect of input configuration on G-Eval
3. ANOVA to test the effect of experiment / representation type on G-Eval
4. ANOVA to test the effect of model on G-Eval
8. Correlation analyses between input length, duration, and G-Eval
"""
import pandas as pd
import numpy as np

from scipy import stats
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm

df = pd.read_excel("Evaluation.xlsx", sheet_name="Statistical_Analysis")

# Clean column names
df.columns = df.columns.str.strip()

# Remove human_eval because it should be ignored
df = df.drop(columns=["human_eval"], errors="ignore")

# Convert decimal commas to decimal points
for col in ["duration_seconds", "g_eval", "input_length_tokens"]:
    df[col] = (
        df[col]
        .astype(str)
        .str.replace(",", ".", regex=False)
    )
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Convert categorical variables
df["station"] = df["station"].astype("category")
df["model"] = df["model"].astype("category")
df["experiment"] = df["experiment"].astype("category")
df["input"] = df["input"].astype("category")

# Remove incomplete rows
df = df.dropna(subset=[
    "station",
    "model",
    "experiment",
    "input",
    "input_length_tokens",
    "duration_seconds",
    "g_eval"
])

def describe_group(group_cols):
    return (
        df.groupby(group_cols, observed=True)["g_eval"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )

print("\nMean G-Eval by input configuration:")
print(describe_group(["input"]))

print("\nMean G-Eval by experiment:")
print(describe_group(["experiment"]))

print("\nMean G-Eval by model:")
print(describe_group(["model"]))

print("\nMean G-Eval by experiment and input:")
print(describe_group(["experiment", "input"]))

print("\nMean G-Eval by experiment and model:")
print(describe_group(["experiment", "model"]))

print("\nMean G-Eval by experiment, model and input:")
best_combinations = describe_group(["experiment", "model", "input"])
print(best_combinations)

# Effect of input configuration
model_input = smf.ols(
    "g_eval ~ C(input) + C(station)",
    data=df
).fit()

anova_input = anova_lm(model_input, typ=2)

print("\nANOVA: Effect of input configuration")
print(anova_input)

p_input = anova_input.loc["C(input)", "PR(>F)"]

if p_input < 0.05:
    print("Input configuration has a statistically significant effect on G-Eval.")
else:
    print("Input configuration does not have a statistically significant effect on G-Eval.")
    
# Effect of input configuration per experiment
for exp in df["experiment"].cat.categories:
    temp = df[df["experiment"] == exp]

    if len(temp) == 0:
        continue

    print("\n================================================")
    print(exp)
    print("================================================")

    print("\nDescriptive means by input:")
    print(describe_group(["experiment", "input"]).query("experiment == @exp"))

    model = smf.ols(
        "g_eval ~ C(input) + C(station)",
        data=temp
    ).fit()

    anova = anova_lm(model, typ=2)

    print("\nANOVA:")
    print(anova)

    p = anova.loc["C(input)", "PR(>F)"]

    if p < 0.05:
        print("Result: Input configuration has a significant effect in this experiment.")
    else:
        print("Result: Input configuration has no significant effect in this experiment.")

    
representation_map = {
    "Experiment 1": "numerical",
    "Experiment 2": "numerical + reference",
    "Experiment 3": "textual + reference",
    "Experiment 4": "visual + reference"
}

df["representation_type"] = df["experiment"].map(representation_map)

# Effect of experiment / representation type
model_experiment = smf.ols(
    "g_eval ~ C(experiment) + C(station)",
    data=df
).fit()

anova_experiment = anova_lm(model_experiment, typ=2)

print("\nANOVA: Effect of experiment / representation type")
print(anova_experiment)

p_exp = anova_experiment.loc["C(experiment)", "PR(>F)"]

if p_exp < 0.05:
    print("Experiment / representation type has a statistically significant effect on G-Eval.")
else:
    print("Experiment / representation type does not have a statistically significant effect on G-Eval.")
    

# Effect of model
model_model = smf.ols(
    "g_eval ~ C(model) + C(station)",
    data=df
).fit()

anova_model = anova_lm(model_model, typ=2)

print("\nANOVA: Effect of model")
print(anova_model)

p_model = anova_model.loc["C(model)", "PR(>F)"]

if p_model < 0.05:
    print("Model has a statistically significant effect on G-Eval.")
else:
    print("Model does not have a statistically significant effect on G-Eval.")
    
# Effect of model per experiment
for exp in df["experiment"].cat.categories:
    temp = df[df["experiment"] == exp]

    if len(temp["model"].unique()) < 2:
        continue

    print("\n================================================")
    print(exp)
    print("================================================")

    print("\nDescriptive means by model:")
    print(
        temp.groupby("model", observed=True)["g_eval"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )

    model = smf.ols(
        "g_eval ~ C(model) + C(station)",
        data=temp
    ).fit()

    anova = anova_lm(model, typ=2)

    print("\nANOVA:")
    print(anova)

    p = anova.loc["C(model)", "PR(>F)"]

    if p < 0.05:
        print("Result: Model has a significant effect in this experiment.")
    else:
        print("Result: Model has no significant effect in this experiment.")
        
    
# Correlation input length and duration
for variable in ["input_length_tokens", "duration_seconds"]:
    pearson_r, pearson_p = stats.pearsonr(df[variable], df["g_eval"])
    spearman_rho, spearman_p = stats.spearmanr(df[variable], df["g_eval"])

    print(f"\nCorrelation between {variable} and G-Eval:")
    print(f"Pearson r = {pearson_r:.3f}, p = {pearson_p:.4f}")
    print(f"Spearman rho = {spearman_rho:.3f}, p = {spearman_p:.4f}")
    
# Correlation per experiment
for exp in df["experiment"].cat.categories:
    temp = df[df["experiment"] == exp]

    print("\n================================================")
    print(exp)
    print("================================================")

    for variable in ["input_length_tokens", "duration_seconds"]:
        pearson_r, pearson_p = stats.pearsonr(temp[variable], temp["g_eval"])
        spearman_rho, spearman_p = stats.spearmanr(temp[variable], temp["g_eval"])

        print(f"\n{variable}:")
        print(f"Pearson r = {pearson_r:.3f}, p = {pearson_p:.4f}")
        print(f"Spearman rho = {spearman_rho:.3f}, p = {spearman_p:.4f}")
        
# OLS Regression with all variables
full_model = smf.ols(
    """
    g_eval ~ C(experiment)
           + C(input)
           + C(model)
           + input_length_tokens
           + duration_seconds
           + C(station)
    """,
    data=df
).fit()

full_anova = anova_lm(full_model, typ=2)

print("\nFull model ANOVA:")
print(full_anova)

print("\nFull model coefficients:")
print(full_model.summary())

# Final Summary Table
summary_rows = []

# Input effect
summary_rows.append({
    "Research question": "Does FI, P, or FI + P affect quality?",
    "Tested variable": "input",
    "p-value": anova_input.loc["C(input)", "PR(>F)"],
    "Significant": anova_input.loc["C(input)", "PR(>F)"] < 0.05,
    "Best group descriptively": (
        df.groupby("input", observed=True)["g_eval"]
        .mean()
        .idxmax()
    ),
    "Highest mean G-Eval": (
        df.groupby("input", observed=True)["g_eval"]
        .mean()
        .max()
    )
})

# Experiment / representation effect
summary_rows.append({
    "Research question": "Does representation type / experiment affect quality?",
    "Tested variable": "experiment",
    "p-value": anova_experiment.loc["C(experiment)", "PR(>F)"],
    "Significant": anova_experiment.loc["C(experiment)", "PR(>F)"] < 0.05,
    "Best group descriptively": (
        df.groupby("experiment", observed=True)["g_eval"]
        .mean()
        .idxmax()
    ),
    "Highest mean G-Eval": (
        df.groupby("experiment", observed=True)["g_eval"]
        .mean()
        .max()
    )
})

# Model effect
summary_rows.append({
    "Research question": "Does model affect quality?",
    "Tested variable": "model",
    "p-value": anova_model.loc["C(model)", "PR(>F)"],
    "Significant": anova_model.loc["C(model)", "PR(>F)"] < 0.05,
    "Best group descriptively": (
        df.groupby("model", observed=True)["g_eval"]
        .mean()
        .idxmax()
    ),
    "Highest mean G-Eval": (
        df.groupby("model", observed=True)["g_eval"]
        .mean()
        .max()
    )
})

# Input length
input_length_r, input_length_p = stats.spearmanr(
    df["input_length_tokens"],
    df["g_eval"]
)

summary_rows.append({
    "Research question": "Does input length affect quality?",
    "Tested variable": "input_length_tokens",
    "p-value": input_length_p,
    "Significant": input_length_p < 0.05,
    "Best group descriptively": "Positive effect" if input_length_r > 0 else "Negative effect",
    "Highest mean G-Eval": np.nan
})

# Duration
duration_r, duration_p = stats.spearmanr(
    df["duration_seconds"],
    df["g_eval"]
)

summary_rows.append({
    "Research question": "Does duration affect quality?",
    "Tested variable": "duration_seconds",
    "p-value": duration_p,
    "Significant": duration_p < 0.05,
    "Best group descriptively": "Positive effect" if duration_r > 0 else "Negative effect",
    "Highest mean G-Eval": np.nan
})

summary_table = pd.DataFrame(summary_rows)

print("\nFINAL SUMMARY TABLE")
print(summary_table)

# Final experiment comparison table
experiment_summary = (
    df.groupby("experiment", observed=True)
    .agg(
        mean_g_eval=("g_eval", "mean"),
        sd_g_eval=("g_eval", "std"),
        n=("g_eval", "count"),
        mean_input_length=("input_length_tokens", "mean"),
        mean_duration=("duration_seconds", "mean")
    )
    .reset_index()
    .sort_values("mean_g_eval", ascending=False)
)

print("\nFINAL EXPERIMENT COMPARISON")
print(experiment_summary)