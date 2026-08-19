from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


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

# Deployment names used by each autoscaler.
# Update these if your manifests use different names.
AUTOSCALER_DEPLOYMENTS = {
    "DAS": {
        "das-autoscaler",
    },
    "HPA-50": {
        # Native HPA normally has no dedicated deployment row.
        # Leave empty unless you monitor a separate HPA controller.
    },
    "HPA-80": {
        # Native HPA normally has no dedicated deployment row.
    },
    "PBScaler": {
        "pbscaler-boutique",
    },
}

OUTPUT_PDF = Path("total_autoscaler_cpu.pdf")
OUTPUT_PNG = Path("total_autoscaler_cpu.png")
OUTPUT_CSV = Path("total_autoscaler_cpu.csv")
PER_MINUTE_CSV = Path("autoscaler_cpu_per_minute.csv")


def calculate_autoscaler_cpu(
    csv_path: Path,
    deployment_names: set[str],
) -> tuple[float, pd.DataFrame]:
    """
    Calculate cumulative autoscaler CPU consumption.

    Procedure:
    1. Select deployment rows belonging to the autoscaler.
    2. Sum their CPU usage at each timestamp.
    3. Average the timestamp totals within each elapsed minute.
    4. Sum the per-minute averages.

    The result is expressed in mCPU-minutes.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

    if not deployment_names:
        raise ValueError(
            "No dedicated autoscaler deployment is configured"
        )

    df = pd.read_csv(csv_path)

    required_columns = {
        "Timestamp",
        "Scope",
        "Name",
        "CPU_m",
    }

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    scaler_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(deployment_names)),
        ["Timestamp", "Name", "CPU_m"],
    ].copy()

    if scaler_df.empty:
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
            f"No matching autoscaler deployment rows found in "
            f"{csv_path}. Expected one of "
            f"{sorted(deployment_names)}.\n"
            f"Available deployment names: {available_names}"
        )

    scaler_df["Timestamp"] = pd.to_datetime(
        scaler_df["Timestamp"],
        errors="coerce",
    )

    scaler_df["CPU_m"] = pd.to_numeric(
        scaler_df["CPU_m"],
        errors="coerce",
    )

    scaler_df = scaler_df.dropna(
        subset=["Timestamp", "CPU_m"]
    )

    if scaler_df.empty:
        raise ValueError(
            f"No valid autoscaler CPU measurements found in {csv_path}"
        )

    # Sum CPU across autoscaler-related deployments at each timestamp.
    timestamp_totals = (
        scaler_df.groupby("Timestamp", as_index=False)["CPU_m"]
        .sum()
        .rename(columns={"CPU_m": "TotalCPU_m"})
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

    # Average autoscaler CPU within each minute.
    minute_cpu = (
        timestamp_totals.groupby(
            "Minute",
            as_index=False,
        )["TotalCPU_m"]
        .mean()
        .rename(
            columns={
                "TotalCPU_m": "AverageCPU_m"
            }
        )
    )

    # Sum per-minute averages to obtain mCPU-minutes.
    total_cpu_m_minutes = minute_cpu[
        "AverageCPU_m"
    ].sum()

    return float(total_cpu_m_minutes), minute_cpu


def main() -> None:
    results: dict[str, float] = {}
    minute_results: list[pd.DataFrame] = []
    unavailable: list[str] = []

    for autoscaler, csv_path in FILES.items():
        deployment_names = AUTOSCALER_DEPLOYMENTS[autoscaler]

        try:
            total_cpu, minute_cpu = calculate_autoscaler_cpu(
                csv_path=csv_path,
                deployment_names=deployment_names,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {autoscaler}: {exc}")
            unavailable.append(autoscaler)
            continue

        results[autoscaler] = total_cpu

        minute_cpu.insert(
            0,
            "Autoscaler",
            autoscaler,
        )
        minute_results.append(minute_cpu)

        print(
            f"{autoscaler}: "
            f"{total_cpu:.2f} mCPU-minutes"
        )

    if not results:
        raise RuntimeError(
            "No autoscaler CPU results were calculated. "
            "Check the deployment names in "
            "AUTOSCALER_DEPLOYMENTS."
        )

    summary_df = pd.DataFrame(
        {
            "Autoscaler": list(results.keys()),
            "TotalAutoscalerCPU_mCPU_minutes": list(
                results.values()
            ),
        }
    )

    summary_df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    if minute_results:
        pd.concat(
            minute_results,
            ignore_index=True,
        ).to_csv(
            PER_MINUTE_CSV,
            index=False,
        )

    labels = list(results.keys())
    values = [results[label] for label in labels]

    fig, ax = plt.subplots(figsize=(6.2, 4.8))

    bars = ax.bar(
        labels,
        values,
        color=[COLORS[label] for label in labels],
        width=0.62,
    )

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:,.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xlabel("Autoscaler")
    ax.set_ylabel(
        "Total autoscaler CPU consumption "
        "(mCPU-minutes)"
    )
    ax.set_title(
        "Cumulative Autoscaler CPU Consumption"
    )

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.7,
        alpha=0.6,
    )

    ax.set_ylim(
        bottom=0,
        top=max(values) * 1.18,
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
    print(f"Saved: {OUTPUT_CSV}")
    print(f"Saved: {PER_MINUTE_CSV}")

    if unavailable:
        print(
            "No dedicated CPU measurement was available for: "
            + ", ".join(unavailable)
        )

    plt.show()


if __name__ == "__main__":
    main()
