import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Enforce order: HPA → DAS → Queue
files = {
    "HPA-80": ["hpa-80.csv"],
    "Custom-DAS-2": ["custom-das-2.csv"],

    "DAS": ["das.csv"],
#
#    "Custom-DAS-3": ["custom-das-3.csv"],
#    "Custom-DAS-1": ["custom-das.csv"],
}
colors = ["tab:blue", "tab:orange", "tab:green"]

all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df[df["Scope"] == "deployment"].copy()

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# -------------------------------
# STEP 1: per-second aggregation
# -------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["Pods"]
    .sum()
)

# -------------------------------
# STEP 2: convert to minute bins
# -------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -------------------------------
# STEP 3: average per second within each minute
# -------------------------------
per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Minute"], as_index=False)["Pods"]
    .mean()
)

# -------------------------------
# STEP 4: average across runs
# -------------------------------
final = (
    per_minute
    .groupby(["Scheme", "Minute"], as_index=False)["Pods"]
    .mean()
)

# -------------------------------
# PLOT
# -------------------------------
plt.figure(figsize=(10, 5))

for scheme, color in zip(files.keys(), colors):
    s = final[final["Scheme"] == scheme]
    plt.plot(
        s["Minute"],
        s["Pods"],
        marker="o",
        linewidth=2,
        color=color,
        label=scheme
    )

plt.xlabel("Time (minutes)")
plt.ylabel("#Pods")
plt.title("Total pod count (per-minute)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_pods_count_line.png", dpi=300)
plt.show()
