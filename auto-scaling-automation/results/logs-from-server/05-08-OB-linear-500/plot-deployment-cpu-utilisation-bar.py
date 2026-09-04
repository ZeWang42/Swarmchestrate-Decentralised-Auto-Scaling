import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Queue-DAS": ["queue-das.csv"],
}
colors = ["tab:blue", "tab:orange", "tab:green"]

all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df[df["Scope"] == "deployment"].copy()

        df["CPU_request_m"] = df["Name"].apply(
            lambda x: 200 if x == "productpage-v1" else 100
        )

        df["AllocatedCPU_m"] = df["Pods"] * df["CPU_request_m"]

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# -----------------------------------
# STEP 1: total used and allocated CPU per second
# -----------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)
    .agg(
        UsedCPU_m=("CPU_m", "sum"),
        AllocatedCPU_m=("AllocatedCPU_m", "sum")
    )
)

per_second["CPU_utilisation"] = (
    per_second["UsedCPU_m"] / per_second["AllocatedCPU_m"] * 100
)

# -----------------------------------
# STEP 2: average utilisation per run
# -----------------------------------
run_avg = (
    per_second
    .groupby(["Scheme", "Run"], as_index=False)["CPU_utilisation"]
    .mean()
)

# -----------------------------------
# STEP 3: average across runs
# -----------------------------------
final = (
    run_avg
    .groupby("Scheme", as_index=False)["CPU_utilisation"]
    .mean()
)

# Keep dict order
final["Scheme"] = pd.Categorical(final["Scheme"], categories=files.keys(), ordered=True)
final = final.sort_values("Scheme")

# -----------------------------------
# PLOT
# -----------------------------------
plt.figure(figsize=(7, 5))

bars = plt.bar(
    final["Scheme"],
    final["CPU_utilisation"],
    color=colors
)

# Y-axis 0–100
plt.ylim(0, 100)

# Add value labels on top of bars
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height + 1,                      # small offset above bar
        f"{height:.1f}%",                # format
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.xlabel("Scheme")
plt.ylabel("Deployment CPU utilisation (%)")
plt.title("Average deployment CPU utilisation")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_utilisation_bar.png", dpi=300)
plt.show()
