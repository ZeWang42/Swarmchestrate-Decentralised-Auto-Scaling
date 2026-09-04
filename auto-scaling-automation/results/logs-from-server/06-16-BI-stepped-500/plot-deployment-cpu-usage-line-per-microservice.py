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
    #"HPA-80": ["hpa-80.csv"],
    "Custom-DAS": ["custom-das.csv"],
    #"DAS": ["das.csv"],
    #"HPA-80": ["hpa-80-1.csv", "hpa-80-2.csv"],
    #"Custom-DAS": ["custom-das-1.csv", "custom-das-2.csv"],
    #"DAS": ["das-1.csv", "das-2.csv"],

}


files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Custom-DAS": ["custom-das.csv", "custom-das.csv"],

}

# Bind color to scheme name, not to plotting order.
scheme_colors = {
    "HPA-80": "tab:orange",
    "DAS": "tab:blue",
    "Custom-DAS": "tab:green",
}


default_color = "tab:gray"


all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df[df["Scope"] == "deployment"].copy()

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (
            df["Timestamp"] - start_time
        ).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# deployment/service name column
service_col = "Name"   # change if your CSV uses another header

# -----------------------------------
# STEP 1: CPU per service per second
# -----------------------------------
per_second = (
    data
    .groupby(
        ["Scheme", "Run", service_col, "ElapsedSec"],
        as_index=False
    )["CPU_m"]
    .mean()
)

# -----------------------------------
# STEP 2: minute binning
# -----------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -----------------------------------
# STEP 3: average per-second CPU within each minute
# -----------------------------------
per_minute = (
    per_second
    .groupby(
        ["Scheme", "Run", service_col, "Minute"],
        as_index=False
    )["CPU_m"]
    .mean()
)

# -----------------------------------
# STEP 4: average across runs
# -----------------------------------
final = (
    per_minute
    .groupby(
        ["Scheme", service_col, "Minute"],
        as_index=False
    )["CPU_m"]
    .mean()
)

# Convert millicores to CPU cores
final["CPU"] = final["CPU_m"] / 1000

# -----------------------------------
# PLOT: one figure per service
# -----------------------------------
services = sorted(final[service_col].unique())

for service in services:
    plt.figure(figsize=(9, 5))

    service_df = final[final[service_col] == service]

    for scheme in files.keys():
        s = service_df[service_df["Scheme"] == scheme]

        plt.plot(
            s["Minute"],
            s["CPU"],
            marker="o",
            linewidth=2,
            color=scheme_colors.get(scheme, default_color),
            label=scheme
        )

    plt.xlabel("Time (minutes)")
    plt.ylabel("CPU usage (cores)")
    plt.title(f"{service} CPU usage")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    safe_service = service.replace("/", "_").replace(" ", "_")
    plt.savefig(f"{safe_service}_cpu_usage.png", dpi=300)
    plt.show()
