"""Statistical Comparison of Human and GPT Evaluations"""

import pandas as pd
import numpy as np
from scipy import stats

df = pd.read_excel("Evaluation.xlsx", sheet_name="Statistical_Analysis")

df.columns = df.columns.str.strip()
df["g_eval"] = pd.to_numeric(df["g_eval"], errors="coerce")
df["human_eval"] = pd.to_numeric(df["human_eval"], errors="coerce")

g_eval = df["g_eval"]
human_eval = df["human_eval"]

#Tost test
def paired_tost(x, y, low_eqbound, high_eqbound, alpha=0.05):
    diff = y - x
    n = len(diff)
    mean_diff = np.mean(diff)
    sd_diff = np.std(diff, ddof=1)
    se_diff = sd_diff / np.sqrt(n)
    df = n - 1

    # Test 1: mean difference > lower bound
    t1 = (mean_diff - low_eqbound) / se_diff
    p1 = 1 - stats.t.cdf(t1, df)

    # Test 2: mean difference < upper bound
    t2 = (mean_diff - high_eqbound) / se_diff
    p2 = stats.t.cdf(t2, df)

    # 90% confidence interval for equivalence testing at alpha = .05
    ci_low, ci_high = stats.t.interval(
        1 - 2 * alpha,
        df,
        loc=mean_diff,
        scale=se_diff
    )

    equivalent = (p1 < alpha) and (p2 < alpha)

    return {
        "mean_difference": mean_diff,
        "lower_equivalence_bound": low_eqbound,
        "upper_equivalence_bound": high_eqbound,
        "t_lower": t1,
        "p_lower": p1,
        "t_upper": t2,
        "p_upper": p2,
        "ci_90_low": ci_low,
        "ci_90_high": ci_high,
        "equivalent": equivalent
    }

equivalence_margin = 0.5

tost_results = paired_tost(
    human_eval,
    g_eval,
    low_eqbound=-equivalence_margin,
    high_eqbound=equivalence_margin
)

print("\nTOST equivalence test:")
for key, value in tost_results.items():
    print(f"{key}: {value}")
