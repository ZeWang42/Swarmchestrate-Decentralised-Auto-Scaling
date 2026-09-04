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

# Native HPA has no dedicated autoscaler Deployment whose resource usage
# can be isolated from the Kubernetes control plane.
NO_DEDICATED_CONTROLLER = {
    "HPA-50",
    "HPA-80",
}

AUTOSCALER_SCOPE = "autoscaler"

OUTPUT_PDF = Path("autoscaler_cpu_memory.pdf")
OUTPUT_PNG = Path("autoscaler_cpu_memory.png")
OUTPUT_SUMMARY_CSV = Path("autoscaler_cpu_memory_summary.csv")
OUTPUT_PER_MINUTE_CSV = Path("autoscaler_cpu_memory_per_minute.csv")

MCPU_PER_CORE = 1000.0
MIB_PER_GIB = 1024.0


def calculate_autoscaler_resources(
    csv_path: Path,
) -> tuple[float, float, pd.DataFrame]:
    """
    Calculate cumulative autoscaler CPU and memory consumption.

    1. Keep rows with Scope='autoscaler'.
    2. Sum all autoscaler controller deployments at each timestamp.
       This supports DAS with multiple per-service controllers.
    3. Average total usage within each elapsed minute.
    4. Sum the per-minute averages across the experiment.
    5. Convert to core-minutes and GiB-minutes.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

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
            f"{csv_path} is missing required columns: {sorted(missing)}"
        )

    scaler_df = df.loc[
        df["Scope"].astype(str).str.strip().str.lower() == AUTOSCALER_SCOPE,
        ["Timestamp", "Name", "CPU_m", "MEM_MiB"],
    ].copy()

    if scaler_df.empty:
        available_scopes = sorted(
            df["Scope"].dropna().astype(str).unique()
        )
        raise ValueError(
            f"No Scope='autoscaler' rows found in {csv_path}. "
            f"Available scopes: {available_scopes}"
        )

    scaler_df["Timestamp"] = pd.to_datetime(
        scaler_df["Timestamp"], errors="coerce"
    )
    scaler_df["CPU_m"] = pd.to_numeric(
        scaler_df["CPU_m"], errors="coerce"
    )
    scaler_df["MEM_MiB"] = pd.to_numeric(
        scaler_df["MEM_MiB"], errors="coerce"
    )

    scaler_df = scaler_df.dropna(
        subset=["Timestamp", "CPU_m", "MEM_MiB"]
    )

    if scaler_df.empty:
        raise ValueError(
            f"No valid autoscaler CPU/memory measurements in {csv_path}"
        )

    timestamp_totals = (
        scaler_df.groupby("Timestamp", as_index=False)[["CPU_m", "MEM_MiB"]]
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

    first_timestamp = timestamp_totals["Timestamp"].iloc[0]

    timestamp_totals["ElapsedSeconds"] = (
        timestamp_totals["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    timestamp_totals["Minute"] = (
        timestamp_totals["ElapsedSeconds"] // 60
    ).astype(int)

    minute_resources = (
        timestamp_totals.groupby("Minute", as_index=False)[
            ["TotalCPU_m", "TotalMemory_MiB"]
        ]
        .mean()
        .rename(
            columns={
                "TotalCPU_m": "AverageCPU_m",
                "TotalMemory_MiB": "AverageMemory_MiB",
            }
        )
    )

    minute_resources["AverageCPU_cores"] = (
        minute_resources["AverageCPU_m"] / MCPU_PER_CORE
    )
    minute_resources["AverageMemory_GiB"] = (
        minute_resources["AverageMemory_MiB"] / MIB_PER_GIB
    )

    total_cpu_core_minutes = (
        minute_resources["AverageCPU_m"].sum() / MCPU_PER_CORE
    )

    total_memory_gib_minutes = (
        minute_resources["AverageMemory_MiB"].sum() / MIB_PER_GIB
    )

    return (
        float(total_cpu_core_minutes),
        float(total_memory_gib_minutes),
        minute_resources,
    )


def add_bar_labels(axis, bars, values, value_format):
    """Place horizontal labels above each bar."""

    if not values:
        return

    offset = max(values) * 0.015 if max(values) > 0 else 0.02

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
    results = {}
    minute_results = []
    unavailable = []

    for autoscaler, csv_path in FILES.items():

        if autoscaler in NO_DEDICATED_CONTROLLER:
            print(
                f"[N/A] {autoscaler}: native HPA has no dedicated "
                f"autoscaler Deployment to measure separately."
            )
            unavailable.append(autoscaler)
            continue

        try:
            total_cpu, total_memory, minute_resources = (
                calculate_autoscaler_resources(csv_path)
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {autoscaler}: {exc}")
            unavailable.append(autoscaler)
            continue

        results[autoscaler] = {
            "CPU": total_cpu,
            "Memory": total_memory,
        }

        minute_output = minute_resources.copy()
        minute_output.insert(0, "Autoscaler", autoscaler)
        minute_results.append(minute_output)

        print(
            f"{autoscaler}: "
            f"CPU={total_cpu:,.3f} core-minutes, "
            f"Memory={total_memory:,.3f} GiB-minutes"
        )

    if not results:
        raise RuntimeError(
            "No autoscaler resource results were calculated. "
            "Ensure the CSVs contain Scope='autoscaler' rows."
        )

    summary_rows = []

    for autoscaler in FILES:
        if autoscaler in results:
            summary_rows.append({
                "Autoscaler": autoscaler,
                "AutoscalerCPU_core_minutes": results[autoscaler]["CPU"],
                "AutoscalerMemory_GiB_minutes": results[autoscaler]["Memory"],
                "Status": "measured",
            })
        else:
            summary_rows.append({
                "Autoscaler": autoscaler,
                "AutoscalerCPU_core_minutes": np.nan,
                "AutoscalerMemory_GiB_minutes": np.nan,
                "Status": (
                    "N/A - no dedicated controller"
                    if autoscaler in NO_DEDICATED_CONTROLLER
                    else "not measured"
                ),
            })

    pd.DataFrame(summary_rows).to_csv(
        OUTPUT_SUMMARY_CSV, index=False
    )

    if minute_results:
        pd.concat(
            minute_results, ignore_index=True
        ).to_csv(
            OUTPUT_PER_MINUTE_CSV, index=False
        )

    labels = [
        autoscaler
        for autoscaler in FILES
        if autoscaler in results
    ]

    cpu_values = [results[label]["CPU"] for label in labels]
    memory_values = [results[label]["Memory"] for label in labels]

    x = np.arange(len(labels))
    bar_width = 0.34

    fig, cpu_ax = plt.subplots(figsize=(8.4, 6.0))
    memory_ax = cpu_ax.twinx()

    cpu_bars = cpu_ax.bar(
        x - bar_width / 2,
        cpu_values,
        width=bar_width,
        color=[COLORS[label] for label in labels],
        edgecolor="black",
        linewidth=0.8,
        alpha=1.0,
        zorder=3,
    )

    memory_bars = memory_ax.bar(
        x + bar_width / 2,
        memory_values,
        width=bar_width,
        color=[COLORS[label] for label in labels],
        edgecolor="black",
        linewidth=0.8,
        alpha=0.35,
        hatch="//",
        zorder=2,
    )

    cpu_ax.set_xlabel("Autoscaler")
    cpu_ax.set_ylabel(
        "Autoscaler CPU Consumption\n(core-minutes)"
    )
    memory_ax.set_ylabel(
        "Autoscaler Memory Consumption\n(GiB-minutes)"
    )
    cpu_ax.set_title(
        "Cumulative Autoscaler CPU and Memory Consumption"
    )

    cpu_ax.set_xticks(x)
    cpu_ax.set_xticklabels(labels)

    cpu_ax.set_ylim(
        bottom=0,
        top=max(cpu_values) * 1.25,
    )
    memory_ax.set_ylim(
        bottom=0,
        top=max(memory_values) * 1.25,
    )

    cpu_ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
        zorder=0,
    )

    add_bar_labels(
        cpu_ax, cpu_bars, cpu_values, "{:,.2f}"
    )
    add_bar_labels(
        memory_ax, memory_bars, memory_values, "{:,.2f}"
    )

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
        ncol=2,
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

    if unavailable:
        print("Not plotted: " + ", ".join(unavailable))

    plt.show()


if __name__ == "__main__":
    main()
