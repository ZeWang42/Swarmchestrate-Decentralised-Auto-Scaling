from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ---------------------------------------------------------------------
# Global plotting style
# ---------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 14,
    "axes.titlesize": 18,
    "axes.labelsize": 16,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 13,
})


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

FILES = {
    #"DAS": Path("das.csv"),
    #"HPA-50": Path("hpa50.csv"),
    #"HPA-80": Path("hpa80.csv"),
    "PBScaler": Path("pbscaler.csv"),
}

COLORS = {
    #"DAS": "tab:blue",
    #"HPA-50": "tab:orange",
    #"HPA-80": "tab:green",
    "PBScaler": "tab:red",
}

# Only these deployments are counted as part of Online Boutique.
# redis-cart is included because it belongs to the application.
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

OUTPUT_PDF = Path("replicas_over_time_minutes.pdf")
OUTPUT_PNG = Path("replicas_over_time_minutes.png")
OUTPUT_CSV = Path("replicas_per_minute.csv")


def load_replicas_per_minute(csv_path: Path) -> pd.DataFrame:
    """
    Calculate the average total application replica count per minute.

    Steps:
    1. Keep application deployment rows.
    2. Sum replicas across deployments at each timestamp.
    3. Convert timestamps to elapsed minutes.
    4. Average the total replica count within each minute.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

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

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(APPLICATION_DEPLOYMENTS)),
        ["Timestamp", "Name", "Pods"],
    ].copy()

    if app_df.empty:
        available_names = sorted(
            df.loc[
                df["Scope"] == "deployment",
                "Name",
            ]
            .dropna()
            .astype(str)
            .unique()
        )

        raise ValueError(
            f"No matching application deployments found in {csv_path}.\n"
            f"Available deployment names: {available_names}"
        )

    app_df["Timestamp"] = pd.to_datetime(
        app_df["Timestamp"],
        errors="coerce",
    )

    app_df["Pods"] = pd.to_numeric(
        app_df["Pods"],
        errors="coerce",
    )

    app_df = app_df.dropna(
        subset=["Timestamp", "Pods"]
    )

    if app_df.empty:
        raise ValueError(
            f"No valid replica measurements found in {csv_path}"
        )

    # Total application replicas at each monitoring timestamp.
    timestamp_totals = (
        app_df.groupby(
            "Timestamp",
            as_index=False,
        )["Pods"]
        .sum()
        .rename(columns={"Pods": "TotalReplicas"})
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    first_timestamp = timestamp_totals["Timestamp"].iloc[0]

    timestamp_totals["ElapsedSeconds"] = (
        timestamp_totals["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    # Assign every sample to elapsed minute 0, 1, 2, ...
    timestamp_totals["Minute"] = (
        timestamp_totals["ElapsedSeconds"] // 60
    ).astype(int)

    # Average all total-replica samples within each minute.
    minute_replicas = (
        timestamp_totals.groupby(
            "Minute",
            as_index=False,
        )["TotalReplicas"]
        .mean()
        .rename(
            columns={
                "TotalReplicas": "AverageReplicas"
            }
        )
    )

    return minute_replicas


def main() -> None:
    all_results: list[pd.DataFrame] = []
    plotted = 0

    fig, ax = plt.subplots(figsize=(8.4, 5.2))

    for autoscaler, csv_path in FILES.items():
        try:
            replicas = load_replicas_per_minute(csv_path)

        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {autoscaler}: {exc}")
            continue

        output = replicas.copy()
        output.insert(0, "Autoscaler", autoscaler)
        all_results.append(output)

        ax.plot(
            replicas["Minute"],
            replicas["AverageReplicas"],
            color=COLORS[autoscaler],
            linewidth=2.3,
            label=autoscaler,
        )

        plotted += 1

    if plotted == 0:
        raise RuntimeError(
            "No replica data was plotted. "
            "Check the filenames and deployment names."
        )

    if all_results:
        pd.concat(
            all_results,
            ignore_index=True,
        ).to_csv(
            OUTPUT_CSV,
            index=False,
        )

    ax.set_xlabel("Elapsed Time (minutes)")
    ax.set_ylabel("Average Total Replicas")
    ax.set_title("Average Application Replica Count over Time")

    ax.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
    )

    ax.legend(
        loc="lower right",
        ncol=1,
        frameon=True,
        framealpha=0.95,
    )

    ax.set_xlim(left=0)

    # Online Boutique begins with 11 components when redis-cart is included.
    # Set this to 0 to show the full vertical range.
    ax.set_ylim(bottom=10)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_PNG,
        dpi=300,
        bbox_inches="tight",
    )

    fig.savefig(
        OUTPUT_PDF,
        dpi=600,
        bbox_inches="tight",
    )

    print(f"Saved: {OUTPUT_PNG}")
    print(f"Saved: {OUTPUT_PDF}")
    print(f"Saved: {OUTPUT_CSV}")

    plt.show()


if __name__ == "__main__":
    main()
