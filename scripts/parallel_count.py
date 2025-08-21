# scripts/parallel_count.py
from __future__ import annotations

import argparse
import time
import multiprocessing as mp
import sys
import pathlib
import csv
import json
from datetime import datetime

# 允许用 “python scripts/parallel_count.py” 直接运行：
# 把项目根目录加入 sys.path，避免 import src 失败
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import ReachabilityEngine


def positive_int(val: str) -> int:
    iv = int(val)
    if iv <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return iv


def _ensure_parent(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _save_layer_sizes_csv(path: pathlib.Path, per_level: list[int]) -> None:
    _ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["depth", "count"])
        for d, c in enumerate(per_level):
            w.writerow([d, c])


def _save_layer_sizes_npy(path: pathlib.Path, per_level: list[int]) -> bool:
    try:
        import numpy as np  # type: ignore
    except Exception as e:
        print(f"[warn] NumPy not available ({e}); skip NPY save.")
        return False
    _ensure_parent(path)
    np.save(str(path), np.array(per_level, dtype=int))
    return True


def _key_to_jsonable(k) -> list:
    # k: Tuple[Tuple[int, ...], ...] -> List[List[int]]
    return [list(inner) for inner in k]


def _save_layers_csv(path: pathlib.Path, layers: dict[int, set]) -> None:
    _ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["depth", "key"])  # key 为 JSON 字符串
        for d in sorted(layers.keys()):
            for k in layers[d]:
                w.writerow([d, json.dumps(_key_to_jsonable(k), separators=(",", ":"))])


def _save_meta_json(path: pathlib.Path, args: argparse.Namespace, res: dict, per_level: list[int]) -> None:
    _ensure_parent(path)
    meta = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "params": {
            "protocol": args.protocol,
            "n": args.n,
            "max_depth": args.depth,
            "workers": args.workers,
            "batch_size": args.batch_size,
            "mode": "serial" if args.serial else "parallel",
        },
        "summary": {
            "reachable_count": res.get("reachable_count"),
            "transitions": res.get("transitions"),
            "depths": len(per_level),
            "per_level": per_level,
        },
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# -------- Parquet I/O（可选） --------
def _try_import_pandas() -> tuple | None:
    try:
        import pandas as pd  # type: ignore
        return (pd,)
    except Exception as e:
        print(f"[warn] pandas not available ({e}); skip Parquet save.")
        return None


def _save_per_level_parquet(path: pathlib.Path, per_level: list[int]) -> bool:
    pk = _try_import_pandas()
    if pk is None:
        return False
    (pd,) = pk
    _ensure_parent(path)
    df = pd.DataFrame({"depth": list(range(len(per_level))), "count": per_level})
    try:
        df.to_parquet(path, index=False)
        return True
    except Exception as e:
        print(f"[warn] Failed to save Parquet ({e}); skip.")
        return False


def _save_layers_parquet(path: pathlib.Path, layers: dict[int, set]) -> bool:
    pk = _try_import_pandas()
    if pk is None:
        return False
    (pd,) = pk
    _ensure_parent(path)
    rows = []
    for d in sorted(layers.keys()):
        for k in layers[d]:
            rows.append(
                {"depth": d, "key_json": json.dumps(_key_to_jsonable(k), separators=(",", ":"))}
            )
    try:
        df = pd.DataFrame(rows, columns=["depth", "key_json"])
        df.to_parquet(path, index=False)
        return True
    except Exception as e:
        print(f"[warn] Failed to save Parquet ({e}); skip.")
        return False


def main() -> None:
    default_workers = max(1, mp.cpu_count() - 1)

    parser = argparse.ArgumentParser(
        description="Level-parallel BFS reachability counter"
    )
    parser.add_argument(
        "-p",
        "--protocol",
        default="ANY",
        choices=["ANY", "CO", "LNS", "TOK", "SPI", "ATK"],
        help="Protocol to evaluate",
    )
    parser.add_argument("--n", type=positive_int, default=9, help="Number of agents")
    parser.add_argument(
        "-d", "--depth", type=positive_int, default=12, help="Max BFS depth"
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=positive_int,
        default=default_workers,
        help="Process pool size",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=128,
        help="States per task batch for parallel expansion",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-level progress"
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Run serial BFS (for comparison baseline)",
    )

    # ==== 输出选项 ====
    parser.add_argument(
        "--out-prefix",
        type=str,
        default=None,
        help="Path prefix for outputs (will create: *_per_level.csv, *_per_level.npy, *_meta.json). "
             "If omitted but --dump-layers/--out-parquet is set, a timestamped prefix under ./runs/ will be used.",
    )
    parser.add_argument(
        "--dump-layers",
        action="store_true",
        help="Additionally save all canonical keys into a single CSV (may be large).",
    )
    parser.add_argument(
        "--out-parquet",
        action="store_true",
        help="Additionally save per-level and (optionally) layers to Parquet (requires pandas + pyarrow/fastparquet).",
    )

    args = parser.parse_args()

    print(
        f"Running {args.protocol}  n={args.n}  depth={args.depth}  "
        f"workers={args.workers}  batch={args.batch_size}  "
        f"mode={'serial' if args.serial else 'parallel'}"
    )

    eng = ReachabilityEngine(args.protocol)

    t0 = time.perf_counter()
    if args.serial:
        res = eng.bfs(args.n, max_depth=args.depth)
    else:
        # 需要 src/engine.py 中的 bfs_parallel(protocol, n, max_depth, workers, batch_size, verbose)
        res = eng.bfs_parallel(
            args.n,
            max_depth=args.depth,
            workers=args.workers,
            batch_size=args.batch_size,
            verbose=args.verbose,
        )
    t1 = time.perf_counter()

    print("reachable_count:", res["reachable_count"])
    print("transitions    :", res["transitions"])

    # 组装 per_level 数组（连续深度，从 0 到 max_depth 或最后一层）
    depths = sorted(res["layers"].keys())
    per_level = [res["layer_sizes"].get(d, 0) for d in range(depths[0], depths[-1] + 1)]
    print("per_level      :", per_level)
    print(f"elapsed        : {t1 - t0:.2f}s")

    # ====== 输出到文件 ======
    need_prefix = args.dump_layers or args.out_parquet or (args.out_prefix is not None)
    prefix = args.out_prefix
    if prefix is None and need_prefix:
        ts = int(time.time())
        prefix = f"runs/{args.protocol}_n{args.n}_d{args.depth}_{ts}"
        print(f"[info] --out-prefix not set; using default: {prefix}")

    if prefix:
        base = pathlib.Path(prefix)

        # 基础：CSV / NPY / JSON
        csv_path = base.with_name(base.name + "_per_level.csv")
        npy_path = base.with_name(base.name + "_per_level.npy")
        meta_path = base.with_name(base.name + "_meta.json")
        _save_layer_sizes_csv(csv_path, per_level)
        if _save_layer_sizes_npy(npy_path, per_level):
            pass
        _save_meta_json(meta_path, args, res, per_level)
        print(f"[saved] {csv_path}")
        if npy_path.exists():
            print(f"[saved] {npy_path}")
        print(f"[saved] {meta_path}")

        # 选配：全部层 keys（CSV）
        if args.dump_layers:
            layers_csv = base.with_name(base.name + "_layers.csv")
            _save_layers_csv(layers_csv, res["layers"])
            print(f"[saved] {layers_csv}")

        # 选配：Parquet
        if args.out_parquet:
            per_level_parquet = base.with_name(base.name + "_per_level.parquet")
            ok1 = _save_per_level_parquet(per_level_parquet, per_level)
            if ok1:
                print(f"[saved] {per_level_parquet}")
            if args.dump_layers:
                layers_parquet = base.with_name(base.name + "_layers.parquet")
                ok2 = _save_layers_parquet(layers_parquet, res["layers"])
                if ok2:
                    print(f"[saved] {layers_parquet}")


if __name__ == "__main__":
    # Windows 多进程的标准保护
    mp.freeze_support()
    main()
