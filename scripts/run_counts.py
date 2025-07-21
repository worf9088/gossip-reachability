# scripts/run_counts.py
from time import time
from src.enumerator import table_counts

for depth in (10, 12):          # 深度实验
    start = time()
    print(f"depth={depth}", table_counts(range(2, 10), depth=depth))
    print("elapsed", time() - start, "s")
