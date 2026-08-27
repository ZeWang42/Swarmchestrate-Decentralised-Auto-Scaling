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

OUTPUT_PDF = Path("replicas_over_time_minutes_average.pdf")
OUTPUT_PNG = Path("replicas_over_time_minutes_average.png")
OUTPUT_CSV = Path("replicas_per_minute_average.csv")


# ---------------------------------------------------------------------
# Load one experiment run
# ---------------------------------------------------------------------

def load_replicas_per_minute(
    csv_path: Path,
) -> pd.DataFrame:
    """
    Calculate average total application replicas per elapsed minute
    for one experiment run.

    For each minute:
      1. Keep Online Boutique deployment rows.
      2. Average pod count for each deployment within that minute.
      3. Sum those per-deployment averages.
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
            f"No matching application deployments "
            f"found in {csv_path}"
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
            f"No valid replica measurements "
            f"found in {csv_path}"
        )

    first_timestamp = (
        app_df["Timestamp"].min()
    )

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
    # Sum deployment averages
    # -----------------------------------------------------------------

    minute_replicas = (
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

    return minute_replicas


# ---------------------------------------------------------------------
# Average multiple runs of one method
# ---------------------------------------------------------------------

def average_method_runs(
    csv_paths: list[Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load multiple runs for one autoscaler and average replica usage
    across runs at each elapsed minute.

    Returns:
        summary:
            Minute
            MeanReplicas
            StdReplicas
            MinReplicas
            MaxReplicas
            Runs

        all_runs:
            Run
            Minute
            AverageReplicas
    """

    run_frames = []

    valid_run = 0

    for csv_path in csv_paths:

        try:
            replicas = load_replicas_per_minute(
                csv_path
            )

        except (
            FileNotFoundError,
            ValueError,
        ) as exc:
            print(
                f"[SKIP RUN] {csv_path}: {exc}"
            )
            continue

        valid_run += 1

        replicas = replicas.copy()

        replicas.insert(
            0,
            "Run",
            valid_run,
        )

        replicas.insert(
            1,
            "File",
            str(csv_path),
        )

        run_frames.append(
            replicas
        )

    if not run_frames:
        raise ValueError(
            "No valid runs available."
        )

    all_runs = pd.concat(
        run_frames,
        ignore_index=True,
    )

    # -----------------------------------------------------------------
    # Average across runs at each minute
    # -----------------------------------------------------------------

    summary = (
        all_runs.groupby(
            "Minute",
            as_index=False,
        )
        .agg(
            MeanReplicas=(
                "AverageReplicas",
                "mean",
            ),

            StdReplicas=(
                "AverageReplicas",
                "std",
            ),

            MinReplicas=(
                "AverageReplicas",
                "min",
            ),

            MaxReplicas=(
                "AverageReplicas",
                "max",
            ),

            Runs=(
                "AverageReplicas",
                "count",
            ),
        )
    )

    summary[
        "StdReplicas"
    ] = (
        summary[
            "StdReplicas"
        ].fillna(0.0)
    )

    return (
        summary,
        all_runs,
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    series: dict[str, pd.DataFrame] = {}

    summary_outputs = []
    run_outputs = []

    # -----------------------------------------------------------------
    # Process each autoscaler
    # -----------------------------------------------------------------

    for autoscaler, csv_paths in INPUT_FILES.items():

        try:

            summary, all_runs = (
                average_method_runs(
                    csv_paths
                )
            )

        except ValueError as exc:

            print(
                f"[SKIP] {autoscaler}: {exc}"
            )

            continue

        series[
            autoscaler
        ] = summary

        # -------------------------------------------------------------
        # Save averaged results
        # -------------------------------------------------------------

        summary_output = (
            summary.copy()
        )

        summary_output.insert(
            0,
            "Autoscaler",
            autoscaler,
        )

        summary_outputs.append(
            summary_output
        )

        # -------------------------------------------------------------
        # Save individual runs too
        # -------------------------------------------------------------

        run_output = (
            all_runs.copy()
        )

        run_output.insert(
            0,
            "Autoscaler",
            autoscaler,
        )

        run_outputs.append(
            run_output
        )

    if not series:
        raise RuntimeError(
            "No replica data was plotted."
        )

    # -----------------------------------------------------------------
    # Save CSV
    # -----------------------------------------------------------------

    if summary_outputs:

        combined = pd.concat(
            summary_outputs,
            ignore_index=True,
        )

        combined.to_csv(
            OUTPUT_CSV,
            index=False,
        )

    # -----------------------------------------------------------------
    # Create compact figure
    # -----------------------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(8.6, 4.2)
    )

    # -----------------------------------------------------------------
    # Plot in INPUT_FILES order:
    #
    # QUEUE -> HPA80 -> DAS
    # -----------------------------------------------------------------

    for autoscaler in INPUT_FILES:

        if autoscaler not in series:
            continue

        replicas = series[
            autoscaler
        ]

        mean = replicas[
            "MeanReplicas"
        ]

        std = replicas[
            "StdReplicas"
        ]

        minute = replicas[
            "Minute"
        ]

        # -------------------------------------------------------------
        # Mean line
        # -------------------------------------------------------------

        ax.plot(
            minute,
            mean,
            color=COLORS[autoscaler],
            linewidth=2.6,
            label=DISPLAY_NAMES[
                autoscaler
            ],
        )

        # -------------------------------------------------------------
        # ±1 standard deviation
        # -------------------------------------------------------------

        lower = np.maximum(
            mean - std,
            0,
        )

        upper = (
            mean + std
        )

        ax.fill_between(
            minute,
            lower,
            upper,
            color=COLORS[
                autoscaler
            ],
            alpha=0.13,
            linewidth=0,
        )

    # -----------------------------------------------------------------
    # Labels
    # -----------------------------------------------------------------

    ax.set_xlabel(
        "Elapsed Time (minutes)"
    )

    ax.set_ylabel(
        "Average Total Replicas"
    )

    ax.set_title(
        "Application Replica Usage Over Time",
        pad=10,
    )

    # -----------------------------------------------------------------
    # Grid
    # -----------------------------------------------------------------

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.45,
    )

    # -----------------------------------------------------------------
    # Full plot frame
    # -----------------------------------------------------------------

    for spine in ax.spines.values():

        spine.set_visible(
            True
        )

        spine.set_linewidth(
            0.8
        )

    # -----------------------------------------------------------------
    # Legend
    # -----------------------------------------------------------------

    ax.legend(
        loc="upper left",
        ncol=3,
        frameon=False,
        prop={
            "weight": "bold",
            "size": 12,
        },
    )

    # -----------------------------------------------------------------
    # Axes
    # -----------------------------------------------------------------

    ax.set_xlim(
        left=0
    )

    all_values = pd.concat(
        [
            replicas[
                "MeanReplicas"
            ]
            for replicas
            in series.values()
        ],
        ignore_index=True,
    )

    all_upper_values = pd.concat(
        [
            (
                replicas[
                    "MeanReplicas"
                ]
                + replicas[
                    "StdReplicas"
                ]
            )
            for replicas
            in series.values()
        ],
        ignore_index=True,
    )

    y_min = max(
        0,
        all_values.min() - 2,
    )

    y_max = (
        all_upper_values.max()
        * 1.06
    )

    ax.set_ylim(
        y_min,
        y_max,
    )

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------

    fig.tight_layout()

    # -----------------------------------------------------------------
    # Save
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

    # -----------------------------------------------------------------
    # Print
    # -----------------------------------------------------------------

    print()

    for autoscaler in INPUT_FILES:

        if autoscaler not in series:
            continue

        print(
            f"=== {DISPLAY_NAMES[autoscaler]} ==="
        )

        print(
            series[
                autoscaler
            ][
                [
                    "Minute",
                    "MeanReplicas",
                    "StdReplicas",
                    "Runs",
                ]
            ]
            .head(10)
            .to_string(
                index=False
            )
        )

        print()

    print(
        f"Saved: {OUTPUT_PNG}"
    )

    print(
        f"Saved: {OUTPUT_PDF}"
    )

    print(
        f"Saved: {OUTPUT_CSV}"
    )

    plt.show()


if __name__ == "__main__":
    main()
