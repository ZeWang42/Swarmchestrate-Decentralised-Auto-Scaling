import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Queue-DAS": ["queue-das.csv"],
}

colors = {
    "HPA-80": "tab:blue",
    "DAS": "tab:orange",
    "Queue-DAS": "tab:green",
}

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
            color=colors[scheme],
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
