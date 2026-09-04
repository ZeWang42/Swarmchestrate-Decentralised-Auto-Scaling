from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt


files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Custom-DAS": ["custom-das.csv", "custom-das.csv"],

}
# Bind color to scheme name, not to plotting order.
scheme_colors = {
    "HPA-80": "tab:orange",
    "DAS": "tab:blue",
    "Custom-DAS": "tab:green",
}

DEFAULT_ORDER = ["HPA-80", "DAS", "Custom-DAS"]
DEFAULT_COLOR = "tab:gray"


def load_data(
    data_dir: Path,
    files: dict[str, list[str]],
) -> pd.DataFrame:

    frames = []

    for scheme, file_list in files.items():

        for run_id, filename in enumerate(file_list, start=1):

            path = data_dir / filename

            if not path.exists():
                raise FileNotFoundError(f"Missing file: {path}")

            df = pd.read_csv(path)

            required = {"Timestamp", "Scope", "Name", "Pods"}
            missing = required - set(df.columns)

            if missing:
                raise ValueError(
                    f"{path} is missing required columns: {sorted(missing)}"
                )

            df = df[df["Scope"] == "deployment"].copy()

            if df.empty:
                raise ValueError(
                    f"{path} contains no rows with Scope == 'deployment'"
                )

            df["Timestamp"] = pd.to_datetime(df["Timestamp"])
            df["Pods"] = pd.to_numeric(df["Pods"], errors="coerce")

            df = df.dropna(
                subset=["Timestamp", "Name", "Pods"]
            )

            start_time = df["Timestamp"].min()

            df["ElapsedSec"] = (
                df["Timestamp"] - start_time
            ).dt.total_seconds()

            df["Minute"] = (
                df["ElapsedSec"] // 60
            ).astype(int)

            df["Scheme"] = scheme
            df["Run"] = run_id

            frames.append(df)

    if not frames:
        raise ValueError("No data loaded.")

    return pd.concat(
        frames,
        ignore_index=True,
    )


def calculate_decision_counts(
    data: pd.DataFrame,
    tolerance: float = 1e-9,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Definition:

    1. Compute average pod count per minute for each microservice.
    2. Compare minute t against minute t-1.
    3. If avg pods changed, count one decision.
    4. Sum decisions across microservices.
    """

    per_minute = (
        data.groupby(
            ["Scheme", "Run", "Name", "Minute"],
            as_index=False,
        )["Pods"]
        .mean()
        .rename(columns={"Pods": "AvgPods"})
        .sort_values(
            ["Scheme", "Run", "Name", "Minute"]
        )
    )

    per_minute["PrevAvgPods"] = (
        per_minute.groupby(
            ["Scheme", "Run", "Name"]
        )["AvgPods"]
        .shift(1)
    )

    per_minute["Decision"] = (
        per_minute["PrevAvgPods"].notna()
        &
        (
            (
                per_minute["AvgPods"]
                - per_minute["PrevAvgPods"]
            ).abs()
            > tolerance
        )
    ).astype(int)

    # Per-run per-service
    per_run_service = (
        per_minute.groupby(
            ["Scheme", "Run", "Name"],
            as_index=False,
        )["Decision"]
        .sum()
        .rename(
            columns={
                "Decision": "DecisionCount"
            }
        )
    )

    # Average across runs
    by_service = (
        per_run_service.groupby(
            ["Scheme", "Name"],
            as_index=False,
        )["DecisionCount"]
        .mean()
    )

    # Total decisions per run
    per_run_total = (
        per_run_service.groupby(
            ["Scheme", "Run"],
            as_index=False,
        )["DecisionCount"]
        .sum()
    )

    # Average across runs
    totals = (
        per_run_total.groupby(
            "Scheme",
            as_index=False,
        )["DecisionCount"]
        .mean()
        .rename(
            columns={
                "DecisionCount":
                "TotalDecisionCount"
            }
        )
    )

    return by_service, totals


def plot_by_microservice(
    by_service: pd.DataFrame,
    scheme_order: list[str],
    output: Path,
) -> None:

    pivot = (
        by_service.pivot(
            index="Name",
            columns="Scheme",
            values="DecisionCount",
        )
        .fillna(0.0)
    )

    existing_order = [
        s for s in scheme_order
        if s in pivot.columns
    ]

    remaining = [
        s for s in pivot.columns
        if s not in existing_order
    ]

    pivot = pivot[
        existing_order + remaining
    ]

    ax = pivot.plot(
        kind="bar",
        figsize=(13, 6),
        width=0.82,
        color=[
            scheme_colors.get(
                col,
                DEFAULT_COLOR,
            )
            for col in pivot.columns
        ],
    )

    ax.set_xlabel("Microservice")
    ax.set_ylabel("Decision count")
    ax.set_title(
        "Decision makings per microservice"
    )

    ax.grid(axis="y", alpha=0.3)
    ax.legend(title="Autoscaler")

    plt.xticks(
        rotation=45,
        ha="right",
    )

    plt.tight_layout()
    plt.savefig(output, dpi=300)
    plt.close()


def plot_total(
    totals: pd.DataFrame,
    scheme_order: list[str],
    output: Path,
) -> None:

    totals = totals.set_index("Scheme")

    existing_order = [
        s for s in scheme_order
        if s in totals.index
    ]

    remaining = [
        s for s in totals.index
        if s not in existing_order
    ]

    totals = totals.loc[
        existing_order + remaining
    ].reset_index()

    plt.figure(figsize=(7, 5))

    bars = plt.bar(
        totals["Scheme"],
        totals["TotalDecisionCount"],
        color=[
            scheme_colors.get(
                scheme,
                DEFAULT_COLOR,
            )
            for scheme in totals["Scheme"]
        ],
    )

    for bar in bars:

        height = bar.get_height()

        plt.text(
            bar.get_x()
            + bar.get_width() / 2,
            height * 1.01,
            f"{height:.0f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    plt.xlabel("Scheme")
    plt.ylabel(
        "Total decision count"
    )
    plt.title(
        "Total decision makings per autoscaler"
    )

    plt.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output, dpi=300)
    plt.close()


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Plot autoscaler decision-making "
            "counts from deployment pod logs."
        )
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("."),
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("."),
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-9,
    )

    args = parser.parse_args()

    args.out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = load_data(
        args.data_dir,
        files,
    )

    by_service, totals = (
        calculate_decision_counts(
            data,
            tolerance=args.tolerance,
        )
    )

    by_service.to_csv(
        args.out_dir
        / "decision_counts_by_microservice.csv",
        index=False,
    )

    totals.to_csv(
        args.out_dir
        / "decision_counts_total.csv",
        index=False,
    )

    plot_by_microservice(
        by_service,
        DEFAULT_ORDER,
        args.out_dir
        / "decision_counts_by_microservice.png",
    )

    plot_total(
        totals,
        DEFAULT_ORDER,
        args.out_dir
        / "decision_counts_total.png",
    )

    print("Saved:")
    print(
        args.out_dir
        / "decision_counts_by_microservice.csv"
    )
    print(
        args.out_dir
        / "decision_counts_total.csv"
    )
    print(
        args.out_dir
        / "decision_counts_by_microservice.png"
    )
    print(
        args.out_dir
        / "decision_counts_total.png"
    )


if __name__ == "__main__":
    main()

