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

    "hybrid-CDT120": [
        Path("hybrid-CDT120-1.csv"),
        Path("hybrid-CDT120-2.csv"),
        Path("hybrid-CDT120-3.csv"),
        Path("hybrid-CDT120-4.csv"),
        Path("hybrid-CDT120-5.csv"),
    ],

    "hybrid-CDT300": [
        Path("hybrid-CDT300-1.csv"),
        Path("hybrid-CDT300-2.csv"),
        Path("hybrid-CDT300-3.csv"),
        Path("hybrid-CDT300-4.csv"),
        Path("hybrid-CDT300-5.csv"),
    ],

}

DISPLAY_NAMES = {
    "queue-CDT120": "Queue-CDT120",
    "queue-CDT300": "Queue-CDT300",
    "hpa80-CDT120": "HPA80-CDT120",
    "hpa80-CDT300": "HPA80-CDT300",
    "hybrid-CDT120": "Hybrid-CDT120",
    "hybrid-CDT300": "Hybrid-CDT300",
}

COLORS = {
    "queue-CDT120": "tab:orange",
    "queue-CDT300": "tab:green",
    "hpa80-CDT120": "tab:blue",
    "hpa80-CDT300": "tab:red",
    "hybrid-CDT120": "tab:purple",
    "hybrid-CDT300": "tab:brown",
}

MAX_MINUTE = 71

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

OUTPUT_PNG = Path("replica_delta_over_time_average.png")
OUTPUT_PDF = Path("replica_delta_over_time_average.pdf")
OUTPUT_CSV = Path("replica_delta_over_time_average.csv")


# ---------------------------------------------------------------------
# Load one run
# ---------------------------------------------------------------------

def load_replica_delta(
    csv_path: Path,
) -> pd.DataFrame:
    """
    Calculate total application replica delta per minute for one run.

    ReplicaDelta(t) =
        AverageReplicas(t) - AverageReplicas(t-1)
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


    # Keep only minute 0 through minute 71.
    app_df = app_df.loc[
        app_df["Minute"] <= MAX_MINUTE
    ].copy()
    # -----------------------------------------------------------------
    # Average each deployment within each minute
    # -----------------------------------------------------------------

    deployment_avg = (
        app_df.groupby(
            [
                "Minute",
                "Name",
            ],
            as_index=False,
        )["Pods"]
        .mean()
    )

    # -----------------------------------------------------------------
    # Total application replicas per minute
    # -----------------------------------------------------------------

    minute_total = (
        deployment_avg.groupby(
            "Minute",
            as_index=False,
        )["Pods"]
        .sum()
        .rename(
            columns={
                "Pods": "AverageReplicas"
            }
        )
    )

    # -----------------------------------------------------------------
    # Decision delta
    # -----------------------------------------------------------------

    minute_total["ReplicaDelta"] = (
        minute_total[
            "AverageReplicas"
        ].diff()
    )

    minute_total = (
        minute_total
        .dropna(
            subset=[
                "ReplicaDelta"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return minute_total


# ---------------------------------------------------------------------
# Average multiple runs
# ---------------------------------------------------------------------

def average_method_runs(
    csv_paths: list[Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate replica delta for each run independently,
    then average across runs at each minute.

    Returns:

        summary:
            Minute
            MeanReplicaDelta
            StdReplicaDelta
            MinReplicaDelta
            MaxReplicaDelta
            Runs

        all_runs:
            Run
            File
            Minute
            AverageReplicas
            ReplicaDelta
    """

    run_frames = []

    valid_run = 0

    for csv_path in csv_paths:

        try:
            df = load_replica_delta(
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

        df = df.copy()

        df.insert(
            0,
            "Run",
            valid_run,
        )

        df.insert(
            1,
            "File",
            str(csv_path),
        )

        run_frames.append(
            df
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
    # Average delta across runs
    # -----------------------------------------------------------------

    summary = (
        all_runs.groupby(
            "Minute",
            as_index=False,
        )
        .agg(
            MeanReplicaDelta=(
                "ReplicaDelta",
                "mean",
            ),

            StdReplicaDelta=(
                "ReplicaDelta",
                "std",
            ),

            MinReplicaDelta=(
                "ReplicaDelta",
                "min",
            ),

            MaxReplicaDelta=(
                "ReplicaDelta",
                "max",
            ),

            Runs=(
                "ReplicaDelta",
                "count",
            ),
        )
    )

    summary[
        "StdReplicaDelta"
    ] = (
        summary[
            "StdReplicaDelta"
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
            "No replica-delta data available."
        )

    # -----------------------------------------------------------------
    # Save averaged CSV
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
    # Common symmetric Y-axis
    # -----------------------------------------------------------------

    max_abs_delta = max(
        (
            df["MeanReplicaDelta"].abs()
            + df["StdReplicaDelta"]
        ).max()
        for df in series.values()
    )

    ylim = max(
        1.0,
        max_abs_delta * 1.08,
    )

    # -----------------------------------------------------------------
    # Create stacked plots
    # -----------------------------------------------------------------

    n = len(series)

    fig, axes = plt.subplots(
        nrows=n,
        ncols=1,
        sharex=True,
        sharey=True,
        figsize=(8.6, 1.8 * n),
    )

    if n == 1:
        axes = [axes]

    # -----------------------------------------------------------------
    # Plot in fixed order:
    #
    # Six CDT configurations in INPUT_FILES order
    # -----------------------------------------------------------------

    plot_index = 0

    for autoscaler in INPUT_FILES:

        if autoscaler not in series:
            continue

        ax = axes[
            plot_index
        ]

        plot_index += 1

        df = series[
            autoscaler
        ]

        minute = df[
            "Minute"
        ]

        mean = df[
            "MeanReplicaDelta"
        ]

        std = df[
            "StdReplicaDelta"
        ]

        # -------------------------------------------------------------
        # Mean delta
        # -------------------------------------------------------------

        ax.plot(
            minute,
            mean,
            color=COLORS[
                autoscaler
            ],
            linewidth=2.4,
        )

        # -------------------------------------------------------------
        # ±1 standard deviation
        # -------------------------------------------------------------

        ax.fill_between(
            minute,
            mean - std,
            mean + std,
            color=COLORS[
                autoscaler
            ],
            alpha=0.14,
            linewidth=0,
        )

        # -------------------------------------------------------------
        # Zero line
        # -------------------------------------------------------------

        ax.axhline(
            0,
            color="black",
            linestyle="--",
            linewidth=1.0,
        )

        # -------------------------------------------------------------
        # Method name
        # -------------------------------------------------------------

        ax.set_title(
            DISPLAY_NAMES[
                autoscaler
            ],
            loc="left",
            fontsize=13,
            fontweight="bold",
            pad=3,
        )

        # -------------------------------------------------------------
        # Grid
        # -------------------------------------------------------------

        ax.grid(
            axis="y",
            linestyle=":",
            linewidth=0.8,
            alpha=0.45,
        )

        # -------------------------------------------------------------
        # Same scale for every subplot
        # -------------------------------------------------------------

        ax.set_ylim(
            -ylim,
            ylim,
        )

        ax.set_xlim(
            0,
            MAX_MINUTE,
        )

        # -------------------------------------------------------------
        # Full border
        # -------------------------------------------------------------

        for spine in ax.spines.values():

            spine.set_visible(
                True
            )

            spine.set_linewidth(
                0.8
            )

    # -----------------------------------------------------------------
    # Shared labels
    # -----------------------------------------------------------------

    fig.supylabel(
        r"$\Delta$ Replicas",
        fontsize=14,
    )

    axes[-1].set_xlabel(
        "Elapsed Time (minutes)"
    )

    # -----------------------------------------------------------------
    # Title
    # -----------------------------------------------------------------

    fig.suptitle(
        "Change in Application Replica Count Over Time",
        fontsize=17,
    )

    # -----------------------------------------------------------------
    # Compact spacing
    # -----------------------------------------------------------------

    fig.subplots_adjust(
        hspace=0.15,
    )

    fig.tight_layout(
        rect=[
            0.03,
            0,
            1,
            0.97,
        ]
    )

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
                    "MeanReplicaDelta",
                    "StdReplicaDelta",
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
