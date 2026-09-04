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
    "DAS": [Path("das_stats.csv")],
    "HPA-50": [Path("hpa50_stats.csv")],
    "HPA-80": [Path("hpa80_stats.csv")],
    "PBScaler": [Path("pbscaler_stats.csv")],
}

COLORS = {
    "DAS": "tab:blue",
    "HPA-50": "tab:orange",
    "HPA-80": "tab:green",
    "PBScaler": "tab:red",
}

SLO_MS = 500

OUTPUT_PDF = Path("slo_violation_rate_bar.pdf")
OUTPUT_PNG = Path("slo_violation_rate_bar.png")
OUTPUT_CSV = Path("slo_violation_rate.csv")


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


def get_aggregated_row(df: pd.DataFrame) -> pd.Series:
    """Return the Locust Aggregated row, or the final row as fallback."""

    if "Name" in df.columns:
        aggregated = df.loc[
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
    """Read latency-percentile points from a Locust stats CSV."""

    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if df.empty:
        raise ValueError(f"CSV is empty: {csv_path}")

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

        latencies.append(float(latency))
        probabilities.append(probability)

    if not latencies:
        raise ValueError(
            f"No supported percentile columns found in {csv_path}"
        )

    points = sorted(
        zip(latencies, probabilities),
        key=lambda point: (point[0], point[1]),
    )

    sorted_latencies = [point[0] for point in points]
    sorted_probabilities = [point[1] for point in points]

    return sorted_latencies, sorted_probabilities


def estimate_violation_rate(
    latencies: list[float],
    probabilities: list[float],
    slo_ms: float,
) -> float:
    """
    Estimate P(latency > SLO) using linear interpolation between
    the reported percentile points.
    """

    if len(latencies) != len(probabilities):
        raise ValueError(
            "Latency and probability arrays must have equal lengths."
        )

    if not latencies:
        raise ValueError("No percentile points were supplied.")

    # SLO is below the smallest recorded percentile latency.
    if slo_ms < latencies[0]:
        return max(0.0, min(1.0, 1.0 - probabilities[0]))

    # SLO exceeds the largest recorded percentile latency.
    if slo_ms >= latencies[-1]:
        return 0.0

    for index in range(len(latencies) - 1):
        left_latency = latencies[index]
        right_latency = latencies[index + 1]

        left_probability = probabilities[index]
        right_probability = probabilities[index + 1]

        if left_latency <= slo_ms <= right_latency:
            if right_latency == left_latency:
                cdf_at_slo = max(
                    left_probability,
                    right_probability,
                )
            else:
                fraction = (
                    (slo_ms - left_latency)
                    / (right_latency - left_latency)
                )

                cdf_at_slo = (
                    left_probability
                    + fraction
                    * (right_probability - left_probability)
                )

            violation_rate = 1.0 - cdf_at_slo

            return max(
                0.0,
                min(1.0, violation_rate),
            )

    return 0.0


def main() -> None:
    results: list[dict[str, float | str]] = []

    for autoscaler, file_list in FILES.items():
        violation_rates: list[float] = []

        for relative_path in file_list:
            csv_path = DATA_DIR / relative_path

            try:
                latencies, probabilities = read_percentiles(csv_path)

                violation_rate = estimate_violation_rate(
                    latencies=latencies,
                    probabilities=probabilities,
                    slo_ms=SLO_MS,
                )

            except (FileNotFoundError, ValueError) as exc:
                print(f"[SKIP] {autoscaler}: {exc}")
                continue

            violation_rates.append(violation_rate * 100.0)

        if not violation_rates:
            continue

        mean_violation_rate = (
            sum(violation_rates) / len(violation_rates)
        )

        results.append({
            "Autoscaler": autoscaler,
            "SLOViolationRate_percent": mean_violation_rate,
        })

        print(
            f"{autoscaler}: "
            f"{mean_violation_rate:.2f}% SLO violation rate"
        )

    if not results:
        raise RuntimeError(
            "No SLO violation rates were calculated. "
            "Check the input filenames and percentile columns."
        )

    results_df = pd.DataFrame(results)

    desired_order = [
        autoscaler
        for autoscaler in FILES
        if autoscaler in set(results_df["Autoscaler"])
    ]

    results_df = (
        results_df.set_index("Autoscaler")
        .loc[desired_order]
        .reset_index()
    )

    results_df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    labels = results_df["Autoscaler"].tolist()
    values = results_df[
        "SLOViolationRate_percent"
    ].tolist()

    fig, ax = plt.subplots(figsize=(8.4, 6))

    bars = ax.bar(
        labels,
        values,
        color=[COLORS[label] for label in labels],
        edgecolor="black",
        linewidth=0.8,
        width=0.62,
        zorder=3,
    )

    maximum_value = max(values)

    # Leave enough space for horizontal labels above the bars.
    upper_limit = max(
        5.0,
        maximum_value * 1.22,
    )

    ax.set_ylim(0, upper_limit)

    label_offset = upper_limit * 0.015

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + label_offset,
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontsize=16,
            rotation=0,
        )

    ax.set_xlabel("Autoscaler")
    ax.set_ylabel("SLO Violation Rate (%)")
    ax.set_title(
        f"SLO Violation Rate "
        f"(Latency > {SLO_MS} ms)"
    )

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
        zorder=0,
    )

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
