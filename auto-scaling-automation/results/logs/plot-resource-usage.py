from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


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

FILES = {
    "DAS": Path("das.csv"),
    "HPA-50": Path("hpa50.csv"),
    "HPA-80": Path("hpa80.csv"),
    "PBScaler": Path("pbscaler.csv"),
}

COLORS = {
    "DAS": "tab:blue",
    "HPA-50": "tab:orange",
    "HPA-80": "tab:green",
    "PBScaler": "tab:red",
}

# Online Boutique application deployments.
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

OUTPUT_PDF = Path("application_cpu_memory.pdf")
OUTPUT_PNG = Path("application_cpu_memory.png")
OUTPUT_SUMMARY_CSV = Path("application_cpu_memory_summary.csv")
OUTPUT_PER_MINUTE_CSV = Path("application_cpu_memory_per_minute.csv")


# ---------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------

MCPU_PER_CORE = 1000.0
MIB_PER_GIB = 1024.0


def calculate_application_resources(
    csv_path: Path,
) -> tuple[float, float, pd.DataFrame]:
    """
    Calculate cumulative application CPU and memory consumption.

    Procedure:
    1. Select application deployment rows.
    2. Sum CPU and memory across deployments at each timestamp.
    3. Average timestamp totals within each elapsed minute.
    4. Sum the per-minute averages across the experiment.
    5. Convert mCPU-minutes to core-minutes and MiB-minutes to
       GiB-minutes for clearer presentation.

    Returns
    -------
    total_cpu_core_minutes:
        Cumulative CPU consumption in core-minutes.
    total_memory_gib_minutes:
        Cumulative memory consumption in GiB-minutes.
    minute_resources:
        Per-minute average CPU and memory totals in both original and
        converted units.
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
        "CPU_m",
        "MEM_MiB",
    }

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(APPLICATION_DEPLOYMENTS)),
        [
            "Timestamp",
            "Name",
            "CPU_m",
            "MEM_MiB",
        ],
    ].copy()

    if app_df.empty:
        available_names = sorted(
            df.loc[
                df["Scope"] == "deployment",
                "Name",
            ]
            .dropna()
            .astype(str)
            .unique()
        )

        raise ValueError(
            f"No application deployment rows found in "
            f"{csv_path}.\n"
            f"Available deployment names: {available_names}"
        )

    app_df["Timestamp"] = pd.to_datetime(
        app_df["Timestamp"],
        errors="coerce",
    )

    app_df["CPU_m"] = pd.to_numeric(
        app_df["CPU_m"],
        errors="coerce",
    )

    app_df["MEM_MiB"] = pd.to_numeric(
        app_df["MEM_MiB"],
        errors="coerce",
    )

    app_df = app_df.dropna(
        subset=[
            "Timestamp",
            "CPU_m",
            "MEM_MiB",
        ]
    )

    if app_df.empty:
        raise ValueError(
            f"No valid CPU and memory measurements found "
            f"in {csv_path}"
        )

    # Sum application resource usage at each monitoring timestamp.
    timestamp_totals = (
        app_df.groupby(
            "Timestamp",
            as_index=False,
        )[["CPU_m", "MEM_MiB"]]
        .sum()
        .rename(
            columns={
                "CPU_m": "TotalCPU_m",
                "MEM_MiB": "TotalMemory_MiB",
            }
        )
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    first_timestamp = timestamp_totals[
        "Timestamp"
    ].iloc[0]

    timestamp_totals["ElapsedSeconds"] = (
        timestamp_totals["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    timestamp_totals["Minute"] = (
        timestamp_totals["ElapsedSeconds"] // 60
    ).astype(int)

    # Average all measurements within each elapsed minute.
    minute_resources = (
        timestamp_totals.groupby(
            "Minute",
            as_index=False,
        )[
            [
                "TotalCPU_m",
                "TotalMemory_MiB",
            ]
        ]
        .mean()
        .rename(
            columns={
                "TotalCPU_m": "AverageCPU_m",
                "TotalMemory_MiB": "AverageMemory_MiB",
            }
        )
    )

    # Add converted per-minute values for easier inspection.
    minute_resources["AverageCPU_cores"] = (
        minute_resources["AverageCPU_m"] / MCPU_PER_CORE
    )
    minute_resources["AverageMemory_GiB"] = (
        minute_resources["AverageMemory_MiB"] / MIB_PER_GIB
    )

    # Sum the per-minute averages and convert units.
    total_cpu_core_minutes = (
        minute_resources["AverageCPU_m"].sum()
        / MCPU_PER_CORE
    )

    total_memory_gib_minutes = (
        minute_resources["AverageMemory_MiB"].sum()
        / MIB_PER_GIB
    )

    return (
        float(total_cpu_core_minutes),
        float(total_memory_gib_minutes),
        minute_resources,
    )


def add_bar_labels(
    axis,
    bars,
    values,
    value_format,
):
    """Place horizontal labels above each bar."""

    offset = max(values) * 0.015

    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + offset,
            value_format.format(value),
            ha="center",
            va="bottom",
            fontsize=17,
            rotation=0,
        )


def main() -> None:
    results: dict[str, dict[str, float]] = {}
    minute_results: list[pd.DataFrame] = []

    for autoscaler, csv_path in FILES.items():
        try:
            (
                total_cpu,
                total_memory,
                minute_resources,
            ) = calculate_application_resources(csv_path)

        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {autoscaler}: {exc}")
            continue

        results[autoscaler] = {
            "CPU": total_cpu,
            "Memory": total_memory,
        }

        minute_output = minute_resources.copy()
        minute_output.insert(
            0,
            "Autoscaler",
            autoscaler,
        )
        minute_results.append(minute_output)

        print(
            f"{autoscaler}: "
            f"CPU={total_cpu:,.2f} core-minutes, "
            f"Memory={total_memory:,.2f} GiB-minutes"
        )

    if not results:
        raise RuntimeError(
            "No resource results were calculated. "
            "Check the filenames and deployment names."
        )

    labels = list(results.keys())

    cpu_values = [
        results[label]["CPU"]
        for label in labels
    ]

    memory_values = [
        results[label]["Memory"]
        for label in labels
    ]

    # -----------------------------------------------------------------
    # Save calculated results
    # -----------------------------------------------------------------

    summary_df = pd.DataFrame({
        "Autoscaler": labels,
        "ApplicationCPU_core_minutes": cpu_values,
        "ApplicationMemory_GiB_minutes": memory_values,
    })

    summary_df.to_csv(
        OUTPUT_SUMMARY_CSV,
        index=False,
    )

    if minute_results:
        pd.concat(
            minute_results,
            ignore_index=True,
        ).to_csv(
            OUTPUT_PER_MINUTE_CSV,
            index=False,
        )

    # -----------------------------------------------------------------
    # Grouped bar plot with separate CPU and memory axes
    # -----------------------------------------------------------------

    x = np.arange(len(labels))
    bar_width = 0.34

    fig, cpu_ax = plt.subplots(
        figsize=(8.4, 6.0)
    )

    memory_ax = cpu_ax.twinx()

    cpu_bars = cpu_ax.bar(
        x - bar_width / 2,
        cpu_values,
        width=bar_width,
        color=[
            COLORS[label]
            for label in labels
        ],
        edgecolor="black",
        linewidth=0.8,
        alpha=1.0,
        label="CPU",
        zorder=3,
    )

    memory_bars = memory_ax.bar(
        x + bar_width / 2,
        memory_values,
        width=bar_width,
        color=[
            COLORS[label]
            for label in labels
        ],
        edgecolor="black",
        linewidth=0.8,
        alpha=0.35,
        hatch="//",
        label="Memory",
        zorder=2,
    )

    cpu_ax.set_xlabel("Autoscaler")
    cpu_ax.set_ylabel(
        "Application CPU Consumption\n"
        "(core-minutes)"
    )

    memory_ax.set_ylabel(
        "Application Memory Consumption\n"
        "(GiB-minutes)"
    )

    cpu_ax.set_title(
        "Cumulative Application CPU and Memory Consumption"
    )

    cpu_ax.set_xticks(x)
    cpu_ax.set_xticklabels(labels)

    cpu_ax.set_ylim(
        bottom=0,
        top=max(cpu_values) * 1.20,
    )

    memory_ax.set_ylim(
        bottom=0,
        top=max(memory_values) * 1.20,
    )

    cpu_ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
        zorder=0,
    )

    # Bar labels use their corresponding axes.
    add_bar_labels(
        cpu_ax,
        cpu_bars,
        cpu_values,
        "{:,.1f}",
    )

    add_bar_labels(
        memory_ax,
        memory_bars,
        memory_values,
        "{:,.1f}",
    )

    # White legend symbols: solid for CPU, hatched for memory.
    legend_handles = [
        Patch(
            facecolor="white",
            edgecolor="black",
            linewidth=1.0,
            label="CPU",
        ),
        Patch(
            facecolor="white",
            edgecolor="black",
            linewidth=1.0,
            hatch="//",
            label="Memory",
        ),
    ]

    cpu_ax.legend(
        handles=legend_handles,
        loc="upper right",
        ncol=1,
        frameon=True,
        framealpha=0.95,
        facecolor="white",
        edgecolor="black",
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
    print(f"Saved: {OUTPUT_SUMMARY_CSV}")
    print(f"Saved: {OUTPUT_PER_MINUTE_CSV}")

    plt.show()


if __name__ == "__main__":
    main()
