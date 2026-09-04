from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ---------------------------------------------------------------------
# Global plotting style
# -------------------------------------------f--------------------------

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

    "hpa60-CDT120": [
        Path("hpa60-CDT120-1.csv"),
        Path("hpa60-CDT120-2.csv"),
        Path("hpa60-CDT120-3.csv"),
        Path("hpa60-CDT120-4.csv"),
        Path("hpa60-CDT120-5.csv"),
    ],

    "hpa60-CDT300": [
        Path("hpa60-CDT300-1.csv"),
        Path("hpa60-CDT300-2.csv"),
        Path("hpa60-CDT300-3.csv"),
        Path("hpa60-CDT300-4.csv"),
        Path("hpa60-CDT300-5.csv"),
    ],

}

DISPLAY_NAMES = {
    "queue-CDT120": "Queue-CDT120",
    "queue-CDT300": "Queue-CDT300",
    "hpa80-CDT120": "HPA80-CDT120",
    "hpa80-CDT300": "HPA80-CDT300",
    "hpa60-CDT120": "hpa60-CDT120",
    "hpa60-CDT300": "hpa60-CDT300",
}

COLORS = {
    "queue-CDT120": "tab:orange",
    "queue-CDT300": "tab:green",
    "hpa80-CDT120": "tab:blue",
    "hpa80-CDT300": "tab:red",
    "hpa60-CDT120": "tab:purple",
    "hpa60-CDT300": "tab:brown",
}

MAX_MINUTE = 71

LATENCY_SCOPE = "http_p95_latency"

ROOT_SERVICE = "frontend"

SLO_MS: float | None = 500

OUTPUT_PNG = Path("latency_over_time_average.png")
OUTPUT_PDF = Path("latency_over_time_average.pdf")
OUTPUT_CSV = Path("latency_over_time_average.csv")


def load_latency(
    csv_path: Path,
    latency_scope: str,
    root_service: str,
) -> pd.DataFrame:
    """
    Read one monitoring CSV and return elapsed minute and latency.
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
        "HTTP_LAT_ms",
    }

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            f"{csv_path} is missing columns: "
            f"{sorted(missing)}"
        )

    latency = df.loc[
        (df["Scope"] == latency_scope)
        & (df["Name"] == root_service),
        [
            "Timestamp",
            "HTTP_LAT_ms",
        ],
    ].copy()

    if latency.empty:
        raise ValueError(
            f"No rows found in {csv_path} for "
            f"Scope={latency_scope!r}, "
            f"Name={root_service!r}"
        )

    latency["Timestamp"] = pd.to_datetime(
        latency["Timestamp"],
        format="mixed",
        dayfirst=True,
        errors="coerce",
    )

    latency["HTTP_LAT_ms"] = pd.to_numeric(
        latency["HTTP_LAT_ms"],
        errors="coerce",
    )

    latency = (
        latency
        .dropna(
            subset=[
                "Timestamp",
                "HTTP_LAT_ms",
            ]
        )
        .sort_values("Timestamp")
        .drop_duplicates(
            subset=["Timestamp"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    if latency.empty:
        raise ValueError(
            f"No valid latency measurements remain in {csv_path}"
        )

    first_timestamp = latency["Timestamp"].iloc[0]

    latency["Elapsed_seconds"] = (
        latency["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    latency["Elapsed_minutes"] = (
        latency["Elapsed_seconds"] / 60.0
    )

    return latency[
        [
            "Elapsed_minutes",
            "HTTP_LAT_ms",
        ]
    ]


def average_method_runs(
    csv_paths: list[Path],
    latency_scope: str,
    root_service: str,
) -> pd.DataFrame:
    """
    Load all runs for one autoscaler and average latency over time.

    Each run is first converted to elapsed minutes.

    To make runs directly comparable, latency is averaged within each
    integer elapsed minute before combining runs.

    Final columns:
        Minute
        MeanLatency_ms
        StdLatency_ms
        Runs
    """

    runs = []

    for run_index, csv_path in enumerate(
        csv_paths,
        start=1,
    ):
        try:
            latency = load_latency(
                csv_path=csv_path,
                latency_scope=latency_scope,
                root_service=root_service,
            )

        except (FileNotFoundError, ValueError) as exc:
            print(
                f"[SKIP RUN] {csv_path}: {exc}"
            )
            continue

        # -------------------------------------------------------------
        # Convert raw observations into one average value per minute
        # for this run.
        # -------------------------------------------------------------

        latency["Minute"] = (
            latency["Elapsed_minutes"] // 1
        ).astype(int)


        # Keep only minute 0 through minute 71.
        latency = latency.loc[
            latency["Minute"] <= MAX_MINUTE
        ].copy()
        run_minute = (
            latency.groupby(
                "Minute",
                as_index=False,
            )["HTTP_LAT_ms"]
            .mean()
            .rename(
                columns={
                    "HTTP_LAT_ms": "Latency_ms"
                }
            )
        )

        run_minute["Run"] = run_index

        runs.append(
            run_minute
        )

    if not runs:
        raise ValueError(
            "No valid runs available."
        )

    all_runs = pd.concat(
        runs,
        ignore_index=True,
    )

    # -------------------------------------------------------------
    # Average across experiment runs
    # -------------------------------------------------------------

    averaged = (
        all_runs.groupby(
            "Minute",
            as_index=False,
        )
        .agg(
            MeanLatency_ms=(
                "Latency_ms",
                "mean",
            ),
            StdLatency_ms=(
                "Latency_ms",
                "std",
            ),
            Runs=(
                "Latency_ms",
                "count",
            ),
        )
    )

    # std is NaN if only one run contributes to a minute
    averaged["StdLatency_ms"] = (
        averaged["StdLatency_ms"]
        .fillna(0.0)
    )

    return averaged


def main() -> None:
    series = []
    all_results = []

    # -----------------------------------------------------------------
    # Average runs for each method
    # -----------------------------------------------------------------

    for label, csv_paths in INPUT_FILES.items():
        try:
            latency = average_method_runs(
                csv_paths=csv_paths,
                latency_scope=LATENCY_SCOPE,
                root_service=ROOT_SERVICE,
            )

        except ValueError as exc:
            print(
                f"[SKIP] {label}: {exc}"
            )
            continue

        series.append(
            (
                label,
                latency,
            )
        )

        output = latency.copy()

        output.insert(
            0,
            "Method",
            label,
        )

        all_results.append(
            output
        )

    if not series:
        raise RuntimeError(
            "No latency series were plotted."
        )

    # -----------------------------------------------------------------
    # Save averaged values
    # -----------------------------------------------------------------

    pd.concat(
        all_results,
        ignore_index=True,
    ).to_csv(
        OUTPUT_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Common Y-axis
    # -----------------------------------------------------------------

    max_latency = max(
        latency["MeanLatency_ms"].max()
        for _, latency in series
    )

    y_max = max_latency * 1.08

    if SLO_MS is not None:
        y_max = max(
            y_max,
            SLO_MS * 1.08,
        )

    # -----------------------------------------------------------------
    # Stacked plots
    # -----------------------------------------------------------------

    n = len(series)

    fig, axes = plt.subplots(
        nrows=n,
        ncols=1,
        sharex=True,
        sharey=True,
        figsize=(8.4, 1.9 * n),
    )

    if n == 1:
        axes = [axes]

    percentile = (
        LATENCY_SCOPE
        .replace("http_", "")
        .replace("_latency", "")
        .upper()
    )

    # -----------------------------------------------------------------
    # Plot averaged latency
    # -----------------------------------------------------------------

    for ax, (label, latency) in zip(
        axes,
        series,
    ):
        ax.plot(
            latency["Minute"],
            latency["MeanLatency_ms"],
            color=COLORS[label],
            linewidth=2.2,
        )

        # Optional variability band across runs
        ax.fill_between(
            latency["Minute"],
            (
                latency["MeanLatency_ms"]
                - latency["StdLatency_ms"]
            ),
            (
                latency["MeanLatency_ms"]
                + latency["StdLatency_ms"]
            ),
            color=COLORS[label],
            alpha=0.15,
            linewidth=0,
        )

        if SLO_MS is not None:
            ax.axhline(
                y=SLO_MS,
                color="black",
                linestyle="--",
                linewidth=1.5,
            )

        ax.set_title(
            DISPLAY_NAMES[label],
            loc="left",
            fontsize=14,
            fontweight="bold",
            pad=4,
        )

        ax.grid(
            True,
            linestyle=":",
            linewidth=0.8,
            alpha=0.6,
        )

        ax.set_xlim(
            0,
            MAX_MINUTE,
        )

        ax.set_ylim(
            0,
            y_max,
        )

    # -----------------------------------------------------------------
    # Shared labels
    # -----------------------------------------------------------------

    fig.supylabel(
        f"{percentile} Latency (ms)",
        fontsize=14,
    )

    axes[-1].set_xlabel(
        "Elapsed Time (minutes)"
    )

    # -----------------------------------------------------------------
    # Title
    # -----------------------------------------------------------------

    fig.suptitle(
        f"Average Application {percentile} Latency over Time",
        fontsize=18,
        y=0.995,
    )

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------

    fig.subplots_adjust(
        hspace=0.16,
    )

    fig.tight_layout(
        rect=[
            0,
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
