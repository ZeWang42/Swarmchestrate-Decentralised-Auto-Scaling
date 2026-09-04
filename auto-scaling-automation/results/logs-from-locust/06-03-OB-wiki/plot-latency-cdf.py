import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa80_stats.csv"],
    "DAS": ["das_stats.csv"],
    "Custom-DAS": ["custom_das_stats_0.csv"],
}


#files = {
#    "HPA-80": ["hpa80_stats_1.csv", "hpa80_stats_2.csv"],
#    "DAS": ["das_stats_1.csv", "das_stats_2.csv"],
#    "Queue-DAS": ["queue_das_stats_1.csv", "queue_das_stats_2.csv"],
#}

colors = ["tab:blue", "tab:orange", "tab:green"]

percentile_map = {
    "50%": 0.50,
    "66%": 0.66,
    "75%": 0.75,
    "80%": 0.80,
    "90%": 0.90,
    "95%": 0.95,
    "98%": 0.98,
    "99%": 0.99,
    "99.90%": 0.999,
    "99.99%": 0.9999,
    "100%": 1.0,
}

MAX_LAT = 1500  # ms

plt.figure(figsize=(7, 5))

for scheme, color in zip(files.keys(), colors):
    all_lat = []
    all_prob = []

    for file in files[scheme]:
        df = pd.read_csv(DATA_DIR / file)
        row = df.iloc[-1]

        for col, p in percentile_map.items():
            if col in df.columns and pd.notna(row[col]):
                val = min(row[col], MAX_LAT)
                all_lat.append(val)
                all_prob.append(p)

    lat, prob = zip(*sorted(zip(all_lat, all_prob)))

    plt.plot(lat, prob, marker="o", linewidth=2, color=color, label=scheme)

# SLO line
plt.axvline(500, color="black", linestyle="--", label="SLO 500 ms")

# ✅ Add percentile guide lines (CDF space)
for y in [0.90, 0.95, 0.99]:
    plt.axhline(y, linestyle="--", alpha=0.4, color="gray")
    plt.text(
        MAX_LAT * 0.05,   # left side
        y,
        f"P{int(y*100)}",
        ha="right",
        va="bottom",
        fontsize=9,
        color="gray"
    )

plt.xlabel("Latency (ms)")
plt.ylabel("CDF")
plt.title("Latency CDF (clipped at 1.5s)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("latency_cdf.png", dpi=300)
plt.show()
