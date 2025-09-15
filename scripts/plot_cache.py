# scripts/plot_cache.py
from __future__ import annotations

"""
Plot cached results into figures for the CA2 deck.

Reads:
  - artifacts/layers_long.parquet (preferred) OR artifacts/layers_long.csv (fallback)
  - artifacts/summary.csv (for elapsed times etc.)

Produces:
  - artifacts/plots/any_n7_serial_vs_parallel.png
  - artifacts/plots/n4_per_protocol_serial.png
  - artifacts/plots/co_n6_parallel.png
  - artifacts/plots/elapsed_bars.png (optional)

Usage:
  # draw everything available
  python -m scripts.plot_cache

  # only some plots, custom outdir
  python -m scripts.plot_cache --plots any_n7 n4_overlay --outdir artifacts/plots2

Notes:
  - Uses matplotlib only (no seaborn).
  - Will skip plots gracefully if required data is not found.
"""

import argparse
import json
import sys
import pathlib
from typing import List, Optional

import pandas as pd
import matplotlib.pyplot as plt


# ---------------------- Paths & loading ----------------------
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "artifacts"
RUNS_DIR = ART_DIR / "runs"
PLOTS_DIR_DEFAULT = ART_DIR / "plots"

LONG_PARQUET = ART_DIR / "layers_long.parquet"
LONG_CSV = ART_DIR / "layers_long.csv"
SUMMARY_CSV = ART_DIR / "summary.csv"


def load_long() -> Optional[pd.DataFrame]:
    """Load long-table (level-wise) data."""
    if LONG_PARQUET.exists():
        try:
            df = pd.read_parquet(LONG_PARQUET)
            print(f"[load] {LONG_PARQUET}")
            return df
        except Exception as e:
            print(f"[warn] failed to read {LONG_PARQUET}: {e}")

    if LONG_CSV.exists():
        try:
            df = pd.read_csv(LONG_CSV)
            print(f"[load] {LONG_CSV}")
            return df
        except Exception as e:
            print(f"[warn] failed to read {LONG_CSV}: {e}")

    print("[warn] no layers_long parquet/csv found")
    return None


def load_summary() -> Optional[pd.DataFrame]:
    """Load summary table (one row per run)."""
    if not SUMMARY_CSV.exists():
        print(f"[warn] not found: {SUMMARY_CSV}")
        return None
    try:
        df = pd.read_csv(SUMMARY_CSV)
        print(f"[load] {SUMMARY_CSV}")
        return df
    except Exception as e:
        print(f"[warn] failed to read {SUMMARY_CSV}: {e}")
        return None


# ---------------------- Plot helpers ----------------------
def savefig(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    print(f"[ok] wrote {path}")


def series_from_long(df: pd.DataFrame, protocol: str, n: int, mode: str) -> Optional[pd.DataFrame]:
    """Return a tiny df with columns [level, states] sorted by level for (protocol, n, mode)."""
    if df is None:
        return None
    sel = df[(df["protocol"] == protocol) & (df["n"] == n) & (df["mode"] == mode)]
    if sel.empty:
        return None
    # In case of duplicates, aggregate by level
    grp = sel.groupby("level", as_index=False)["states"].sum().sort_values("level")
    return grp


# ---------------------- Individual plots ----------------------
def plot_any_n7(outdir: pathlib.Path, df_long: Optional[pd.DataFrame]):
    """ANY n=7, serial vs parallel layer growth."""
    if df_long is None:
        print("[skip] any_n7: no long-table data")
        return
    s = series_from_long(df_long, "ANY", 7, "serial")
    p = series_from_long(df_long, "ANY", 7, "parallel")
    if s is None or p is None:
        print("[skip] any_n7: need both serial and parallel for ANY n=7")
        return

    plt.figure(figsize=(8, 4.5))
    plt.plot(s["level"], s["states"], marker="o", label="serial")
    plt.plot(p["level"], p["states"], marker="o", label="parallel")
    plt.xlabel("Depth")
    plt.ylabel("States per level")
    plt.title("ANY n=7 — Level Growth (serial vs parallel)")
    plt.legend()
    savefig(outdir / "any_n7_serial_vs_parallel.png")


def plot_n4_overlay(outdir: pathlib.Path, df_long: Optional[pd.DataFrame]):
    """n=4 per-protocol overlay (serial): ANY/CO/LNS/TOK/SPI."""
    if df_long is None:
        print("[skip] n4_overlay: no long-table data")
        return

    protocols = ["ANY", "CO", "LNS", "TOK", "SPI"]
    found = 0

    plt.figure(figsize=(8, 4.5))
    for proto in protocols:
        s = series_from_long(df_long, proto, 4, "serial")
        if s is None:
            continue
        plt.plot(s["level"], s["states"], marker="o", label=proto)
        found += 1

    if found < 2:
        plt.close()
        print("[skip] n=4 overlay: fewer than 2 protocols available")
        return

    plt.xlabel("Depth")
    plt.ylabel("States per level")
    plt.title("n=4 — Per-Protocol Layer Growth (serial)")
    plt.legend()
    savefig(outdir / "n4_per_protocol_serial.png")


def plot_co_n6_parallel(outdir: pathlib.Path, df_long: Optional[pd.DataFrame]):
    """CO n=6 (parallel) layer growth."""
    if df_long is None:
        print("[skip] co_n6_parallel: no long-table data")
        return
    s = series_from_long(df_long, "CO", 6, "parallel")
    if s is None:
        print("[skip] CO n=6 parallel: no matching rows")
        return

    plt.figure(figsize=(8, 4.5))
    plt.plot(s["level"], s["states"], marker="o", label="CO n=6 parallel")
    plt.xlabel("Depth")
    plt.ylabel("States per level")
    plt.title("CO n=6 — Layer Growth (parallel)")
    plt.legend()
    savefig(outdir / "co_n6_parallel.png")


def plot_elapsed_bars(outdir: pathlib.Path, df_summary: Optional[pd.DataFrame]):
    """Bar chart of elapsed_sec for all runs in summary.csv (optional)."""
    if df_summary is None or df_summary.empty:
        print("[skip] elapsed_bars: no summary")
        return

    # Make a compact label: proto-n-d-mode(-wX-bY)
    def label_row(r):
        base = f"{r['protocol']}-n{int(r['n'])}-d{int(r['depth'])}-{r['mode']}"
        if r["mode"] == "parallel":
            w = str(int(r["workers"])) if pd.notna(r["workers"]) else "?"
            b = str(int(r["batch_size"])) if pd.notna(r["batch_size"]) else "?"
            base += f"-w{w}-b{b}"
        return base

    df = df_summary.copy()
    df["label"] = df.apply(label_row, axis=1)
    df = df.sort_values("elapsed_sec", ascending=True)

    plt.figure(figsize=(10, 5))
    plt.barh(range(len(df)), df["elapsed_sec"])
    plt.yticks(range(len(df)), df["label"])
    plt.xlabel("Elapsed seconds")
    plt.title("Elapsed time per run")
    plt.tight_layout()
    savefig(outdir / "elapsed_bars.png")


# ---------------------- CLI ----------------------
def main():
    parser = argparse.ArgumentParser(description="Plot cached results from artifacts/*.")
    parser.add_argument(
        "--outdir",
        default=str(PLOTS_DIR_DEFAULT),
        help="Output directory for figures (default: artifacts/plots)",
    )
    parser.add_argument(
        "--plots",
        nargs="*",
        choices=["any_n7", "n4_overlay", "co_n6", "elapsed"],
        help="Which plots to generate. Default: all available.",
    )
    args = parser.parse_args()

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df_long = load_long()
    df_summary = load_summary()

    # Decide which plots to run
    to_run = args.plots or ["any_n7", "n4_overlay", "co_n6", "elapsed"]

    if "any_n7" in to_run:
        plot_any_n7(outdir, df_long)

    if "n4_overlay" in to_run:
        plot_n4_overlay(outdir, df_long)

    if "co_n6" in to_run:
        plot_co_n6_parallel(outdir, df_long)

    if "elapsed" in to_run:
        plot_elapsed_bars(outdir, df_summary)


if __name__ == "__main__":
    main()
