import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    # "HPA-80": ["hpa-80-1.csv", "hpa-80-2.csv"],
    "HPA-80": ["hpa-80-1.csv"],
    "DAS": ["das-1.csv", "das-2.csv"],
    "Custom-DAS": ["custom-das-1.csv", "custom-das-2.csv"],
}

scheme_colors = {
    "HPA-80": "tab:orange",
    "DAS": "tab:blue",
    "Custom-DAS": "tab:green",
}

all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        path = DATA_DIR / file

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

        df = pd.read_csv(path)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df["Pods"] = pd.to_numeric(df["Pods"], errors="coerce")
        df["CPU_m"] = pd.to_numeric(df["CPU_m"], errors="coerce")

        df = df[df["Scope"] == "deployment"].copy()
        df = df.dropna(subset=["Timestamp", "Name", "Pods", "CPU_m"])

        if df.empty:
            raise ValueError(f"{path} has no valid deployment rows.")

        df["CPU_request_m"] = df["Name"].apply(
            lambda x: 200 if x == "productpage-v1" else 100
        )

        df["AllocatedCPU_m"] = df["Pods"] * df["CPU_request_m"]

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (
            df["Timestamp"] - start_time
        ).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

per_second = (
    data.groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)
    .agg(
        UsedCPU_m=("CPU_m", "sum"),
        AllocatedCPU_m=("AllocatedCPU_m", "sum"),
    )
)

per_second = per_second[per_second["AllocatedCPU_m"] > 0].copy()

per_second["CPU_utilisation"] = (
    per_second["UsedCPU_m"] / per_second["AllocatedCPU_m"] * 100
)

run_avg = (
    per_second.groupby(["Scheme", "Run"], as_index=False)["CPU_utilisation"]
    .mean()
)

final = (
    run_avg.groupby("Scheme", as_index=False)["CPU_utilisation"]
    .mean()
)

final["Scheme"] = pd.Categorical(
    final["Scheme"],
    categories=list(files.keys()),
    ordered=True,
)

final = final.sort_values("Scheme")

colors = [
    scheme_colors.get(scheme, "tab:gray")
    for scheme in final["Scheme"].astype(str)
]

plt.figure(figsize=(7, 5))

bars = plt.bar(
    final["Scheme"].astype(str),
    final["CPU_utilisation"],
    color=colors,
)

plt.ylim(0, 100)

for bar in bars:
    height = bar.get_height()

    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height + 1,
        f"{height:.1f}%",
        ha="center",
        va="bottom",
        fontsize=10,
    )

plt.xlabel("Scheme")
plt.ylabel("Deployment CPU utilisation (%)")
plt.title("Average deployment CPU utilisation")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_utilisation_bar.png", dpi=300)
plt.show()
