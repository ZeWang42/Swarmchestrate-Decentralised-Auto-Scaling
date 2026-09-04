from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Global plotting style
# ---------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 13,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 11,
})


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
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

    "hybrid-CDT120": [
        Path("hybrid-CDT120-1_stats_history.csv"),
        Path("hybrid-CDT120-2_stats_history.csv"),
        Path("hybrid-CDT120-3_stats_history.csv"),
        Path("hybrid-CDT120-4_stats_history.csv"),
        Path("hybrid-CDT120-5_stats_history.csv"),
    ],

    "hybrid-CDT300": [
        Path("hybrid-CDT300-1_stats_history.csv"),
        Path("hybrid-CDT300-2_stats_history.csv"),
        Path("hybrid-CDT300-3_stats_history.csv"),
        Path("hybrid-CDT300-4_stats_history.csv"),
        Path("hybrid-CDT300-5_stats_history.csv"),
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

X_LABELS = {
    "queue-CDT120": "Queue\nCDT120",
    "queue-CDT300": "Queue\nCDT300",
    "hpa80-CDT120": "HPA80\nCDT120",
    "hpa80-CDT300": "HPA80\nCDT300",
    "hybrid-CDT120": "Hybrid\nCDT120",
    "hybrid-CDT300": "Hybrid\nCDT300",
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

# ---------------------------------------------------------------------
# Locust percentile columns
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Experiment settings
# ---------------------------------------------------------------------

SLO_MS = 500.0
MAX_LATENCY_MS = 1500.0


# ---------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------

OUTPUT_PNG = Path("latency_cdf_and_slo_violation.png")
OUTPUT_PDF = Path("latency_cdf_and_slo_violation.pdf")

OUTPUT_RUN_CSV = Path("slo_violation_per_run.csv")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def get_aggregated_row(
    df: pd.DataFrame,
) -> pd.Series:
    """
    Return the cumulative Locust Aggregated snapshot at or before
    MAX_MINUTE elapsed minutes.
    """

    if "Name" in df.columns:
        aggregated = df.loc[
            df["Name"]
            .astype(str)
            .str.strip()
            .str.lower()
            == "aggregated"
        ].copy()
    else:
        aggregated = df.copy()

    if aggregated.empty:
        raise ValueError(
            "No Aggregated rows found."
        )

    if "Timestamp" not in aggregated.columns:
        raise ValueError(
            "Timestamp column is required to enforce the minute cutoff."
        )

    aggregated["Timestamp"] = pd.to_numeric(
        aggregated["Timestamp"],
        errors="coerce",
    )

    aggregated = (
        aggregated
        .dropna(subset=["Timestamp"])
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    if aggregated.empty:
        raise ValueError(
            "No valid Aggregated timestamps found."
        )

    start_timestamp = float(
        aggregated["Timestamp"].iloc[0]
    )

    aggregated["ElapsedSeconds"] = (
        aggregated["Timestamp"]
        - start_timestamp
    )

    aggregated["Minute"] = (
        aggregated["ElapsedSeconds"] // 60
    ).astype(int)

    eligible = aggregated.loc[
        aggregated["Minute"] <= MAX_MINUTE
    ]

    if eligible.empty:
        raise ValueError(
            f"No Aggregated snapshot available by minute {MAX_MINUTE}."
        )

    return eligible.iloc[-1]


def read_percentiles(
    csv_path: Path,
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    Read latency percentile points from one Locust stats CSV.

    Returns:
        latencies
        cumulative probabilities
        total request count
    """

    if not csv_path.exists():
        raise FileNotFoundError(
            f"File not found: {csv_path}"
        )

    df = pd.read_csv(csv_path)

    if df.empty:
        raise ValueError(
            f"CSV is empty: {csv_path}"
        )

    row = get_aggregated_row(df)

    # Locust *_stats.csv normally uses "Request Count".
    # Some other exports use "Total Request Count", so accept both.
    request_count_column = next(
        (
            column
            for column in [
                "Request Count",
                "Total Request Count",
            ]
            if column in df.columns
        ),
        None,
    )

    if request_count_column is None:
        raise ValueError(
            f"No request-count column found in {csv_path}"
        )

    request_count = pd.to_numeric(
        row[request_count_column],
        errors="coerce",
    )

    if pd.isna(request_count):
        raise ValueError(
            f"Invalid request count in {csv_path}"
        )

    request_count = int(request_count)

    latencies = []
    probabilities = []

    for possible_columns, probability in PERCENTILE_COLUMNS:

        selected_column = next(
            (
                column
                for column in possible_columns
                if column in df.columns
            ),
            None,
        )

        if selected_column is None:
            continue

        latency = pd.to_numeric(
            row[selected_column],
            errors="coerce",
        )

        if pd.isna(latency):
            continue

        latency = min(
            float(latency),
            MAX_LATENCY_MS,
        )

        latencies.append(
            latency
        )

        probabilities.append(
            probability
        )

    if not latencies:
        raise ValueError(
            f"No supported percentile columns found in {csv_path}"
        )

    # -----------------------------------------------------------------
    # Sort by latency
    # -----------------------------------------------------------------

    points = sorted(
        zip(
            latencies,
            probabilities,
        ),
        key=lambda point: (
            point[0],
            point[1],
        ),
    )

    # -----------------------------------------------------------------
    # Collapse duplicate latency values
    # -----------------------------------------------------------------

    unique_points = {}

    for latency, probability in points:

        unique_points[latency] = max(
            unique_points.get(
                latency,
                0.0,
            ),
            probability,
        )

    latency_array = np.array(
        list(
            unique_points.keys()
        ),
        dtype=float,
    )

    probability_array = np.array(
        list(
            unique_points.values()
        ),
        dtype=float,
    )

    return (
        latency_array,
        probability_array,
        request_count,
    )


def estimate_violation_rate(
    latencies: np.ndarray,
    probabilities: np.ndarray,
    slo_ms: float,
) -> float:
    """
    Estimate:

        P(latency > SLO)

    using linear interpolation between percentile points.
    """

    if len(latencies) != len(probabilities):
        raise ValueError(
            "Latency and probability arrays must match."
        )

    if len(latencies) == 0:
        raise ValueError(
            "No percentile points supplied."
        )

    # -----------------------------------------------------------------
    # SLO below lowest recorded percentile latency
    # -----------------------------------------------------------------

    if slo_ms < latencies[0]:

        return max(
            0.0,
            min(
                1.0,
                1.0 - probabilities[0],
            ),
        )

    # -----------------------------------------------------------------
    # SLO >= maximum recorded latency
    # -----------------------------------------------------------------

    if slo_ms >= latencies[-1]:
        return 0.0

    # -----------------------------------------------------------------
    # Find interval containing SLO
    # -----------------------------------------------------------------

    for i in range(
        len(latencies) - 1
    ):

        left_latency = latencies[i]
        right_latency = latencies[i + 1]

        left_probability = probabilities[i]
        right_probability = probabilities[i + 1]

        if (
            left_latency
            <= slo_ms
            <= right_latency
        ):

            if right_latency == left_latency:

                cdf_at_slo = max(
                    left_probability,
                    right_probability,
                )

            else:

                fraction = (
                    slo_ms - left_latency
                ) / (
                    right_latency - left_latency
                )

                cdf_at_slo = (
                    left_probability
                    + fraction
                    * (
                        right_probability
                        - left_probability
                    )
                )

            violation_rate = (
                1.0 - cdf_at_slo
            )

            return max(
                0.0,
                min(
                    1.0,
                    violation_rate,
                ),
            )

    return 0.0


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    # -----------------------------------------------------------------
    # Common latency grid
    # -----------------------------------------------------------------

    x_grid = np.linspace(
        0,
        MAX_LATENCY_MS,
        1200,
    )

    method_curves = {}

    run_rows = []

    # -----------------------------------------------------------------
    # Process every run
    # -----------------------------------------------------------------

    for method, csv_paths in INPUT_FILES.items():

        curves = []
        run_number = 0

        for csv_path in csv_paths:

            try:

                latencies, probabilities, request_count = (
                    read_percentiles(
                        csv_path
                    )
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

            # ---------------------------------------------------------
            # Interpolate run CDF on common latency grid
            # ---------------------------------------------------------

            curve = np.interp(
                x_grid,
                latencies,
                probabilities,
                left=0.0,
                right=1.0,
            )

            curves.append(
                curve
            )

            # ---------------------------------------------------------
            # SLO violation rate for this run
            # ---------------------------------------------------------

            violation_rate = (
                estimate_violation_rate(
                    latencies,
                    probabilities,
                    SLO_MS,
                )
                * 100.0
            )

            run_rows.append({
                "Method":
                    method,

                "DisplayName":
                    DISPLAY_NAMES[method],

                "Run":
                    run_number,

                "File":
                    str(csv_path),

                "SLOViolationRate_percent":
                    violation_rate,

                "TotalRequestCount":
                    request_count,
            })

        if curves:

            method_curves[
                method
            ] = np.vstack(
                curves
            )

    if not method_curves:
        raise RuntimeError(
            "No valid experiment data found."
        )

    # -----------------------------------------------------------------
    # Per-run SLO data
    # -----------------------------------------------------------------

    run_df = pd.DataFrame(
        run_rows
    )

    run_df.to_csv(
        OUTPUT_RUN_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Available methods
    # -----------------------------------------------------------------

    methods = [
        method
        for method in INPUT_FILES
        if method in method_curves
    ]

    # -----------------------------------------------------------------
    # SLO violation summary
    # -----------------------------------------------------------------

    violation_summary = (
        run_df.groupby(
            [
                "Method",
                "DisplayName",
            ],
            as_index=False,
        )
        .agg(
            MeanViolationRate=(
                "SLOViolationRate_percent",
                "mean",
            ),

            StdViolationRate=(
                "SLOViolationRate_percent",
                "std",
            ),

            MinViolationRate=(
                "SLOViolationRate_percent",
                "min",
            ),

            MaxViolationRate=(
                "SLOViolationRate_percent",
                "max",
            ),

            MeanRequestCount=(
                "TotalRequestCount",
                "mean",
            ),

            StdRequestCount=(
                "TotalRequestCount",
                "std",
            ),

            MinRequestCount=(
                "TotalRequestCount",
                "min",
            ),

            MaxRequestCount=(
                "TotalRequestCount",
                "max",
            ),

            Runs=(
                "SLOViolationRate_percent",
                "count",
            ),
        )
    )

    violation_summary[
        "StdViolationRate"
    ] = (
        violation_summary[
            "StdViolationRate"
        ].fillna(0.0)
    )

    violation_summary[
        "StdRequestCount"
    ] = (
        violation_summary[
            "StdRequestCount"
        ].fillna(0.0)
    )

    order_map = {
        method: i
        for i, method
        in enumerate(
            INPUT_FILES
        )
    }

    violation_summary[
        "Order"
    ] = (
        violation_summary[
            "Method"
        ].map(
            order_map
        )
    )

    violation_summary = (
        violation_summary
        .sort_values(
            "Order"
        )
        .reset_index(
            drop=True
        )
    )

    # =================================================================
    # Combined figure: latency CDF, SLO violation, and request count.
    # =================================================================

    fig, axes = plt.subplots(
        nrows=1,
        ncols=3,
        figsize=(18, 5),
    )

    ax_cdf = axes[0]
    ax_slo = axes[1]
    ax_requests = axes[2]

    # =================================================================
    # LEFT: Latency CDF
    # =================================================================

    for method in methods:

        curves = method_curves[
            method
        ]

        mean_curve = curves.mean(
            axis=0
        )

        if curves.shape[0] > 1:

            std_curve = curves.std(
                axis=0,
                ddof=1,
            )

        else:

            std_curve = np.zeros_like(
                mean_curve
            )

        lower = np.clip(
            mean_curve - std_curve,
            0.0,
            1.0,
        )

        upper = np.clip(
            mean_curve + std_curve,
            0.0,
            1.0,
        )

        # Mean
        ax_cdf.plot(
            x_grid,
            mean_curve,
            color=COLORS[method],
            linewidth=2.5,
            label=DISPLAY_NAMES[
                method
            ],
        )

        # Standard deviation band
        ax_cdf.fill_between(
            x_grid,
            lower,
            upper,
            color=COLORS[method],
            alpha=0.15,
            linewidth=0,
        )

    # -----------------------------------------------------------------
    # SLO reference
    # -----------------------------------------------------------------

    ax_cdf.axvline(
        SLO_MS,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label=f"SLO ({SLO_MS:g} ms)",
    )

    # -----------------------------------------------------------------
    # Percentile guide lines
    # -----------------------------------------------------------------

    for probability, label in [
        (0.90, "P90"),
        (0.95, "P95"),
        (0.99, "P99"),
    ]:

        ax_cdf.axhline(
            probability,
            color="gray",
            linestyle="--",
            linewidth=0.7,
            alpha=0.4,
        )

        ax_cdf.text(
            15,
            probability + 0.003,
            label,
            fontsize=10,
            color="gray",
        )

    ax_cdf.set_xlabel(
        "Latency (ms)"
    )

    ax_cdf.set_ylabel(
        "Cumulative Probability"
    )

    ax_cdf.set_title(
        "(a) End-to-End Latency CDF"
    )

    ax_cdf.set_xlim(
        0,
        MAX_LATENCY_MS,
    )

    ax_cdf.set_ylim(
        0.48,
        1.01,
    )

    ax_cdf.set_yticks([
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
        0.95,
        0.99,
        1.00,
    ])

    ax_cdf.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.55,
    )

    ax_cdf.legend(
        loc="lower right",
        frameon=True,
        framealpha=0.95,
        prop={
            "weight": "bold",
            "size": 11,
        },
    )

    # =================================================================
    # RIGHT: SLO violation
    # =================================================================

    x = np.arange(
        len(
            violation_summary
        )
    )

    bars = ax_slo.bar(
        x,
        violation_summary[
            "MeanViolationRate"
        ],
        color=[
            COLORS[method]
            for method in violation_summary[
                "Method"
            ]
        ],
        edgecolor="black",
        linewidth=0.8,
        width=0.60,
        zorder=3,
    )

    # -----------------------------------------------------------------
    # Standard deviation
    # -----------------------------------------------------------------

    ax_slo.errorbar(
        x,
        violation_summary[
            "MeanViolationRate"
        ],
        yerr=violation_summary[
            "StdViolationRate"
        ],
        fmt="none",
        color="black",
        linewidth=1.2,
        capsize=5,
        zorder=4,
    )

    # -----------------------------------------------------------------
    # Individual experiment runs
    # -----------------------------------------------------------------

    rng = np.random.default_rng(
        42
    )

    method_positions = {
        method: i
        for i, method
        in enumerate(
            violation_summary[
                "Method"
            ]
        )
    }

    for method in violation_summary[
        "Method"
    ]:

        values = run_df.loc[
            run_df["Method"]
            == method,
            "SLOViolationRate_percent",
        ].to_numpy()

        jitter = rng.uniform(
            -0.055,
            0.055,
            size=len(values),
        )

        ax_slo.scatter(
            (
                method_positions[
                    method
                ]
                + jitter
            ),
            values,
            color="black",
            s=30,
            zorder=5,
        )

    # -----------------------------------------------------------------
    # Mean labels above bars
    # -----------------------------------------------------------------

    maximum = max(
        (
            violation_summary[
                "MeanViolationRate"
            ]
            + violation_summary[
                "StdViolationRate"
            ]
        ).max(),

        run_df[
            "SLOViolationRate_percent"
        ].max(),

        1.0,
    )

    label_offset = (
        maximum * 0.025
    )

    for bar, value in zip(
        bars,
        violation_summary[
            "MeanViolationRate"
        ],
    ):

        ax_slo.text(
            (
                bar.get_x()
                + bar.get_width() / 2
            ),
            (
                bar.get_height()
                + label_offset
            ),
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax_slo.set_xticks(
        x
    )

    ax_slo.set_xticklabels(
        [
            X_LABELS[name]
            for name in violation_summary["Method"]
        ],
        #fontweight="bold",
    )

    ax_slo.set_ylabel(
        "SLO Violation Rate (%)"
    )

    ax_slo.set_title(
        "(b) SLO Violation Rate"
    )

    ax_slo.set_ylim(
        0,
        maximum * 1.18,
    )

    ax_slo.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.55,
        zorder=0,
    )

    # =================================================================
    # RIGHT: Total request count
    # =================================================================

    request_bars = ax_requests.bar(
        x,
        violation_summary[
            "MeanRequestCount"
        ],
        color=[
            COLORS[method]
            for method in violation_summary[
                "Method"
            ]
        ],
        edgecolor="black",
        linewidth=0.8,
        width=0.60,
        zorder=3,
    )

    ax_requests.errorbar(
        x,
        violation_summary[
            "MeanRequestCount"
        ],
        yerr=violation_summary[
            "StdRequestCount"
        ],
        fmt="none",
        color="black",
        linewidth=1.2,
        capsize=5,
        zorder=4,
    )

    # Plot every run as a black point, matching the SLO panel.
    request_rng = np.random.default_rng(42)

    for method in violation_summary[
        "Method"
    ]:

        values = run_df.loc[
            run_df["Method"] == method,
            "TotalRequestCount",
        ].to_numpy()

        jitter = request_rng.uniform(
            -0.055,
            0.055,
            size=len(values),
        )

        ax_requests.scatter(
            method_positions[method] + jitter,
            values,
            color="black",
            s=30,
            zorder=5,
        )

    request_maximum = max(
        (
            violation_summary[
                "MeanRequestCount"
            ]
            + violation_summary[
                "StdRequestCount"
            ]
        ).max(),
        run_df[
            "TotalRequestCount"
        ].max(),
        1.0,
    )

    request_label_offset = request_maximum * 0.025

    # Put the exact mean request count above each bar, e.g. 417,170.
    for bar, value in zip(
        request_bars,
        violation_summary[
            "MeanRequestCount"
        ],
    ):

        ax_requests.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + request_label_offset,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax_requests.set_xticks(x)

    ax_requests.set_xticklabels(
        [
            X_LABELS[name]
            for name in violation_summary["Method"]
        ]
    )

    ax_requests.set_ylabel(
        "Total Request Count"
    )

    ax_requests.set_title(
        "(c) Total Requests"
    )

    ax_requests.set_ylim(
        0,
        request_maximum * 1.18,
    )

    ax_requests.yaxis.set_major_formatter(
        StrMethodFormatter("{x:,.0f}")
    )

    ax_requests.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.55,
        zorder=0,
    )

    # -----------------------------------------------------------------
    # Full borders
    # -----------------------------------------------------------------

    for ax in axes:

        for spine in ax.spines.values():

            spine.set_visible(
                True
            )

            spine.set_linewidth(
                0.8
            )

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------

    fig.tight_layout(
        w_pad=2.5
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
    # Print summary
    # -----------------------------------------------------------------

    print()
    print(
        "=== Per-run SLO violation ==="
    )

    print(
        run_df.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print()
    print(
        "=== SLO violation summary ==="
    )

    print(
        violation_summary[
            [
                "DisplayName",
                "Runs",
                "MeanViolationRate",
                "StdViolationRate",
                "MinViolationRate",
                "MaxViolationRate",
                "MeanRequestCount",
                "StdRequestCount",
                "MinRequestCount",
                "MaxRequestCount",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
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

    plt.show()


if __name__ == "__main__":
    main()
