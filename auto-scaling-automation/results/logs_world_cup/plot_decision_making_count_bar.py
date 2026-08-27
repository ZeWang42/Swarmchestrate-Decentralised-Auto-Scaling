from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Global plotting style
# ---------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 13,
    "axes.titlesize": 17,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
})


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

INPUT_FILES = {
    "queue-CDT120": [
        Path("queue-CDT120-1.csv"),
        Path("queue-CDT120-2.csv"),
        Path("queue-CDT120-3.csv"),
        Path("queue-CDT120-4.csv"),
        Path("queue-CDT120-5.csv"),
    ],
    
    "queue-CDT300": [
        Path("queue-CDT300-1.csv"),
        Path("queue-CDT300-2.csv"),
        Path("queue-CDT300-3.csv"),
        Path("queue-CDT300-4.csv"),
        Path("queue-CDT300-5.csv"),
    ],
    "hpa80-CDT120": [
        Path("hpa80-CDT120-1.csv"),
        Path("hpa80-CDT120-2.csv"),
        Path("hpa80-CDT120-3.csv"),
        Path("hpa80-CDT120-4.csv"),
        Path("hpa80-CDT120-5.csv"),
    ],
        
    "hpa80-CDT300": [
        Path("hpa80-CDT300-1.csv"),
        Path("hpa80-CDT300-2.csv"),
        Path("hpa80-CDT300-3.csv"),
        Path("hpa80-CDT300-4.csv"),
        Path("hpa80-CDT300-5.csv"),
    ],

}

DISPLAY_NAMES = {
    "queue-CDT120": "QUEUE-CDT120",
    "queue-CDT300": "QUEUE-CDT300",
    "hpa80-CDT120": "HPA80-CDT120",
    "hpa80-CDT300": "HPA80-CDT300",
    #"das": "DAS",
}

COLORS = {
    "queue-CDT120": "tab:orange",
    "queue-CDT300": "tab:green",
    "hpa80-CDT120": "tab:blue",
    "hpa80-CDT300": "tab:red",
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

OUTPUT_RUN_CSV = Path("scaling_decision_per_run.csv")
OUTPUT_SUMMARY_CSV = Path("scaling_decision_summary.csv")

OUTPUT_PNG = Path("scaling_decision_count_average.png")
OUTPUT_PDF = Path("scaling_decision_count_average.pdf")


# ---------------------------------------------------------------------
# Load one run
# ---------------------------------------------------------------------

def load_replica_delta(
    csv_path: Path,
) -> pd.DataFrame:
    """
    Calculate average total application replicas per minute
    and replica change between consecutive minutes.

    Delta:
        ReplicaDelta(t) = Replicas(t) - Replicas(t-1)
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

    missing = required_columns.difference(
        df.columns
    )

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (
            df["Name"].isin(
                APPLICATION_DEPLOYMENTS
            )
        ),
        [
            "Timestamp",
            "Name",
            "Pods",
        ],
    ].copy()

    if app_df.empty:
        raise ValueError(
            f"No matching application deployments found in {csv_path}"
        )

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

    # -----------------------------------------------------------------
    # Convert to elapsed minute
    # -----------------------------------------------------------------

    first_timestamp = app_df[
        "Timestamp"
    ].min()

    app_df["ElapsedSeconds"] = (
        app_df["Timestamp"]
        - first_timestamp
    ).dt.total_seconds()

    app_df["Minute"] = (
        app_df["ElapsedSeconds"] // 60
    ).astype(int)

    # -----------------------------------------------------------------
    # Average each deployment within each minute
    # -----------------------------------------------------------------

    deployment_minute_avg = (
        app_df.groupby(
            [
                "Minute",
                "Name",
            ],
            as_index=False,
        )["Pods"]
        .mean()
        .rename(
            columns={
                "Pods":
                    "AverageDeploymentReplicas"
            }
        )
    )

    # -----------------------------------------------------------------
    # Total application replicas per minute
    # -----------------------------------------------------------------

    minute_total = (
        deployment_minute_avg.groupby(
            "Minute",
            as_index=False,
        )[
            "AverageDeploymentReplicas"
        ]
        .sum()
        .rename(
            columns={
                "AverageDeploymentReplicas":
                    "AverageReplicas"
            }
        )
    )

    # -----------------------------------------------------------------
    # Calculate decision delta
    # -----------------------------------------------------------------

    minute_total["ReplicaDelta"] = (
        minute_total[
            "AverageReplicas"
        ].diff()
    )

    return minute_total


# ---------------------------------------------------------------------
# Decision metrics for one run
# ---------------------------------------------------------------------

def calculate_decision_metrics(
    replica_data: pd.DataFrame,
) -> dict[str, float]:
    """
    Calculate scaling decision metrics.

    ScaleUpEvents:
        Number of intervals where replicas increased.

    ScaleDownEvents:
        Number of intervals where replicas decreased.

    DecisionEvents:
        Number of intervals with any non-zero replica change.

    TotalScalingMagnitude:
        Sum of absolute replica changes.

        Example:
            +2, -1, +3 -> 6
    """

    delta = (
        replica_data["ReplicaDelta"]
        .dropna()
    )

    scale_up_events = int(
        (delta > 0).sum()
    )

    scale_down_events = int(
        (delta < 0).sum()
    )

    decision_events = int(
        (delta != 0).sum()
    )

    total_scaling_magnitude = float(
        delta.abs().sum()
    )

    return {
        "ScaleUpEvents":
            scale_up_events,

        "ScaleDownEvents":
            scale_down_events,

        "DecisionEvents":
            decision_events,

        "TotalScalingMagnitude":
            total_scaling_magnitude,
    }


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    run_rows = []

    # -----------------------------------------------------------------
    # Calculate metrics for every run independently
    # -----------------------------------------------------------------

    for autoscaler, csv_paths in INPUT_FILES.items():

        valid_run = 0

        for csv_path in csv_paths:

            try:

                replica_data = (
                    load_replica_delta(
                        csv_path
                    )
                )

                metrics = (
                    calculate_decision_metrics(
                        replica_data
                    )
                )

            except (
                FileNotFoundError,
                ValueError,
            ) as exc:

                print(
                    f"[SKIP] {autoscaler}: "
                    f"{csv_path}: {exc}"
                )

                continue

            valid_run += 1

            run_rows.append({
                "Autoscaler":
                    autoscaler,

                "DisplayName":
                    DISPLAY_NAMES[
                        autoscaler
                    ],

                "Run":
                    valid_run,

                "File":
                    str(csv_path),

                **metrics,
            })

    if not run_rows:
        raise RuntimeError(
            "No scaling decision data available."
        )

    # -----------------------------------------------------------------
    # Per-run results
    # -----------------------------------------------------------------

    run_df = pd.DataFrame(
        run_rows
    )

    run_df.to_csv(
        OUTPUT_RUN_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Average across runs
    # -----------------------------------------------------------------

    summary = (
        run_df.groupby(
            [
                "Autoscaler",
                "DisplayName",
            ],
            as_index=False,
        )
        .agg(
            MeanScaleUpEvents=(
                "ScaleUpEvents",
                "mean",
            ),

            StdScaleUpEvents=(
                "ScaleUpEvents",
                "std",
            ),

            MeanScaleDownEvents=(
                "ScaleDownEvents",
                "mean",
            ),

            StdScaleDownEvents=(
                "ScaleDownEvents",
                "std",
            ),

            MeanDecisionEvents=(
                "DecisionEvents",
                "mean",
            ),

            StdDecisionEvents=(
                "DecisionEvents",
                "std",
            ),

            MeanTotalScalingMagnitude=(
                "TotalScalingMagnitude",
                "mean",
            ),

            StdTotalScalingMagnitude=(
                "TotalScalingMagnitude",
                "std",
            ),

            MinTotalScalingMagnitude=(
                "TotalScalingMagnitude",
                "min",
            ),

            MaxTotalScalingMagnitude=(
                "TotalScalingMagnitude",
                "max",
            ),

            Runs=(
                "TotalScalingMagnitude",
                "count",
            ),
        )
    )

    # -----------------------------------------------------------------
    # Handle one-run case
    # -----------------------------------------------------------------

    std_columns = [
        "StdScaleUpEvents",
        "StdScaleDownEvents",
        "StdDecisionEvents",
        "StdTotalScalingMagnitude",
    ]

    summary[
        std_columns
    ] = (
        summary[
            std_columns
        ].fillna(0.0)
    )

    # -----------------------------------------------------------------
    # Keep order:
    #
    # QUEUE -> HPA80 -> DAS
    # -----------------------------------------------------------------

    order_map = {
        name: i
        for i, name in enumerate(
            INPUT_FILES
        )
    }

    summary["Order"] = (
        summary["Autoscaler"]
        .map(
            order_map
        )
    )

    summary = (
        summary
        .sort_values(
            "Order"
        )
        .drop(
            columns="Order"
        )
        .reset_index(
            drop=True
        )
    )

    # -----------------------------------------------------------------
    # Save summary
    # -----------------------------------------------------------------

    summary.to_csv(
        OUTPUT_SUMMARY_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Print per-run results
    # -----------------------------------------------------------------

    print()
    print(
        "=== Scaling Decision Per Run ==="
    )

    print(
        run_df[
            [
                "DisplayName",
                "Run",
                "ScaleUpEvents",
                "ScaleDownEvents",
                "DecisionEvents",
                "TotalScalingMagnitude",
            ]
        ].to_string(
            index=False
        )
    )

    # -----------------------------------------------------------------
    # Print average results
    # -----------------------------------------------------------------

    print()
    print(
        "=== Average Scaling Decision Summary ==="
    )

    print(
        summary[
            [
                "DisplayName",
                "Runs",
                "MeanScaleUpEvents",
                "MeanScaleDownEvents",
                "MeanDecisionEvents",
                "MeanTotalScalingMagnitude",
                "StdTotalScalingMagnitude",
                "MinTotalScalingMagnitude",
                "MaxTotalScalingMagnitude",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    # -----------------------------------------------------------------
    # Plot mean total scaling magnitude
    # -----------------------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(6, 5)
    )

    x = np.arange(
        len(summary)
    )

    bars = ax.bar(
        x,
        summary[
            "MeanTotalScalingMagnitude"
        ],
        color=[
            COLORS[name]
            for name in summary[
                "Autoscaler"
            ]
        ],
        width=0.58,
        zorder=3,
    )

    # -----------------------------------------------------------------
    # Standard deviation error bars
    # -----------------------------------------------------------------

    ax.errorbar(
        x,
        summary[
            "MeanTotalScalingMagnitude"
        ],
        yerr=summary[
            "StdTotalScalingMagnitude"
        ],
        fmt="none",
        color="black",
        linewidth=1.2,
        capsize=5,
        zorder=4,
    )

    # -----------------------------------------------------------------
    # Individual run points
    # -----------------------------------------------------------------

    rng = np.random.default_rng(
        42
    )

    positions = {
        autoscaler: i
        for i, autoscaler
        in enumerate(
            summary[
                "Autoscaler"
            ]
        )
    }

    for autoscaler in summary[
        "Autoscaler"
    ]:

        values = run_df.loc[
            run_df[
                "Autoscaler"
            ] == autoscaler,
            "TotalScalingMagnitude",
        ].to_numpy()

        jitter = rng.uniform(
            -0.055,
            0.055,
            size=len(values),
        )

        ax.scatter(
            (
                positions[
                    autoscaler
                ]
                + jitter
            ),
            values,
            color="black",
            s=28,
            zorder=5,
        )

    # -----------------------------------------------------------------
    # Values above bars
    # -----------------------------------------------------------------

    max_value = max(
        (
            summary[
                "MeanTotalScalingMagnitude"
            ]
            + summary[
                "StdTotalScalingMagnitude"
            ]
        ).max(),

        run_df[
            "TotalScalingMagnitude"
        ].max(),

        1.0,
    )

    offset = max(
        0.2,
        max_value * 0.02,
    )

    for bar, value in zip(
        bars,
        summary[
            "MeanTotalScalingMagnitude"
        ],
    ):

        ax.text(
            (
                bar.get_x() 
                #+ bar.get_width() / 2
            ),
            (
                bar.get_height()
                + offset
            ),
            f"{value:.1f}",
            ha="left",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    # -----------------------------------------------------------------
    # Formatting
    # -----------------------------------------------------------------

    ax.set_xticks(
        x
    )

    ax.set_xticklabels(
        summary[
            "DisplayName"
        ],
        #fontweight="bold",
    )

    ax.set_ylabel(
        r"Total Scaling Magnitude ($\sum |\Delta replicas|$)"
    )

    ax.set_title(
        "Autoscaler Decision Activity"
    )

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.45,
        zorder=0,
    )

    ax.set_ylim(
        0,
        max_value * 1.15,
    )

    # Full frame
    for spine in ax.spines.values():

        spine.set_visible(
            True
        )

        spine.set_linewidth(
            0.8
        )

    fig.tight_layout()

    # -----------------------------------------------------------------
    # Save figure
    # -----------------------------------------------------------------

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

    print()
    print(
        f"Saved: {OUTPUT_RUN_CSV}"
    )

    print(
        f"Saved: {OUTPUT_SUMMARY_CSV}"
    )

    print(
        f"Saved: {OUTPUT_PNG}"
    )

    print(
        f"Saved: {OUTPUT_PDF}"
    )

    plt.show()


if __name__ == "__main__":
    main()
