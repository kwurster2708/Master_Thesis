import pandas as pd
import numpy as np

from scipy import stats
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multitest import multipletests

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

# ============================================================
# EFFECT OF INPUT CONFIGURATION
# FI vs P vs FI + P
# ============================================================

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
    
# ============================================================
# EFFECT OF INPUT CONFIGURATION PER EXPERIMENT
# ============================================================

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

# ============================================================
# PAIRWISE INPUT COMPARISONS
# ============================================================

def pairwise_input_tests(data, label):
    inputs = data["input"].dropna().unique()
    results = []

    for i in range(len(inputs)):
        for j in range(i + 1, len(inputs)):
            a = inputs[i]
            b = inputs[j]

            group_a = data[data["input"] == a]["g_eval"]
            group_b = data[data["input"] == b]["g_eval"]

            t, p = stats.ttest_ind(group_a, group_b, equal_var=False)

            results.append({
                "analysis": label,
                "comparison": f"{a} vs {b}",
                "mean_a": group_a.mean(),
                "mean_b": group_b.mean(),
                "difference": group_b.mean() - group_a.mean(),
                "p_uncorrected": p
            })

    results = pd.DataFrame(results)

    if len(results) > 0:
        results["p_holm"] = multipletests(
            results["p_uncorrected"],
            method="holm"
        )[1]

    return results


print("\nOverall pairwise input comparisons:")
print(pairwise_input_tests(df, "Overall"))

for exp in df["experiment"].cat.categories:
    temp = df[df["experiment"] == exp]
    print(f"\nPairwise input comparisons for {exp}:")
    print(pairwise_input_tests(temp, exp))
    
# Example only - adjust this to your actual thesis setup
representation_map = {
    "Experiment 1": "numerical",
    "Experiment 2": "numerical + seed",
    "Experiment 3": "textual",
    "Experiment 4": "visual"
}

df["representation_type"] = df["experiment"].map(representation_map)

# ============================================================
# EFFECT OF REPRESENTATION TYPE / EXPERIMENT
# ============================================================

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
    
# ============================================================
# PAIRWISE EXPERIMENT COMPARISONS
# ============================================================

experiments = df["experiment"].dropna().unique()
results = []

for i in range(len(experiments)):
    for j in range(i + 1, len(experiments)):
        a = experiments[i]
        b = experiments[j]

        group_a = df[df["experiment"] == a]["g_eval"]
        group_b = df[df["experiment"] == b]["g_eval"]

        t, p = stats.ttest_ind(group_a, group_b, equal_var=False)

        results.append({
            "comparison": f"{a} vs {b}",
            "mean_a": group_a.mean(),
            "mean_b": group_b.mean(),
            "difference": group_b.mean() - group_a.mean(),
            "p_uncorrected": p
        })

experiment_posthoc = pd.DataFrame(results)

experiment_posthoc["p_holm"] = multipletests(
    experiment_posthoc["p_uncorrected"],
    method="holm"
)[1]

print("\nPairwise experiment comparisons:")
print(experiment_posthoc.sort_values("p_holm"))

# ============================================================
# EFFECT OF MODEL OVERALL
# ============================================================

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
    
# ============================================================
# EFFECT OF MODEL PER EXPERIMENT
# ============================================================

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
        
# ============================================================
# PAIRWISE MODEL COMPARISONS PER EXPERIMENT
# ============================================================

def pairwise_model_tests(data, label):
    models = data["model"].dropna().unique()
    results = []

    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            a = models[i]
            b = models[j]

            group_a = data[data["model"] == a]["g_eval"]
            group_b = data[data["model"] == b]["g_eval"]

            t, p = stats.ttest_ind(group_a, group_b, equal_var=False)

            results.append({
                "analysis": label,
                "comparison": f"{a} vs {b}",
                "mean_a": group_a.mean(),
                "mean_b": group_b.mean(),
                "difference": group_b.mean() - group_a.mean(),
                "p_uncorrected": p
            })

    results = pd.DataFrame(results)

    if len(results) > 0:
        results["p_holm"] = multipletests(
            results["p_uncorrected"],
            method="holm"
        )[1]

    return results


for exp in df["experiment"].cat.categories:
    temp = df[df["experiment"] == exp]
    print(f"\nPairwise model comparisons for {exp}:")
    print(pairwise_model_tests(temp, exp))
    
# ============================================================
# CORRELATION: INPUT LENGTH AND DURATION
# ============================================================

for variable in ["input_length_tokens", "duration_seconds"]:
    pearson_r, pearson_p = stats.pearsonr(df[variable], df["g_eval"])
    spearman_rho, spearman_p = stats.spearmanr(df[variable], df["g_eval"])

    print(f"\nCorrelation between {variable} and G-Eval:")
    print(f"Pearson r = {pearson_r:.3f}, p = {pearson_p:.4f}")
    print(f"Spearman rho = {spearman_rho:.3f}, p = {spearman_p:.4f}")
    
# ============================================================
# CORRELATION PER EXPERIMENT
# ============================================================

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
        
# ============================================================
# SIMPLE REGRESSION WITH ALL PREDICTORS
# ============================================================

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

# ============================================================
# FINAL SUMMARY TABLE
# ============================================================

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

summary_table.to_csv("final_summary_table.csv", index=False)

# ============================================================
# FINAL EXPERIMENT COMPARISON TABLE
# ============================================================

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

experiment_summary.to_csv("final_experiment_comparison.csv", index=False)