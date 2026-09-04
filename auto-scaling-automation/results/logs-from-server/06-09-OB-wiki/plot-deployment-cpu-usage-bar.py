import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Enforce order: HPA → DAS → Queue
files = {
#    "HPA-80": ["hpa-80-1.csv"],
#    "Custom-DAS": ["custom-das-1.csv"],
#    "DAS": ["das-1.csv"],
    #"HPA-80": ["hpa-80-2.csv"],
    #"Custom-DAS": ["custom-das-2.csv"],
    #"DAS": ["das-2.csv"],
    "Dadqn": ["dadqn.csv"],
    "HPA-80": ["hpa-80.csv"],
    "Custom-DAS": ["custom-das.csv"],
    "DAS": ["das.csv"],
    #"HPA-80": ["hpa-80-1.csv", "hpa-80-2.csv"],
    #"Custom-DAS": ["custom-das-1.csv", "custom-das-2.csv"],
    #"DAS": ["das-1.csv", "das-2.csv"],

}


# Bind color to scheme name, not to plotting order.
scheme_colors = {
    "Dadqn": "tab:blue",
    "HPA-80": "tab:orange",
    "Custom-DAS": "tab:green",
    "DAS": "tab:brown",
}

default_color = "tab:gray"

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
# -----------------------------------
# STEP 1: sum CPU usage across deployments per second
# -----------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["CPU_m"]
    .sum()
)

# -----------------------------------
# STEP 2: minute binning
# -----------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -----------------------------------
# STEP 3: average per-second CPU usage within each minute
# -----------------------------------
per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Minute"], as_index=False)["CPU_m"]
    .mean()
)

# -----------------------------------
# STEP 4: convert each minute to accumulated mCPU-seconds
# avg mCPU in minute × 60 seconds
# -----------------------------------
per_minute["CPU_m_seconds"] = per_minute["CPU_m"] * 60

# -----------------------------------
# STEP 5: accumulate all minutes per run
# -----------------------------------
run_totals = (
    per_minute
    .groupby(["Scheme", "Run"], as_index=False)["CPU_m_seconds"]
    .sum()
)

# -----------------------------------
# STEP 6: average across runs
# -----------------------------------
final_bar = (
    run_totals
    .groupby("Scheme", as_index=False)["CPU_m_seconds"]
    .mean()
)

final_bar = final_bar.set_index("Scheme").loc[files.keys()].reset_index()
# Convert mCPU-seconds to CPU-seconds
final_bar["CPU_seconds"] = final_bar["CPU_m_seconds"] / 1000

# -----------------------------------
# PLOT
# -----------------------------------
plt.figure(figsize=(7, 5))

bars = plt.bar(
    final_bar["Scheme"],
    final_bar["CPU_seconds"],
    color=[scheme_colors.get(scheme, default_color) for scheme in final_bar["Scheme"]]
)

for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height * 1.01,
        f"{height:.1f}",
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.xlabel("Scheme")
plt.ylabel("Accumulated CPU usage (CPU-seconds)")
plt.title("Accumulated CPU usage of all deployments")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_usage_bar.png", dpi=300)
plt.show()
