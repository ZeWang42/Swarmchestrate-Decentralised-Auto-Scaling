from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

INPUT_FILES = {
    "queue": Path("queue-2.csv"),
    "hpa80": Path("hpa80-1.csv"),
    "das": Path("das-1.csv"),
}

COLORS = {
    "queue": "tab:orange",
    "hpa80": "tab:green",
    "das": "tab:blue",
}

APPLICATION_DEPLOYMENTS = {
    "frontend",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
    "adservice",
    "redis-cart",
}

OUTPUT_PDF = Path("average_replicas_bar.pdf")
OUTPUT_PNG = Path("average_replicas_bar.png")


def average_total_replicas(csv_path: Path) -> float:
    """
    Return the average total application replicas.

    Logic:
    1. Keep Online Boutique deployment rows.
    2. Convert timestamps to elapsed minutes.
    3. Average pod count for each deployment within each minute.
    4. Sum those deployment averages to get total replicas per minute.
    5. Average total replicas across all minutes.
    """

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {csv_path}"
        )

    df = pd.read_csv(csv_path)

    required_columns = {
        "Timestamp",
        "Scope",
        "Name",
        "Pods",
    }

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    # -------------------------------------------------------------
    # Keep only Online Boutique application deployments
    # -------------------------------------------------------------

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(APPLICATION_DEPLOYMENTS)),
        ["Timestamp", "Name", "Pods"],
    ].copy()

    if app_df.empty:
        raise ValueError(
            f"No matching application deployments found in {csv_path}"
        )

    # -------------------------------------------------------------
    # Parse timestamps and pod counts
    # -------------------------------------------------------------

    app_df["Timestamp"] = pd.to_datetime(
        app_df["Timestamp"],
        format="mixed",
        dayfirst=True,
        errors="coerce",
    )

    app_df["Pods"] = pd.to_numeric(
        app_df["Pods"],
        errors="coerce",
    )

    app_df = app_df.dropna(
        subset=[
            "Timestamp",
            "Name",
            "Pods",
        ]
    )

    if app_df.empty:
        raise ValueError(
            f"No valid replica measurements found in {csv_path}"
        )

    # -------------------------------------------------------------
    # Convert to elapsed minutes
    # -------------------------------------------------------------

    first_timestamp = app_df["Timestamp"].min()

    app_df["ElapsedSeconds"] = (
        app_df["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    app_df["Minute"] = (
        app_df["ElapsedSeconds"] // 60
    ).astype(int)

    # -------------------------------------------------------------
    # Average each deployment within each minute
    # -------------------------------------------------------------

    deployment_minute_avg = (
        app_df.groupby(
            ["Minute", "Name"],
            as_index=False,
        )["Pods"]
        .mean()
        .rename(
            columns={
                "Pods": "AverageDeploymentReplicas"
            }
        )
    )

    # -------------------------------------------------------------
    # Sum deployment averages within each minute
    # -------------------------------------------------------------

    minute_totals = (
        deployment_minute_avg.groupby(
            "Minute",
            as_index=False,
        )["AverageDeploymentReplicas"]
        .sum()
        .rename(
            columns={
                "AverageDeploymentReplicas": "AverageTotalReplicas"
            }
        )
    )

    # -------------------------------------------------------------
    # Average across all minutes
    # -------------------------------------------------------------

    return minute_totals["AverageTotalReplicas"].mean()


# ---------------------------------------------------------------------
# Calculate averages
# ---------------------------------------------------------------------

results = {}

for name, csv_path in INPUT_FILES.items():
    try:
        results[name] = average_total_replicas(
            csv_path
        )

    except (FileNotFoundError, ValueError) as exc:
        print(f"[SKIP] {name}: {exc}")


if not results:
    raise RuntimeError(
        "No replica data available."
    )


# ---------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------

fig, ax = plt.subplots(
    figsize=(5.5, 4.5)
)

bars = ax.bar(
    results.keys(),
    results.values(),
    color=[
        COLORS[k]
        for k in results
    ],
    width=0.6,
)


# ---------------------------------------------------------------------
# Show values on bars
# ---------------------------------------------------------------------

for bar in bars:
    height = bar.get_height()

    ax.text(
        bar.get_x() + bar.get_width() / 2,
        height + 0.2,
        f"{height:.1f}",
        ha="center",
        va="bottom",
        fontsize=10,
    )


# ---------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------

ax.set_ylabel(
    "Average Total Replicas"
)

ax.set_title(
    "Average Replica Usage"
)

ax.set_ylim(
    0,
    max(results.values()) * 1.15,
)

ax.grid(
    axis="y",
    linestyle=":",
    linewidth=0.8,
    alpha=0.6,
)

plt.tight_layout()


# ---------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------

plt.savefig(
    OUTPUT_PDF,
    dpi=600,
    bbox_inches="tight",
)

plt.savefig(
    OUTPUT_PNG,
    dpi=300,
    bbox_inches="tight",
)

print(f"Saved: {OUTPUT_PDF}")
print(f"Saved: {OUTPUT_PNG}")

plt.show()
