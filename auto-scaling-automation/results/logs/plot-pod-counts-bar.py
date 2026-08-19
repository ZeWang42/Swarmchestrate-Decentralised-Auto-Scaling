from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

FILES = {
    "DAS": "das.csv",
    "HPA-50": "hpa50.csv",
    "HPA-80": "hpa80.csv",
    "PBScaler": "pbscaler.csv",
}

COLORS = {
    "DAS": "tab:blue",
    "HPA-50": "tab:orange",
    "HPA-80": "tab:green",
    "PBScaler": "tab:red",
}


def average_total_replicas(csv_file):
    df = pd.read_csv(csv_file)

    df = df[df["Scope"] == "deployment"].copy()
    df["Pods"] = pd.to_numeric(df["Pods"], errors="coerce")

    # total replicas at each timestamp
    totals = (
        df.groupby("Timestamp")["Pods"]
        .sum()
        .reset_index(name="TotalReplicas")
    )

    return totals["TotalReplicas"].mean()


results = {
    name: average_total_replicas(csv)
    for name, csv in FILES.items()
}

fig, ax = plt.subplots(figsize=(5.5, 4.5))

bars = ax.bar(
    results.keys(),
    results.values(),
    color=[COLORS[k] for k in results.keys()],
    width=0.6,
)

# show values on bars
for bar in bars:
    h = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width()/2,
        h + 0.2,
        f"{h:.1f}",
        ha="center",
        va="bottom",
        fontsize=10,
    )

ax.set_ylabel("Average Total Replicas")
ax.set_title("Average Replica Usage")
ax.set_ylim(0, max(results.values()) * 1.15)

plt.tight_layout()
plt.savefig("average_replicas_bar.pdf", dpi=600)
plt.savefig("average_replicas_bar.png", dpi=300)
plt.show()
