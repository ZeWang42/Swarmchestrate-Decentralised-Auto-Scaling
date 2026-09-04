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

        # keep only deployments
        df = df[df["Scope"] == "deployment"].copy()

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# deployment name column
service_col = "Name"   # change if your CSV uses another header

# --------------------------------
# per-second pod count per service
# --------------------------------
per_second = (
    data.groupby(
        ["Scheme", "Run", service_col, "ElapsedSec"],
        as_index=False
    )["Pods"].mean()
)

# --------------------------------
# convert to minute bins
# --------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# --------------------------------
# average within each minute
# --------------------------------
per_minute = (
    per_second.groupby(
        ["Scheme", "Run", service_col, "Minute"],
        as_index=False
    )["Pods"].mean()
)

# --------------------------------
# average across runs
# --------------------------------
final = (
    per_minute.groupby(
        ["Scheme", service_col, "Minute"],
        as_index=False
    )["Pods"].mean()
)

# --------------------------------
# plot one figure per microservice
# --------------------------------
services = sorted(final[service_col].unique())

for service in services:
    plt.figure(figsize=(9, 5))

    service_df = final[final[service_col] == service]

    for scheme in files.keys():
        s = service_df[service_df["Scheme"] == scheme]

        plt.plot(
            s["Minute"],
            s["Pods"],
            marker="o",
            linewidth=2,
            color=scheme_colors.get(scheme, default_color),
            label=scheme
        )

    plt.xlabel("Time (minutes)")
    plt.ylabel("Pod count")
    plt.title(f"{service} pod scaling")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()

    plt.savefig(f"{service}_pods.png", dpi=300)
    plt.show()
