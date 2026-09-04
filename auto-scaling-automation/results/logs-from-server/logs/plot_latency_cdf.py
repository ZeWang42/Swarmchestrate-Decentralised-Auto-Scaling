from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ---------------------------------------------------------------------
# Global plotting style
# ---------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 17,
    "axes.titlesize": 21,
    "axes.labelsize": 19,
    "xtick.labelsize": 17,
    "ytick.labelsize": 17,
    "legend.fontsize": 16,
})


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

DATA_DIR = Path(".")

FILES = {
    "DAS": ["das_stats.csv"],
    "HPA-50": ["hpa50_stats.csv"],
    "HPA-80": ["hpa80_stats.csv"],
    "PBScaler": ["pbscaler_stats.csv"],
}

COLORS = {
    "DAS": "tab:blue",
    "HPA-50": "tab:orange",
    "HPA-80": "tab:green",
    "PBScaler": "tab:red",
}

# Locust versions may use either "99.9%" or "99.90%".
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

MAX_LATENCY_MS = 1500
SLO_MS = 500

OUTPUT_PDF = Path("latency_cdf.pdf")
OUTPUT_PNG = Path("latency_cdf.png")


def get_aggregated_row(df: pd.DataFrame) -> pd.Series:
    """Return the Locust Aggregated row, or the last row as fallback."""

    if "Name" in df.columns:
        aggregated = df[
            df["Name"].astype(str).str.strip().str.lower()
            == "aggregated"
        ]

        if not aggregated.empty:
            return aggregated.iloc[-1]

    print(
        "[WARNING] No Aggregated row found; "
        "using the final CSV row instead."
    )

    return df.iloc[-1]


def read_percentiles(
    csv_path: Path,
) -> tuple[list[float], list[float]]:
    """Read latency-percentile points from one Locust stats CSV."""

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

    latencies: list[float] = []
    probabilities: list[float] = []

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

        latencies.append(
            min(float(latency), MAX_LATENCY_MS)
        )
        probabilities.append(probability)

    if not latencies:
        raise ValueError(
            f"No percentile columns found in {csv_path}"
        )

    return latencies, probabilities


def main() -> None:
    fig, ax = plt.subplots(figsize=(8.4, 6.0))

    plotted = 0

    for scheme, file_list in FILES.items():
        all_latencies: list[float] = []
        all_probabilities: list[float] = []

        for filename in file_list:
            csv_path = DATA_DIR / filename

            try:
                latencies, probabilities = read_percentiles(
                    csv_path
                )

            except (FileNotFoundError, ValueError) as exc:
                print(f"[SKIP] {scheme}: {exc}")
                continue

            all_latencies.extend(latencies)
            all_probabilities.extend(probabilities)

        if not all_latencies:
            continue

        points = sorted(
            zip(
                all_latencies,
                all_probabilities,
            ),
            key=lambda point: (
                point[0],
                point[1],
            ),
        )

        latency_values = [
            point[0]
            for point in points
        ]

        probability_values = [
            point[1]
            for point in points
        ]

        ax.plot(
            latency_values,
            probability_values,
            marker="o",
            markersize=5,
            linewidth=2.3,
            color=COLORS[scheme],
            label=scheme,
        )

        plotted += 1

    if plotted == 0:
        raise RuntimeError(
            "No CDF curves were plotted. "
            "Check the input filenames."
        )

    # SLO reference line.
    ax.axvline(
        SLO_MS,
        color="black",
        linestyle="--",
        linewidth=2.0,
        label=f"SLO ({SLO_MS} ms)",
    )

    # Percentile guide lines.
    for probability, label in [
        (0.90, "P90"),
        (0.95, "P95"),
        (0.99, "P99"),
    ]:
        ax.axhline(
            probability,
            linestyle="--",
            linewidth=0.8,
            alpha=0.45,
            color="gray",
        )

        ax.text(
            MAX_LATENCY_MS * 0.015,
            probability + 0.003,
            label,
            ha="left",
            va="bottom",
            fontsize=12,
            color="gray",
        )

    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Cumulative Probability")

    ax.set_title(
        f"End-to-End Latency CDF "
        f"(clipped at {MAX_LATENCY_MS / 1000:g} s)"
    )

    ax.set_xlim(
        0,
        MAX_LATENCY_MS,
    )

    ax.set_ylim(
        0.48,
        1.01,
    )

    ax.set_yticks([
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
        0.95,
        0.99,
        1.00,
    ])

    ax.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
    )

    ax.legend(
        loc="lower right",
        frameon=True,
        framealpha=0.95,
        facecolor="white",
        edgecolor="black",
    )

    fig.tight_layout()

    fig.savefig(
        OUTPUT_PDF,
        dpi=600,
        bbox_inches="tight",
    )

    fig.savefig(
        OUTPUT_PNG,
        dpi=300,
        bbox_inches="tight",
    )

    print(f"Saved: {OUTPUT_PDF}")
    print(f"Saved: {OUTPUT_PNG}")

    plt.show()


if __name__ == "__main__":
    main()
