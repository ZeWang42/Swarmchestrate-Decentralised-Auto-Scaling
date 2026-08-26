from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
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
    "queue": Path("queue-2.csv"),
    "hpa80": Path("hpa80-1.csv"),
    "das": Path("das-1.csv"),
}

DISPLAY_NAMES = {
    "queue": "Queue-based",
    "hpa80": "HPA (80%)",
    "das": "DAS",
}

COLORS = {
    "queue": "tab:orange",
    "hpa80": "tab:green",
    "das": "tab:blue",
}

LATENCY_SCOPE = "http_p95_latency"
ROOT_SERVICE = "frontend"

OUTPUT_PNG = Path("latency_delta_over_time.png")
OUTPUT_PDF = Path("latency_delta_over_time.pdf")
OUTPUT_CSV = Path("latency_delta_over_time.csv")


def load_latency_delta(
    csv_path: Path,
    latency_scope: str,
    root_service: str,
) -> pd.DataFrame:
    """
    Read one monitoring CSV and calculate consecutive latency differences.

    Delta latency is:

        Delta L(t) = L(t) - L(t-1)

    Positive:
        latency increased.

    Negative:
        latency decreased.

    Zero:
        latency remained unchanged.
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
            f"{csv_path} is missing columns: {sorted(missing)}"
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

    # -----------------------------------------------------------------
    # Parse timestamps
    # -----------------------------------------------------------------

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

    if len(latency) < 2:
        raise ValueError(
            f"Not enough valid latency samples in {csv_path}"
        )

    # -----------------------------------------------------------------
    # Convert to elapsed time
    # -----------------------------------------------------------------

    first_timestamp = latency["Timestamp"].iloc[0]

    latency["Elapsed_seconds"] = (
        latency["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    latency["Elapsed_minutes"] = (
        latency["Elapsed_seconds"] / 60.0
    )

    # -----------------------------------------------------------------
    # Calculate delta latency
    #
    # Current - previous:
    #
    # positive -> latency increased
    # negative -> latency decreased
    # -----------------------------------------------------------------

    latency["LatencyDelta_ms"] = (
        latency["HTTP_LAT_ms"].diff()
    )

    # First sample has no previous value.
    latency = (
        latency
        .dropna(
            subset=["LatencyDelta_ms"]
        )
        .reset_index(drop=True)
    )

    return latency


def main() -> None:
    series: list[tuple[str, pd.DataFrame]] = []
    all_results: list[pd.DataFrame] = []

    # -----------------------------------------------------------------
    # Load data
    # -----------------------------------------------------------------

    for autoscaler, csv_path in INPUT_FILES.items():
        try:
            latency = load_latency_delta(
                csv_path=csv_path,
                latency_scope=LATENCY_SCOPE,
                root_service=ROOT_SERVICE,
            )

        except (FileNotFoundError, ValueError) as exc:
            print(
                f"[SKIP] {autoscaler}: {exc}"
            )
            continue

        series.append(
            (
                autoscaler,
                latency,
            )
        )

        output = latency[
            [
                "Timestamp",
                "Elapsed_minutes",
                "HTTP_LAT_ms",
                "LatencyDelta_ms",
            ]
        ].copy()

        output.insert(
            0,
            "Autoscaler",
            autoscaler,
        )

        all_results.append(output)

    if not series:
        raise RuntimeError(
            "No latency-delta series were plotted."
        )

    # -----------------------------------------------------------------
    # Save delta values
    # -----------------------------------------------------------------

    pd.concat(
        all_results,
        ignore_index=True,
    ).to_csv(
        OUTPUT_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Find common symmetric Y-axis
    #
    # Example:
    # largest positive = +180
    # largest negative = -140
    #
    # axis becomes approximately:
    # -190 to +190
    #
    # This makes positive and negative changes visually comparable.
    # -----------------------------------------------------------------

    max_abs_delta = max(
        latency["LatencyDelta_ms"]
        .abs()
        .max()
        for _, latency in series
    )

    y_limit = max_abs_delta * 1.08

    # -----------------------------------------------------------------
    # Create stacked figure
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
    # Plot
    # -----------------------------------------------------------------

    for ax, (autoscaler, latency) in zip(
        axes,
        series,
    ):
        ax.plot(
            latency["Elapsed_minutes"],
            latency["LatencyDelta_ms"],
            color=COLORS[autoscaler],
            linewidth=2.2,
        )

        # Zero line:
        # above = latency worsening
        # below = latency improving
        ax.axhline(
            y=0,
            color="black",
            linestyle="--",
            linewidth=1.1,
        )

        ax.set_title(
            DISPLAY_NAMES[autoscaler],
            loc="left",
            fontsize=13,
            fontweight="bold",
            pad=3,
        )

        ax.grid(
            axis="y",
            linestyle=":",
            linewidth=0.8,
            alpha=0.45,
        )

        ax.set_xlim(
            left=0,
        )

        ax.set_ylim(
            -y_limit,
            y_limit,
        )

        # Keep full box / ceiling
        ax.spines["top"].set_visible(True)
        ax.spines["right"].set_visible(True)

        for spine in ax.spines.values():
            spine.set_linewidth(0.8)

    # -----------------------------------------------------------------
    # Shared labels
    # -----------------------------------------------------------------

    fig.supylabel(
        r"$\Delta$ P95 Latency (ms)",
        fontsize=14,
    )

    axes[-1].set_xlabel(
        "Elapsed Time (minutes)"
    )

    # -----------------------------------------------------------------
    # Overall title
    # -----------------------------------------------------------------

    fig.suptitle(
        "Change in Application P95 Latency Over Time",
        fontsize=17,
        y=0.995,
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
