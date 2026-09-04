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
        df["ElapsedSec"] = (
            df["Timestamp"] - start_time
        ).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["Pods"]
    .sum()
)

per_second["Minute"] = per_second["ElapsedSec"] // 60

per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Minute"], as_index=False)["Pods"]
    .mean()
)

final = (
    per_minute
    .groupby(["Scheme", "Minute"], as_index=False)["Pods"]
    .mean()
)

plt.figure(figsize=(10, 5))

for scheme in files.keys():
    color = scheme_colors.get(scheme, default_color)
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
plt.ylabel("Average #Pods")
plt.title("Average deployment pod count per minute")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_pods_count_line_average.png", dpi=300)
plt.show()
