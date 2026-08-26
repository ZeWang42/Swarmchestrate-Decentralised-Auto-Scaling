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

INPUT_FILES = {
    "queue": Path("queue-2.csv"),
    "hpa80": Path("hpa80-2.csv"),
    "das": Path("das-1.csv"),
}

COLORS = {
    "queue": "tab:orange",
    "hpa80": "tab:green",
    "das": "tab:blue",
}

LATENCY_SCOPE = "http_p95_latency"

ROOT_SERVICE = "frontend"

SLO_MS: float | None = 500

OUTPUT_PNG = Path("latency_over_time.png")
OUTPUT_PDF = Path("latency_over_time.pdf")


def load_latency(
    csv_path: Path,
    latency_scope: str,
    root_service: str,
) -> pd.DataFrame:
    """Read one monitoring CSV and return elapsed time and latency."""

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
        ["Timestamp", "HTTP_LAT_ms"],
    ].copy()

    if latency.empty:
        available_scopes = sorted(
            df["Scope"]
            .dropna()
            .astype(str)
            .unique()
        )

        raise ValueError(
            f"No rows found in {csv_path} for "
            f"Scope={latency_scope!r}, "
            f"Name={root_service!r}.\n"
            f"Available scopes: {available_scopes}"
        )

    latency["Timestamp"] = pd.to_datetime(
        latency["Timestamp"],
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

    return latency


def main() -> None:
    # -------------------------------------------------------------
    # Load all datasets first
    # -------------------------------------------------------------

    series = []

    for label, csv_path in INPUT_FILES.items():
        try:
            latency = load_latency(
                csv_path=csv_path,
                latency_scope=LATENCY_SCOPE,
                root_service=ROOT_SERVICE,
            )

        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {label}: {exc}")
            continue

        series.append(
            (label, latency)
        )

    if not series:
        raise RuntimeError(
            "No latency series were plotted. "
            "Check filenames, LATENCY_SCOPE, "
            "and ROOT_SERVICE."
        )

    # -------------------------------------------------------------
    # Calculate common Y-axis limit
    # -------------------------------------------------------------

    max_latency = max(
        latency["HTTP_LAT_ms"].max()
        for _, latency in series
    )

    y_max = max_latency * 1.08

    if SLO_MS is not None:
        y_max = max(
            y_max,
            SLO_MS * 1.08,
        )

    # -------------------------------------------------------------
    # Create vertically stacked plots
    #
    # sharex=True  -> same time axis
    # sharey=True  -> same latency scale
    # -------------------------------------------------------------

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

    for ax, (label, latency) in zip(axes, series):
        ax.plot(
            latency["Elapsed_minutes"],
            latency["HTTP_LAT_ms"],
            color=COLORS[label],
            linewidth=2.1,
        )

        if SLO_MS is not None:
            ax.axhline(
                y=SLO_MS,
                color="black",
                linestyle="--",
                linewidth=1.5,
            )

        ax.set_title(
            label.upper(),
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

        ax.set_ylim(0, y_max)
        ax.set_xlim(left=0)


    # One shared Y-axis label
    fig.supylabel(
        f"{percentile} Latency (ms)",
        fontsize=14,
    )

    # One shared X-axis label
    axes[-1].set_xlabel(
        "Elapsed Time (minutes)"
    )
    # -------------------------------------------------------------
    # Shared X-axis
    # -------------------------------------------------------------

    axes[-1].set_xlabel(
        "Elapsed Time (minutes)"
    )

    # -------------------------------------------------------------
    # Overall title
    # -------------------------------------------------------------

    fig.suptitle(
        f"Application {percentile} Latency over Time",
        fontsize=18,
        y=0.995,
    )

    # -------------------------------------------------------------
    # Compact subplot spacing
    # -------------------------------------------------------------

    fig.subplots_adjust(
        hspace=0.16,
    )

    fig.tight_layout(
        rect=[0, 0, 1, 0.97]
    )

    # -------------------------------------------------------------
    # Save
    # -------------------------------------------------------------

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

    plt.show()


if __name__ == "__main__":
    main()
