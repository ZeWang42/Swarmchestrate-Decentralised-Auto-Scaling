import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Enforce order: HPA → DAS → Queue
files = {
    "HPA-80": ["HPA-80.csv"],
    "DAS": ["DAS.csv"],
    "Queue-DAS": ["our-queue-das.csv"],
}
colors = ["tab:blue", "tab:orange", "tab:green"]

all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df[df["Scope"] == "node"].copy()

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# -----------------------------------
# STEP 1: per-second average across nodes
# -----------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["CPU_pct"]
    .mean()
)

# -----------------------------------
# STEP 2: minute bins
# -----------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -----------------------------------
# STEP 3: average per-second values within minute
# -----------------------------------
per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Minute"], as_index=False)["CPU_pct"]
    .mean()
)
# -----------------------------------
# STEP 4: average node CPU utilisation per run
# -----------------------------------
run_avg = (
    per_minute
    .groupby(["Scheme", "Run"], as_index=False)["CPU_pct"]
    .mean()
)

# -----------------------------------
# STEP 5: average across runs
# -----------------------------------
final_bar = (
    run_avg
    .groupby("Scheme", as_index=False)["CPU_pct"]
    .mean()
)

# Keep order
final_bar = final_bar.set_index("Scheme").loc[files.keys()].reset_index()

# -----------------------------------
# PLOT BAR
# -----------------------------------
plt.figure(figsize=(7, 5))

bars = plt.bar(
    final_bar["Scheme"],
    final_bar["CPU_pct"],
    color=colors
)

for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height * 1.01,
        f"{height:.1f}%",
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.xlabel("Scheme")
plt.ylabel("Average node CPU utilization (%)")
plt.title("Average cluster CPU utilization")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("node_cpu_utilization_bar.png", dpi=300)
plt.show()
