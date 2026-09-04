from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ============================================================
# Plot style
# ============================================================

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 13,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 11,
})


# ============================================================
# Input files
# ============================================================

INPUT_FILES = {
    "queue-CDT120": [
        Path("queue-CDT120-1_stats_history.csv"),
        Path("queue-CDT120-2_stats_history.csv"),
        Path("queue-CDT120-3_stats_history.csv"),
        Path("queue-CDT120-4_stats_history.csv"),
        Path("queue-CDT120-5_stats_history.csv"),
    ],

    "queue-CDT300": [
        Path("queue-CDT300-1_stats_history.csv"),
        Path("queue-CDT300-2_stats_history.csv"),
        Path("queue-CDT300-3_stats_history.csv"),
        Path("queue-CDT300-4_stats_history.csv"),
        Path("queue-CDT300-5_stats_history.csv"),
    ],

    "hpa80-CDT120": [
        Path("hpa80-CDT120-1_stats_history.csv"),
        Path("hpa80-CDT120-2_stats_history.csv"),
        Path("hpa80-CDT120-3_stats_history.csv"),
        Path("hpa80-CDT120-4_stats_history.csv"),
        Path("hpa80-CDT120-5_stats_history.csv"),
    ],

    "hpa80-CDT300": [
        Path("hpa80-CDT300-1_stats_history.csv"),
        Path("hpa80-CDT300-2_stats_history.csv"),
        Path("hpa80-CDT300-3_stats_history.csv"),
        Path("hpa80-CDT300-4_stats_history.csv"),
        Path("hpa80-CDT300-5_stats_history.csv"),
    ],
}


DISPLAY_NAMES = {
    "queue-CDT120": "QUEUE-CDT120",
    "queue-CDT300": "QUEUE-CDT300",
    "hpa80-CDT120": "HPA80-CDT120",
    "hpa80-CDT300": "HPA80-CDT300",
}


COLORS = {
    "queue-CDT120": "tab:orange",
    "queue-CDT300": "tab:green",
    "hpa80-CDT120": "tab:blue",
    "hpa80-CDT300": "tab:red",
}


# ============================================================
# Locust percentile columns
# ============================================================

PERCENTILE_COLUMNS = [
    (["50%"], 0.50),
    (["66%"], 0.66),
    (["75%"], 0.75),
    (["80%"], 0.80),
    (["90%"], 0.90),
    (["95%"], 0.95),
    (["98%"], 0.98),
    (["99%"], 0.99),
    (["99.9%", "99.90%"], 0.999),
    (["99.99%"], 0.9999),
    (["100%"], 1.00),
]


# ============================================================
# Analysis settings
# ============================================================

SLO_MS = 500.0

# Which latency percentile to show in panel (a).
LATENCY_PERCENTILE = "95%"

# Use the last cumulative Locust snapshot in every elapsed-minute bucket.
TIME_BUCKET_SECONDS = 60


# ============================================================
# Outputs
# ============================================================

OUTPUT_PNG = Path("latency_and_slo_evolution_over_time.png")
OUTPUT_PDF = Path("latency_and_slo_evolution_over_time.pdf")

OUTPUT_RUN_CSV = Path("latency_and_slo_evolution_per_run.csv")
OUTPUT_SUMMARY_CSV = Path("latency_and_slo_evolution_summary.csv")


# ============================================================
# Helpers
# ============================================================

def as_float(value) -> float | None:
    value = pd.to_numeric(value, errors="coerce")

    if pd.isna(value):
        return None

    return float(value)


def first_existing_column(
    columns: pd.Index,
    candidates: list[str],
) -> str | None:

    for column in candidates:
        if column in columns:
            return column

    return None


def get_aggregated_rows(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep only Locust's cumulative Aggregated history rows.
    """

    if "Name" in df.columns:

        df = df.loc[
            df["Name"]
            .astype(str)
            .str.strip()
            .str.lower()
            == "aggregated"
        ].copy()

    if df.empty:
        raise ValueError(
            "No Aggregated rows found."
        )

    if "Timestamp" not in df.columns:
        raise ValueError(
            "Missing Timestamp column."
        )

    if "Total Request Count" not in df.columns:
        raise ValueError(
            "Missing Total Request Count column."
        )

    df["Timestamp"] = pd.to_numeric(
        df["Timestamp"],
        errors="coerce",
    )

    df["Total Request Count"] = pd.to_numeric(
        df["Total Request Count"],
        errors="coerce",
    )

    df = (
        df.dropna(
            subset=[
                "Timestamp",
                "Total Request Count",
            ]
        )
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    return df


def row_cdf_points(
    row: pd.Series,
    columns: pd.Index,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Reconstruct the cumulative CDF represented by one Locust history row.

    IMPORTANT:
    This is the cumulative distribution of all requests observed up to
    this row's timestamp. It is NOT an instantaneous interval distribution.
    """

    points: list[tuple[float, float]] = []

    # Approximate lower CDF anchor from the minimum latency.
    min_column = first_existing_column(
        columns,
        [
            "Total Min Response Time",
            "Min Response Time",
        ],
    )

    if min_column is not None:

        value = as_float(
            row[min_column]
        )

        if value is not None and value >= 0:
            points.append(
                (value, 0.0)
            )

    # Locust percentile points.
    for candidate_columns, probability in PERCENTILE_COLUMNS:

        selected_column = first_existing_column(
            columns,
            candidate_columns,
        )

        if selected_column is None:
            continue

        latency = as_float(
            row[selected_column]
        )

        if latency is None or latency < 0:
            continue

        points.append(
            (latency, probability)
        )

    # Approximate upper CDF anchor from the maximum latency.
    max_column = first_existing_column(
        columns,
        [
            "Total Max Response Time",
            "Max Response Time",
        ],
    )

    if max_column is not None:

        value = as_float(
            row[max_column]
        )

        if value is not None and value >= 0:
            points.append(
                (value, 1.0)
            )

    if not points:
        raise ValueError(
            "No usable percentile values in row."
        )

    points.sort(
        key=lambda point: (
            point[0],
            point[1],
        )
    )

    # Several percentiles can have the same rounded latency.
    # At that latency, keep the largest cumulative probability.
    collapsed: dict[float, float] = {}

    for latency, probability in points:

        collapsed[latency] = max(
            collapsed.get(latency, 0.0),
            probability,
        )

    latencies = np.asarray(
        list(collapsed.keys()),
        dtype=float,
    )

    probabilities = np.asarray(
        list(collapsed.values()),
        dtype=float,
    )

    probabilities = np.clip(
        probabilities,
        0.0,
        1.0,
    )

    probabilities = np.maximum.accumulate(
        probabilities
    )

    return latencies, probabilities


def estimate_cumulative_violation_rate(
    row: pd.Series,
    columns: pd.Index,
    slo_ms: float,
) -> float | None:
    """
    Estimate cumulative P(latency > SLO) for all requests seen up to this row.
    """

    request_count = as_float(
        row["Total Request Count"]
    )

    if request_count is None or request_count <= 0:
        return None

    try:
        latencies, probabilities = row_cdf_points(
            row,
            columns,
        )
    except ValueError:
        return None

    cdf_at_slo = float(
        np.interp(
            slo_ms,
            latencies,
            probabilities,
            left=0.0,
            right=1.0,
        )
    )

    violation_rate = (
        1.0 - cdf_at_slo
    )

    return float(
        np.clip(
            violation_rate,
            0.0,
            1.0,
        )
    )


def read_one_run(
    csv_path: Path,
) -> pd.DataFrame:
    """
    Read one Locust stats-history run and return one cumulative snapshot
    per elapsed minute.
    """

    if not csv_path.exists():
        raise FileNotFoundError(
            f"File not found: {csv_path}"
        )

    df = pd.read_csv(
        csv_path
    )

    if df.empty:
        raise ValueError(
            f"CSV is empty: {csv_path}"
        )

    history = get_aggregated_rows(
        df
    )

    if LATENCY_PERCENTILE not in history.columns:
        raise ValueError(
            f"Missing latency percentile column "
            f"{LATENCY_PERCENTILE!r}: {csv_path}"
        )

    start_timestamp = float(
        history["Timestamp"].iloc[0]
    )

    history["ElapsedSeconds"] = (
        history["Timestamp"]
        - start_timestamp
    )

    history["Minute"] = (
        history["ElapsedSeconds"]
        // TIME_BUCKET_SECONDS
    ).astype(int)

    history["SelectedLatency_ms"] = pd.to_numeric(
        history[LATENCY_PERCENTILE],
        errors="coerce",
    )

    history["CumulativeSLOViolationRate_percent"] = [
        (
            estimate_cumulative_violation_rate(
                row,
                history.columns,
                SLO_MS,
            )
            * 100.0
        )
        if estimate_cumulative_violation_rate(
            row,
            history.columns,
            SLO_MS,
        ) is not None
        else np.nan
        for _, row in history.iterrows()
    ]

    # --------------------------------------------------------
    # Use the final cumulative snapshot in each elapsed minute.
    # --------------------------------------------------------

    minute_df = (
        history.groupby(
            "Minute",
            as_index=False,
        )
        .tail(1)
        .copy()
    )

    minute_df = minute_df[
        [
            "Minute",
            "Timestamp",
            "Total Request Count",
            "SelectedLatency_ms",
            "CumulativeSLOViolationRate_percent",
        ]
    ]

    minute_df = (
        minute_df
        .dropna(
            subset=[
                "SelectedLatency_ms",
                "CumulativeSLOViolationRate_percent",
            ]
        )
        .sort_values("Minute")
        .reset_index(drop=True)
    )

    return minute_df


# ============================================================
# Main
# ============================================================

def main() -> None:

    all_runs: list[pd.DataFrame] = []

    # --------------------------------------------------------
    # Read each run independently
    # --------------------------------------------------------

    for method, csv_paths in INPUT_FILES.items():

        run_number = 0

        for csv_path in csv_paths:

            try:
                run_df = read_one_run(
                    csv_path
                )

            except (
                FileNotFoundError,
                ValueError,
            ) as exc:

                print(
                    f"[SKIP] {method}: "
                    f"{csv_path}: {exc}"
                )

                continue

            run_number += 1

            run_df["Method"] = method
            run_df["DisplayName"] = DISPLAY_NAMES[method]
            run_df["Run"] = run_number
            run_df["File"] = str(csv_path)

            all_runs.append(
                run_df
            )

    if not all_runs:
        raise RuntimeError(
            "No valid experiment data found."
        )

    run_df = pd.concat(
        all_runs,
        ignore_index=True,
    )

    run_df.to_csv(
        OUTPUT_RUN_CSV,
        index=False,
    )

    # --------------------------------------------------------
    # Mean ± std across repeated runs at each elapsed minute
    # --------------------------------------------------------

    summary_df = (
        run_df.groupby(
            [
                "Method",
                "DisplayName",
                "Minute",
            ],
            as_index=False,
        )
        .agg(
            MeanLatency_ms=(
                "SelectedLatency_ms",
                "mean",
            ),

            StdLatency_ms=(
                "SelectedLatency_ms",
                "std",
            ),

            MeanCumulativeSLOViolationRate_percent=(
                "CumulativeSLOViolationRate_percent",
                "mean",
            ),

            StdCumulativeSLOViolationRate_percent=(
                "CumulativeSLOViolationRate_percent",
                "std",
            ),

            Runs=(
                "Run",
                "count",
            ),
        )
    )

    summary_df[
        "StdLatency_ms"
    ] = (
        summary_df[
            "StdLatency_ms"
        ].fillna(0.0)
    )

    summary_df[
        "StdCumulativeSLOViolationRate_percent"
    ] = (
        summary_df[
            "StdCumulativeSLOViolationRate_percent"
        ].fillna(0.0)
    )

    order_map = {
        method: index
        for index, method
        in enumerate(INPUT_FILES)
    }

    summary_df["Order"] = (
        summary_df["Method"]
        .map(order_map)
    )

    summary_df = (
        summary_df
        .sort_values(
            [
                "Order",
                "Minute",
            ]
        )
        .drop(columns="Order")
        .reset_index(drop=True)
    )

    summary_df.to_csv(
        OUTPUT_SUMMARY_CSV,
        index=False,
    )

    methods = [
        method
        for method in INPUT_FILES
        if method in summary_df["Method"].unique()
    ]

    # ========================================================
    # Figure
    # ========================================================

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(12, 6),
    )

    ax_latency = axes[0]
    ax_slo = axes[1]

    # --------------------------------------------------------
    # (a) Latency percentile evolution
    # --------------------------------------------------------

    for method in methods:

        data = (
            summary_df.loc[
                summary_df["Method"] == method
            ]
            .sort_values("Minute")
        )

        x = data["Minute"].to_numpy()

        mean = data[
            "MeanLatency_ms"
        ].to_numpy()

        std = data[
            "StdLatency_ms"
        ].to_numpy()

        ax_latency.plot(
            x,
            mean,
            color=COLORS[method],
            linewidth=2.3,
            label=DISPLAY_NAMES[method],
        )

        ax_latency.fill_between(
            x,
            np.maximum(0.0, mean - std),
            mean + std,
            color=COLORS[method],
            alpha=0.15,
            linewidth=0,
        )

    ax_latency.axhline(
        SLO_MS,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label=f"SLO ({SLO_MS:g} ms)",
    )

    ax_latency.set_xlabel(
        "Elapsed Time (min)"
    )

    ax_latency.set_ylabel(
        f"{LATENCY_PERCENTILE} Latency (ms)"
    )

    ax_latency.set_title(
        f"(a) {LATENCY_PERCENTILE} Latency Evolution"
    )

    ax_latency.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.55,
    )

    ax_latency.legend(
        loc="upper left",
        frameon=True,
        framealpha=0.95,
        prop={
            "weight": "bold",
            "size": 10,
        },
    )

    # --------------------------------------------------------
    # (b) Cumulative SLO violation evolution
    # --------------------------------------------------------

    for method in methods:

        data = (
            summary_df.loc[
                summary_df["Method"] == method
            ]
            .sort_values("Minute")
        )

        x = data["Minute"].to_numpy()

        mean = data[
            "MeanCumulativeSLOViolationRate_percent"
        ].to_numpy()

        std = data[
            "StdCumulativeSLOViolationRate_percent"
        ].to_numpy()

        ax_slo.plot(
            x,
            mean,
            color=COLORS[method],
            linewidth=2.3,
            label=DISPLAY_NAMES[method],
        )

        ax_slo.fill_between(
            x,
            np.maximum(0.0, mean - std),
            np.minimum(100.0, mean + std),
            color=COLORS[method],
            alpha=0.15,
            linewidth=0,
        )

    ax_slo.set_xlabel(
        "Elapsed Time (min)"
    )

    ax_slo.set_ylabel(
        "Cumulative SLO Violation Rate (%)"
    )

    ax_slo.set_title(
        "(b) Cumulative SLO Violation Evolution"
    )

    ax_slo.set_ylim(
        bottom=0
    )

    ax_slo.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.55,
    )

    ax_slo.legend(
        loc="upper right",
        frameon=True,
        framealpha=0.95,
        prop={
            "weight": "bold",
            "size": 10,
        },
    )

    # --------------------------------------------------------
    # Full plot borders
    # --------------------------------------------------------

    for ax in axes:

        for spine in ax.spines.values():

            spine.set_visible(
                True
            )

            spine.set_linewidth(
                0.8
            )

    fig.tight_layout(
        w_pad=2.5
    )

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
        "=== Final cumulative values per run ==="
    )

    final_rows = (
        run_df
        .sort_values("Minute")
        .groupby(
            [
                "Method",
                "Run",
            ],
            as_index=False,
        )
        .tail(1)
    )

    print(
        final_rows[
            [
                "DisplayName",
                "Run",
                "Minute",
                "SelectedLatency_ms",
                "CumulativeSLOViolationRate_percent",
                "Total Request Count",
            ]
        ].to_string(
            index=False,
            float_format=lambda value: f"{value:.3f}",
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
        f"Saved: {OUTPUT_RUN_CSV}"
    )

    print(
        f"Saved: {OUTPUT_SUMMARY_CSV}"
    )

    plt.show()


if __name__ == "__main__":
    main()
