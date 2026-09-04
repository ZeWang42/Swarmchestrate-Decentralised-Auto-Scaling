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
    "DAS": Path("das.csv"),
    "HPA-50": Path("hpa50.csv"),
    "HPA-80": Path("hpa80.csv"),
    "Queue": Path("queue.csv"),
}

COLORS = {
    "DAS": "tab:blue",
    "HPA-50": "tab:orange",
    "HPA-80": "tab:green",
    "Queue": "tab:red",
}

# Set this to the scope written by your monitor:
# "http_p90_latency" or "http_p95_latency".
LATENCY_SCOPE = "http_p95_latency"

# Application entry service whose latency is monitored.
ROOT_SERVICE = "productpage-v1"

# Optional SLO reference line. Set to None to disable.
SLO_MS: float | None = 200

OUTPUT_PNG = Path("latency_over_time.png")
OUTPUT_PDF = Path("latency_over_time.pdf")


def load_latency(
    csv_path: Path,
    latency_scope: str,
    root_service: str,
) -> pd.DataFrame:
    """Read one monitoring CSV and return elapsed time and latency."""

    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

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
            df["Scope"].dropna().astype(str).unique()
        )

        raise ValueError(
            f"No rows found in {csv_path} for "
            f"Scope={latency_scope!r}, Name={root_service!r}.\n"
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
        latency.dropna(
            subset=["Timestamp", "HTTP_LAT_ms"]
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
    fig, ax = plt.subplots(figsize=(8.4, 5.2))

    plotted = 0

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

        ax.plot(
            latency["Elapsed_minutes"],
            latency["HTTP_LAT_ms"],
            label=label,
            color=COLORS[label],
            linewidth=2.3,
        )

        plotted += 1

    if plotted == 0:
        raise RuntimeError(
            "No latency series were plotted. Check the filenames, "
            "LATENCY_SCOPE, and ROOT_SERVICE settings."
        )

    if SLO_MS is not None:
        ax.axhline(
            y=SLO_MS,
            color="black",
            linestyle="--",
            linewidth=2.0,
            label=f"SLO ({SLO_MS:g} ms)",
        )

    percentile = (
        LATENCY_SCOPE
        .replace("http_", "")
        .replace("_latency", "")
        .upper()
    )

    ax.set_xlabel("Elapsed Time (minutes)")
    ax.set_ylabel(f"{percentile} Latency (ms)")
    ax.set_title(
        f"Application {percentile} Latency over Time"
    )

    ax.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
    )

    ax.legend(
        loc="upper right",
        ncol=1,
        frameon=True,
        framealpha=0.95,
        fontsize=13,
    )

    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

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

    plt.show()


if __name__ == "__main__":
    main()
