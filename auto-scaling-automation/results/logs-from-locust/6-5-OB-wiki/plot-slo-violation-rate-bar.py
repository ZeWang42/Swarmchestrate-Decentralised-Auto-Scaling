import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa80_stats.csv"],
    "DAS": ["das_stats.csv"],
    "Queue-DAS": ["queue_das_stats.csv"],
}
#files = {
#    "HPA-80": ["hpa80_stats_1.csv", "hpa80_stats_2.csv"],
#    "DAS": ["das_stats_1.csv", "das_stats_2.csv"],
#    "Queue-DAS": ["queue_das_stats_1.csv", "queue_das_stats_2.csv"],
#}

colors = ["tab:blue", "tab:orange", "tab:green"]

SLO = 500  # ms

percentile_map = {
    "50%": 0.50,
    "66%": 0.66,
    "75%": 0.75,
    "80%": 0.80,
    "90%": 0.90,
    "95%": 0.95,
    "98%": 0.98,
    "99%": 0.99,
    "99.90%": 0.999,
    "99.99%": 0.9999,
    "100%": 1.0,
}

def estimate_violation(lat, prob, slo):
    for i in range(len(lat) - 1):
        if lat[i] <= slo <= lat[i + 1]:
            # linear interpolation
            p = prob[i] + (prob[i + 1] - prob[i]) * (slo - lat[i]) / (lat[i + 1] - lat[i])
            return 1 - p

    # edge cases
    if slo < lat[0]:
        return 1 - prob[0]
    if slo > lat[-1]:
        return 0.0

results = []

for scheme in files.keys():
    violations = []

    for file in files[scheme]:
        df = pd.read_csv(DATA_DIR / file)
        row = df.iloc[-1]

        lat = []
        prob = []

        for col, p in percentile_map.items():
            if col in df.columns and pd.notna(row[col]):
                lat.append(row[col])
                prob.append(p)

        lat, prob = zip(*sorted(zip(lat, prob)))

        violation = estimate_violation(lat, prob, SLO)
        violations.append(violation * 100)

    results.append({
        "Scheme": scheme,
        "ViolationRate": sum(violations) / len(violations)
    })

final = pd.DataFrame(results)
final = final.set_index("Scheme").loc[files.keys()].reset_index()
# -----------------------------------
# PLOT
# -----------------------------------
plt.figure(figsize=(7, 5))

bars = plt.bar(
    final["Scheme"],
    final["ViolationRate"],
    color=colors
)

# Limit y-axis to 0–5%
plt.ylim(0, 10)

for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        min(height + 0.1, 4.8),   # keep label inside axis
        f"{height:.2f}%",
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.xlabel("Scheme")
plt.ylabel("SLO violation rate (%)")
plt.title(f"SLO violations (> {SLO} ms)")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("slo_violation_bar.png", dpi=300)
plt.show()
