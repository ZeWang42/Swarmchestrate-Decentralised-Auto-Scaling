import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Custom-DAS": ["custom-das.csv", "custom-das.csv"],

}
scheme_colors = {
    "HPA-80": "tab:orange",
    "DAS": "tab:blue",
    "Custom-DAS": "tab:green",
}

all_data = []

required_columns = {
    "Timestamp",
    "Scope",
    "Name",
    "Pods",
    "CPU_m",
}

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        path = DATA_DIR / file

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

        df = pd.read_csv(path)

        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")

        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df["Pods"] = pd.to_numeric(df["Pods"], errors="coerce")
        df["CPU_m"] = pd.to_numeric(df["CPU_m"], errors="coerce")

        df = df[df["Scope"] == "deployment"].copy()

        df = df.dropna(
            subset=[
                "Timestamp",
                "Name",
                "Pods",
                "CPU_m",
            ]
        )

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

if not all_data:
    raise ValueError("No data loaded.")

data = pd.concat(all_data, ignore_index=True)

per_second = (
    data.groupby(
        ["Scheme", "Run", "ElapsedSec"],
        as_index=False,
    )
    .agg(
        UsedCPU_m=("CPU_m", "sum"),
        AllocatedCPU_m=("AllocatedCPU_m", "sum"),
    )
)

per_second = per_second[
    per_second["AllocatedCPU_m"] > 0
].copy()

per_second["CPU_utilisation"] = (
    per_second["UsedCPU_m"]
    / per_second["AllocatedCPU_m"]
    * 100
)

per_second["Minute"] = per_second["ElapsedSec"] // 60

per_minute = (
    per_second.groupby(
        ["Scheme", "Run", "Minute"],
        as_index=False,
    )["CPU_utilisation"]
    .mean()
)

final = (
    per_minute.groupby(
        ["Scheme", "Minute"],
        as_index=False,
    )["CPU_utilisation"]
    .mean()
)

plt.figure(figsize=(10, 5))

for scheme in files.keys():
    s = final[final["Scheme"] == scheme]

    if s.empty:
        continue

    plt.plot(
        s["Minute"],
        s["CPU_utilisation"],
        marker="o",
        linewidth=2,
        color=scheme_colors.get(scheme, "tab:gray"),
        label=scheme,
    )

plt.xlabel("Time (minutes)")
plt.ylabel("CPU utilisation (%)")
plt.title("CPU utilisation over time")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_utilisation_line.png", dpi=300)
plt.show()
