# scripts/plot_n4_overlay.py
from __future__ import annotations
import argparse, ast
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

# ---- helpers ----

def _guess_mode(df: pd.DataFrame) -> pd.Series:
    """If 'mode' missing, infer: workers>0 => parallel else serial."""
    if "mode" in df.columns:
        return df["mode"].astype(str)
    if "workers" in df.columns:
        return df["workers"].fillna(0).astype(int).map(lambda w: "parallel" if w > 0 else "serial")
    # fallback: all serial
    return pd.Series(["serial"] * len(df), index=df.index)

def _unify_long_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Rename possibly different column names to a standard schema:
       protocol, n, mode, layer, size
    """
    cols = {c.lower(): c for c in df.columns}  # map lower->original
    # protocol
    proto_col = cols.get("protocol") or cols.get("proto")
    if not proto_col:
        raise KeyError(f"Missing 'protocol' column in {list(df.columns)}")

    # n
    n_col = cols.get("n") or cols.get("agents") or cols.get("num_agents")
    if not n_col:
        raise KeyError(f"Missing 'n' (agents) column in {list(df.columns)}")

    # layer index
    layer_col = (
        cols.get("layer")
        or cols.get("level")
        or cols.get("depth_layer")  # rare
        or cols.get("layer_idx")
        or cols.get("layer_index")
        or cols.get("depth")        # sometimes stored as depth
    )
    if not layer_col:
        raise KeyError(f"Missing layer/level/depth column in {list(df.columns)}")

    # size (frontier size)
    size_col = (
        cols.get("size")
        or cols.get("count")
        or cols.get("frontier")
        or cols.get("frontier_size")
        or cols.get("states")
        or cols.get("value")
    )
    if not size_col:
        raise KeyError(f"Missing size/count/frontier column in {list(df.columns)}")

    out = pd.DataFrame({
        "protocol": df[proto_col].astype(str).str.upper(),
        "n": pd.to_numeric(df[n_col], errors="coerce").astype("Int64"),
        "layer": pd.to_numeric(df[layer_col], errors="coerce").astype("Int64"),
        "size": pd.to_numeric(df[size_col], errors="coerce").astype("Int64"),
    })
    # mode: from column or guessed
    out["mode"] = _guess_mode(df).astype(str)
    return out

def _load_from_parquet(p_parquet: Path, n: int, mode: str) -> pd.DataFrame | None:
    if not p_parquet.exists():
        return None
    df_raw = pd.read_parquet(p_parquet)
    df = _unify_long_schema(df_raw)
    df = df[(df["n"] == n) & (df["mode"] == mode)]
    if df.empty:
        return pd.DataFrame(columns=["protocol","n","mode","layer","size"])
    return df[["protocol","n","mode","layer","size"]].copy()

def _load_from_csv(p_csv: Path, n: int, mode: str) -> pd.DataFrame | None:
    if not p_csv.exists():
        return None
    summ = pd.read_csv(p_csv)
    # expected columns at least: protocol, n, mode, layer_sizes (dict-like string)
    need = {"protocol","n","mode","layer_sizes"}
    if not need.issubset(set(summ.columns)):
        # Sometimes 'mode' might be missing in summary; assume serial
        if "mode" not in summ.columns:
            summ["mode"] = "serial"
        if "layer_sizes" not in summ.columns:
            return None
    summ = summ[(summ["n"] == n) & (summ["mode"] == mode)].copy()
    rows = []
    for _, row in summ.iterrows():
        proto = str(row["protocol"]).upper()
        try:
            layer_dict = ast.literal_eval(str(row["layer_sizes"]))
        except Exception:
            continue
        for k, v in layer_dict.items():
            rows.append({
                "protocol": proto,
                "n": n,
                "mode": mode,
                "layer": int(k),
                "size": int(v),
            })
    if not rows:
        return pd.DataFrame(columns=["protocol","n","mode","layer","size"])
    return pd.DataFrame(rows)

def load_layers(n: int = 4, mode: str = "serial", prefer: str = "auto") -> pd.DataFrame:
    """Return long-form df with: protocol,n,mode,layer,size.
       prefer: 'auto'|'parquet'|'csv'
    """
    art = Path("artifacts")
    p_parquet = art / "layers_long.parquet"
    p_csv = art / "summary.csv"

    if prefer == "parquet":
        df = _load_from_parquet(p_parquet, n, mode)
        if df is not None and not df.empty:
            return df
        raise RuntimeError("Parquet chosen but no usable rows found. Try --prefer csv.")

    if prefer == "csv":
        df = _load_from_csv(p_csv, n, mode)
        if df is not None and not df.empty:
            return df
        raise RuntimeError("CSV chosen but no usable rows found. Did precompute write summary.csv?")

    # auto
    df = _load_from_parquet(p_parquet, n, mode)
    if df is not None and not df.empty:
        return df
    df = _load_from_csv(p_csv, n, mode)
    if df is not None and not df.empty:
        return df
    raise RuntimeError(
        "No data found for plotting. Run 'python -m scripts.precompute_cache --all' first.\n"
        f"Checked: {p_parquet} and {p_csv}"
    )

# ---- plotting ----

def plot_n4_overlay(outdir: Path, n: int = 4, mode: str = "serial", prefer: str = "auto") -> Path:
    df = load_layers(n=n, mode=mode, prefer=prefer)
    order = ["ANY","CO","LNS","TOK","SPI"]
    df["protocol"] = pd.Categorical(df["protocol"], categories=order, ordered=True)

    plt.figure(figsize=(9, 4.5), dpi=160)
    for proto in order:
        d = df[df["protocol"] == proto].sort_values("layer")
        if d.empty:
            continue
        plt.plot(d["layer"], d["size"], marker="o", linewidth=1.8, label=proto)

    plt.xlabel("BFS depth (layer)")
    plt.ylabel("unique states at layer")
    plt.title(f"n={n}, {mode} BFS — per-layer frontier sizes")
    plt.grid(True, alpha=0.25, linewidth=0.6)
    plt.legend(loc="best", ncol=3, frameon=False)

    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"n{n}_per_protocol_{mode}.png"
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path

# ---- cli ----

def main():
    ap = argparse.ArgumentParser(
        description="Overlay per-layer curves for n across protocols (serial by default)."
    )
    ap.add_argument("--outdir", default="artifacts/plots", help="Output directory for the PNG")
    ap.add_argument("--n", type=int, default=4, help="Number of agents (default: 4)")
    ap.add_argument("--mode", choices=["serial","parallel"], default="serial", help="BFS mode (default: serial)")
    ap.add_argument("--prefer", choices=["auto","parquet","csv"], default="auto",
                    help="Data source preference (default: auto)")
    args = ap.parse_args()

    out = plot_n4_overlay(Path(args.outdir), n=args.n, mode=args.mode, prefer=args.prefer)
    print(f"[ok] wrote {out}")

if __name__ == "__main__":
    main()
