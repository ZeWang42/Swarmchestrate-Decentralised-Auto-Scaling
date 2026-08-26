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
    "hpa80": Path("hpa80-1.csv"),
    "das": Path("das-1.csv"),
}

COLORS = {
    "queue": "tab:orange",
    "hpa80": "tab:green",
    "das": "tab:blue",
}

# Only these deployments are counted as part of Online Boutique.
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

OUTPUT_PDF = Path("replicas_over_time_minutes.pdf")
OUTPUT_PNG = Path("replicas_over_time_minutes.png")
OUTPUT_CSV = Path("replicas_per_minute.csv")


def load_replicas_per_minute(csv_path: Path) -> pd.DataFrame:
    """
    Calculate average total application replicas per elapsed minute.

    For each minute:
      1. Keep Online Boutique deployment rows.
      2. Average pod count for each deployment within that minute.
      3. Sum those per-deployment averages.

    This avoids incorrectly summing repeated measurements when multiple
    samples share the same minute-level timestamp.
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

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: "
            f"{sorted(missing)}"
        )

    # -----------------------------------------------------------------
    # Keep only application deployment measurements
    # -----------------------------------------------------------------

    app_df = df.loc[
        (df["Scope"] == "deployment")
        & (df["Name"].isin(APPLICATION_DEPLOYMENTS)),
        ["Timestamp", "Name", "Pods"],
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
            f"No matching application deployments found in {csv_path}.\n"
            f"Available deployment names: {available_names}"
        )

    # -----------------------------------------------------------------
    # Parse timestamp
    #
    # format="mixed" allows mixed timestamp styles such as:
    #
    # 2026-08-24 20:30:15
    # 24/08/2026 20:30
    #
    # dayfirst=True handles DD/MM/YYYY timestamps correctly.
    # -----------------------------------------------------------------

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
            f"No valid replica measurements found in {csv_path}"
        )

    # -----------------------------------------------------------------
    # Convert timestamps to elapsed minutes
    # -----------------------------------------------------------------

    first_timestamp = app_df["Timestamp"].min()

    app_df["ElapsedSeconds"] = (
        app_df["Timestamp"] - first_timestamp
    ).dt.total_seconds()

    app_df["Minute"] = (
        app_df["ElapsedSeconds"] // 60
    ).astype(int)

    # -----------------------------------------------------------------
    # Step 1:
    # Average each deployment's replica count within each minute.
    #
    # Example:
    #
    # Minute 0:
    # frontend:        1, 1, 2, 2 -> 1.5
    # currencyservice: 1, 1, 1, 1 -> 1.0
    # ...
    # -----------------------------------------------------------------

    deployment_minute_avg = (
        app_df.groupby(
            ["Minute", "Name"],
            as_index=False,
        )["Pods"]
        .mean()
        .rename(
            columns={
                "Pods": "AverageDeploymentReplicas"
            }
        )
    )

    # -----------------------------------------------------------------
    # Step 2:
    # Sum the average replica count of all deployments.
    #
    # This gives the average total application replicas for each minute.
    # -----------------------------------------------------------------

    minute_replicas = (
        deployment_minute_avg.groupby(
            "Minute",
            as_index=False,
        )["AverageDeploymentReplicas"]
        .sum()
        .rename(
            columns={
                "AverageDeploymentReplicas": "AverageReplicas"
            }
        )
    )

    # -----------------------------------------------------------------
    # Count how many application deployments were present per minute.
    # Useful for debugging missing measurements.
    # -----------------------------------------------------------------

    deployment_counts = (
        deployment_minute_avg.groupby(
            "Minute"
        )["Name"]
        .nunique()
        .reset_index(
            name="Deployments"
        )
    )

    minute_replicas = minute_replicas.merge(
        deployment_counts,
        on="Minute",
        how="left",
    )

    return minute_replicas


def main() -> None:
    all_results: list[pd.DataFrame] = []

    fig, ax = plt.subplots(
        figsize=(8.4, 5.2)
    )

    plotted = 0

    # -----------------------------------------------------------------
    # Process each autoscaler result
    # -----------------------------------------------------------------

    for autoscaler, csv_path in INPUT_FILES.items():
        try:
            replicas = load_replicas_per_minute(
                csv_path
            )

        except (FileNotFoundError, ValueError) as exc:
            print(
                f"[SKIP] {autoscaler}: {exc}"
            )
            continue

        # -------------------------------------------------------------
        # Debug preview
        # -------------------------------------------------------------

        print()
        print(f"=== {autoscaler} ===")

        print(
            replicas[
                [
                    "Minute",
                    "AverageReplicas",
                    "Deployments",
                ]
            ].head(10)
        )

        # -------------------------------------------------------------
        # Store output for combined CSV
        # -------------------------------------------------------------

        output = replicas.copy()

        output.insert(
            0,
            "Autoscaler",
            autoscaler,
        )

        all_results.append(output)

        # -------------------------------------------------------------
        # Plot
        # -------------------------------------------------------------

        ax.plot(
            replicas["Minute"],
            replicas["AverageReplicas"],
            color=COLORS[autoscaler],
            linewidth=2.3,
            label=autoscaler,
        )

        plotted += 1

    if plotted == 0:
        raise RuntimeError(
            "No replica data was plotted. "
            "Check the filenames and deployment names."
        )

    # -----------------------------------------------------------------
    # Save combined per-minute results
    # -----------------------------------------------------------------

    if all_results:
        combined = pd.concat(
            all_results,
            ignore_index=True,
        )

        combined.to_csv(
            OUTPUT_CSV,
            index=False,
        )

    # -----------------------------------------------------------------
    # Plot formatting
    # -----------------------------------------------------------------

    ax.set_xlabel(
        "Elapsed Time (minutes)"
    )

    ax.set_ylabel(
        "Average Total Replicas"
    )

    ax.set_title(
        "Average Application Replica Count over Time"
    )

    ax.grid(
        True,
        linestyle=":",
        linewidth=0.8,
        alpha=0.65,
    )

    ax.legend(
        loc="lower right",
        ncol=1,
        frameon=True,
        framealpha=0.95,
    )

    ax.set_xlim(
        left=0
    )

    # Online Boutique has 11 components including redis-cart.
    ax.set_ylim(
        bottom=10
    )

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
    print(f"Saved: {OUTPUT_PNG}")
    print(f"Saved: {OUTPUT_PDF}")
    print(f"Saved: {OUTPUT_CSV}")

    plt.show()


if __name__ == "__main__":
    main()
