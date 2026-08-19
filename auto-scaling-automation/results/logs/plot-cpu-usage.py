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

# Online Boutique application deployments.
# redis-cart is included because it is part of the deployed application.
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

OUTPUT_PDF = Path("total_application_cpu.pdf")
OUTPUT_PNG = Path("total_application_cpu.png")
OUTPUT_CSV = Path("total_application_cpu.csv")


def calculate_application_cpu(csv_path: Path) -> tuple[float, pd.DataFrame]:
    """
    Calculate cumulative application CPU consumption.

    Procedure:
    1. Select application deployment rows.
    2. Sum CPU usage across deployments at each timestamp.
    3. Average the timestamp totals within each elapsed minute.
    4. Sum the per-minute averages.

    The returned total is expressed in mCPU-minutes.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

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

    # Keep only the application deployments.
    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(APPLICATION_DEPLOYMENTS)),
        ["Timestamp", "Name", "CPU_m"],
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
            f"No application deployment rows found in {csv_path}.\n"
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

    app_df = app_df.dropna(
        subset=["Timestamp", "CPU_m"]
    )

    if app_df.empty:
        raise ValueError(
            f"No valid CPU measurements found in {csv_path}"
        )

    # Sum CPU usage across all application deployments
    # at each monitoring timestamp.
    timestamp_totals = (
        app_df.groupby("Timestamp", as_index=False)["CPU_m"]
        .sum()
        .rename(columns={"CPU_m": "TotalCPU_m"})
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    first_timestamp = timestamp_totals["Timestamp"].iloc[0]

    timestamp_totals["ElapsedSeconds"] = (
        timestamp_totals["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    # Each minute starts at 0, 1, 2, ...
    timestamp_totals["Minute"] = (
        timestamp_totals["ElapsedSeconds"] // 60
    ).astype(int)

    # Average total application CPU within each minute.
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

    # Each per-minute average represents approximately one minute
    # of CPU consumption, so summing gives mCPU-minutes.
    total_cpu_m_minutes = minute_cpu[
        "AverageCPU_m"
    ].sum()

    return float(total_cpu_m_minutes), minute_cpu


def main() -> None:
    results: dict[str, float] = {}
    minute_results: list[pd.DataFrame] = []

    for autoscaler, csv_path in FILES.items():
        try:
            total_cpu, minute_cpu = calculate_application_cpu(
                csv_path
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[SKIP] {autoscaler}: {exc}")
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
            "No CPU results were calculated. "
            "Check the filenames and deployment names."
        )

    # Save summary and per-minute values.
    summary_df = pd.DataFrame(
        {
            "Autoscaler": list(results.keys()),
            "TotalApplicationCPU_mCPU_minutes": list(
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
            "application_cpu_per_minute.csv",
            index=False,
        )

    # -----------------------------------------------------------------
    # Bar plot
    # -----------------------------------------------------------------

    labels = list(results.keys())
    values = [results[label] for label in labels]

    fig, ax = plt.subplots(
        figsize=(6.2, 4.8)
    )

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
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xlabel("Autoscaler")
    ax.set_ylabel(
        "Total application CPU consumption "
        "(mCPU-minutes)"
    )
    ax.set_title(
        "Cumulative Application CPU Consumption"
    )

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.7,
        alpha=0.6,
    )

    ax.set_ylim(
        bottom=0,
        top=max(values) * 1.15,
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
    print("Saved: application_cpu_per_minute.csv")

    plt.show()


if __name__ == "__main__":
    main()
