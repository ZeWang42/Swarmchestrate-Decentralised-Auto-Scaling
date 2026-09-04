from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


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


# ---------------------------------------------------------------------
# Resource prices
#
# CPU:    $ / vCPU / second
# Memory: $ / GiB / second
#
# Based on:
# CPU    = $0.04656 / vCPU / hour
# Memory = $0.00510 / GiB / hour
# ---------------------------------------------------------------------

CPU_PRICE_PER_VCPU_SECOND = 0.04656 / 3600.0
MEMORY_PRICE_PER_GIB_SECOND = 0.00510 / 3600.0

SECONDS_PER_MINUTE = 60.0


# ---------------------------------------------------------------------
# Resource limits per replica
# ---------------------------------------------------------------------

RESOURCE_LIMITS = {
    "frontend": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "adservice": {
        "cpu_m": 300,
        "memory_mib": 300,
    },

    "cartservice": {
        "cpu_m": 300,
        "memory_mib": 128,
    },

    "checkoutservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "currencyservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "emailservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "paymentservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "productcatalogservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "recommendationservice": {
        "cpu_m": 200,
        "memory_mib": 450,
    },

    "shippingservice": {
        "cpu_m": 200,
        "memory_mib": 128,
    },

    "redis-cart": {
        "cpu_m": 125,
        "memory_mib": 256,
    },
}

APPLICATION_DEPLOYMENTS = set(
    RESOURCE_LIMITS.keys()
)


# ---------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------

OUTPUT_RUN_CSV = Path(
    "resource_cost_per_run.csv"
)

OUTPUT_SUMMARY_CSV = Path(
    "resource_cost_average_summary.csv"
)

OUTPUT_MINUTE_CSV = Path(
    "resource_cost_per_minute.csv"
)

OUTPUT_PNG = Path(
    "resource_cost_comparison_average.png"
)

OUTPUT_PDF = Path(
    "resource_cost_comparison_average.pdf"
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def cpu_m_to_vcpu(cpu_m: float) -> float:
    """Convert Kubernetes millicores to vCPU."""
    return cpu_m / 1000.0


def mib_to_gib(memory_mib: float) -> float:
    """Convert MiB to GiB."""
    return memory_mib / 1024.0


# ---------------------------------------------------------------------
# Load deployment replicas per minute
# ---------------------------------------------------------------------

def load_deployment_replicas_per_minute(
    csv_path: Path,
) -> pd.DataFrame:
    """
    Calculate average replica count for every deployment
    within every elapsed minute.

    Result:

        Minute | Name | AverageReplicas
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
        "Pods",
    }

    missing = required_columns.difference(
        df.columns
    )

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (
            df["Name"].isin(
                APPLICATION_DEPLOYMENTS
            )
        ),
        [
            "Timestamp",
            "Name",
            "Pods",
        ],
    ].copy()

    if app_df.empty:
        raise ValueError(
            f"No matching application deployments "
            f"found in {csv_path}"
        )

    app_df["Timestamp"] = pd.to_datetime(
        app_df["Timestamp"],
        format="mixed",
        dayfirst=True,
        errors="coerce",
    )

    app_df["Pods"] = pd.to_numeric(
        app_df["Pods"],
        errors="coerce",
    )

    app_df = app_df.dropna(
        subset=[
            "Timestamp",
            "Name",
            "Pods",
        ]
    )

    if app_df.empty:
        raise ValueError(
            f"No valid deployment measurements "
            f"remain in {csv_path}"
        )

    first_timestamp = (
        app_df["Timestamp"].min()
    )

    app_df["ElapsedSeconds"] = (
        app_df["Timestamp"]
        - first_timestamp
    ).dt.total_seconds()

    app_df["Minute"] = (
        app_df["ElapsedSeconds"] // 60
    ).astype(int)

    deployment_minute = (
        app_df.groupby(
            [
                "Minute",
                "Name",
            ],
            as_index=False,
        )["Pods"]
        .mean()
        .rename(
            columns={
                "Pods": "AverageReplicas"
            }
        )
    )

    return deployment_minute


# ---------------------------------------------------------------------
# Cost calculation for one run
# ---------------------------------------------------------------------

def calculate_cost(
    csv_path: Path,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Compute the complete experiment cost for one run.

    Cost:

        sum_t sum_d [
            replicas(t,d)
            *
            (
                CPU_limit(d) * CPU_price
                +
                Memory_limit(d) * Memory_price
            )
            *
            60 seconds
        ]
    """

    deployment_minute = (
        load_deployment_replicas_per_minute(
            csv_path
        )
    )

    rows = []

    for row in deployment_minute.itertuples(
        index=False
    ):
        deployment = row.Name
        minute = row.Minute
        replicas = row.AverageReplicas

        limits = RESOURCE_LIMITS[
            deployment
        ]

        cpu_vcpu_per_replica = (
            cpu_m_to_vcpu(
                limits["cpu_m"]
            )
        )

        memory_gib_per_replica = (
            mib_to_gib(
                limits["memory_mib"]
            )
        )

        # -------------------------------------------------------------
        # Allocated resources
        # -------------------------------------------------------------

        allocated_cpu_vcpu = (
            replicas
            * cpu_vcpu_per_replica
        )

        allocated_memory_gib = (
            replicas
            * memory_gib_per_replica
        )

        # -------------------------------------------------------------
        # Cost during this minute
        # -------------------------------------------------------------

        cpu_cost = (
            allocated_cpu_vcpu
            * CPU_PRICE_PER_VCPU_SECOND
            * SECONDS_PER_MINUTE
        )

        memory_cost = (
            allocated_memory_gib
            * MEMORY_PRICE_PER_GIB_SECOND
            * SECONDS_PER_MINUTE
        )

        total_cost = (
            cpu_cost
            + memory_cost
        )

        rows.append({
            "Minute": minute,
            "Deployment": deployment,
            "AverageReplicas": replicas,

            "AllocatedCPU_vCPU":
                allocated_cpu_vcpu,

            "AllocatedMemory_GiB":
                allocated_memory_gib,

            "CPUCost_USD":
                cpu_cost,

            "MemoryCost_USD":
                memory_cost,

            "TotalCost_USD":
                total_cost,
        })

    detail = pd.DataFrame(
        rows
    )

    # -----------------------------------------------------------------
    # Aggregate deployment costs into cost per minute
    # -----------------------------------------------------------------

    minute_cost = (
        detail.groupby(
            "Minute",
            as_index=False,
        )
        .agg(
            CPUCost_USD=(
                "CPUCost_USD",
                "sum",
            ),
            MemoryCost_USD=(
                "MemoryCost_USD",
                "sum",
            ),
            TotalCost_USD=(
                "TotalCost_USD",
                "sum",
            ),
        )
    )

    # -----------------------------------------------------------------
    # Complete cost of this experiment run
    # -----------------------------------------------------------------

    summary = {
        "CPUCost_USD":
            minute_cost["CPUCost_USD"].sum(),

        "MemoryCost_USD":
            minute_cost["MemoryCost_USD"].sum(),

        "TotalCost_USD":
            minute_cost["TotalCost_USD"].sum(),
    }

    return (
        minute_cost,
        summary,
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    run_rows = []
    minute_results = []

    # -----------------------------------------------------------------
    # Process every run independently
    # -----------------------------------------------------------------

    for autoscaler, csv_paths in INPUT_FILES.items():

        for run_number, csv_path in enumerate(
            csv_paths,
            start=1,
        ):
            try:
                minute_cost, summary = (
                    calculate_cost(
                        csv_path
                    )
                )

            except (
                FileNotFoundError,
                ValueError,
            ) as exc:
                print(
                    f"[SKIP] {autoscaler} "
                    f"run {run_number}: {exc}"
                )
                continue

            # ---------------------------------------------------------
            # Save per-minute results
            # ---------------------------------------------------------

            minute_output = (
                minute_cost.copy()
            )

            minute_output.insert(
                0,
                "Run",
                run_number,
            )

            minute_output.insert(
                0,
                "Autoscaler",
                autoscaler,
            )

            minute_results.append(
                minute_output
            )

            # ---------------------------------------------------------
            # Save total cost of this run
            # ---------------------------------------------------------

            run_rows.append({
                "Autoscaler":
                    autoscaler,

                "DisplayName":
                    DISPLAY_NAMES[autoscaler],

                "Run":
                    run_number,

                "File":
                    str(csv_path),

                "CPUCost_USD":
                    summary["CPUCost_USD"],

                "MemoryCost_USD":
                    summary["MemoryCost_USD"],

                "TotalCost_USD":
                    summary["TotalCost_USD"],
            })

    if not run_rows:
        raise RuntimeError(
            "No cost data available."
        )

    # -----------------------------------------------------------------
    # Per-run DataFrame
    # -----------------------------------------------------------------

    run_df = pd.DataFrame(
        run_rows
    )

    run_df.to_csv(
        OUTPUT_RUN_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Average across runs for each autoscaler
    # -----------------------------------------------------------------

    summary_df = (
        run_df.groupby(
            [
                "Autoscaler",
                "DisplayName",
            ],
            as_index=False,
        )
        .agg(
            MeanCPUCost_USD=(
                "CPUCost_USD",
                "mean",
            ),
            StdCPUCost_USD=(
                "CPUCost_USD",
                "std",
            ),

            MeanMemoryCost_USD=(
                "MemoryCost_USD",
                "mean",
            ),
            StdMemoryCost_USD=(
                "MemoryCost_USD",
                "std",
            ),

            MeanTotalCost_USD=(
                "TotalCost_USD",
                "mean",
            ),
            StdTotalCost_USD=(
                "TotalCost_USD",
                "std",
            ),

            MinTotalCost_USD=(
                "TotalCost_USD",
                "min",
            ),

            MaxTotalCost_USD=(
                "TotalCost_USD",
                "max",
            ),

            Runs=(
                "TotalCost_USD",
                "count",
            ),
        )
    )

    # -------------------------------------------------------------
    # Keep plotting order consistent
    # -------------------------------------------------------------

    ORDER = ["queue-CDT120","queue-CDT300", "hpa80-CDT120", "hpa80-CDT300"]

    summary_df["Order"] = summary_df["Autoscaler"].map(
        {name: i for i, name in enumerate(ORDER)}
    )

    summary_df = (
        summary_df
        .sort_values("Order")
        .drop(columns="Order")
        .reset_index(drop=True)
    )
    # One run -> std is NaN.
    std_columns = [
        "StdCPUCost_USD",
        "StdMemoryCost_USD",
        "StdTotalCost_USD",
    ]

    summary_df[std_columns] = (
        summary_df[std_columns]
        .fillna(0.0)
    )

    summary_df.to_csv(
        OUTPUT_SUMMARY_CSV,
        index=False,
    )

    # -----------------------------------------------------------------
    # Save minute-level data
    # -----------------------------------------------------------------

    if minute_results:
        pd.concat(
            minute_results,
            ignore_index=True,
        ).to_csv(
            OUTPUT_MINUTE_CSV,
            index=False,
        )

    # -----------------------------------------------------------------
    # Print per-run results
    # -----------------------------------------------------------------

    print()
    print(
        "=== Cost Per Run ==="
    )

    print(
        run_df[
            [
                "DisplayName",
                "Run",
                "TotalCost_USD",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.6f}",
        )
    )

    # -----------------------------------------------------------------
    # Print averages
    # -----------------------------------------------------------------

    print()
    print(
        "=== Average Resource Cost ==="
    )

    print(
        summary_df[
            [
                "DisplayName",
                "Runs",
                "MeanCPUCost_USD",
                "MeanMemoryCost_USD",
                "MeanTotalCost_USD",
                "StdTotalCost_USD",
                "MinTotalCost_USD",
                "MaxTotalCost_USD",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.6f}",
        )
    )

    # -----------------------------------------------------------------
    # Plot mean total cost
    # -----------------------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(6, 5)
    )

    bars = ax.bar(
        summary_df["DisplayName"],
        summary_df["MeanTotalCost_USD"],
        color=[
            COLORS[name]
            for name in summary_df[
                "Autoscaler"
            ]
        ],
        width=0.58,
    )

    # -----------------------------------------------------------------
    # Standard-deviation error bars
    # -----------------------------------------------------------------

    ax.errorbar(
        summary_df["DisplayName"],
        summary_df["MeanTotalCost_USD"],
        yerr=summary_df["StdTotalCost_USD"],
        fmt="none",
        capsize=5,
        linewidth=1.3,
    )

    max_cost = (
        (
            summary_df["MeanTotalCost_USD"]
            + summary_df["StdTotalCost_USD"]
        )
        .max()
    )

    text_offset = max(
        max_cost * 0.015,
        0.00001,
    )

    # -----------------------------------------------------------------
    # Values above bars
    # -----------------------------------------------------------------

    for bar in bars:
        height = bar.get_height()

        ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            height + text_offset,
            f"${height:.4f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    # -----------------------------------------------------------------
    # Formatting
    # -----------------------------------------------------------------

    ax.set_ylabel(
        "Mean Total Resource Cost (USD)"
    )

    ax.set_title(
        "Average Application Resource Cost"
    )

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.45,
    )

    ax.set_ylim(
        0,
        max_cost * 1.15,
    )

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)

    fig.tight_layout()

    # -----------------------------------------------------------------
    # Save figure
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

    print()
    print(
        f"Saved: {OUTPUT_RUN_CSV}"
    )

    print(
        f"Saved: {OUTPUT_SUMMARY_CSV}"
    )

    print(
        f"Saved: {OUTPUT_MINUTE_CSV}"
    )

    print(
        f"Saved: {OUTPUT_PNG}"
    )

    print(
        f"Saved: {OUTPUT_PDF}"
    )

    plt.show()


if __name__ == "__main__":
    main()
