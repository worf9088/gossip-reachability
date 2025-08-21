# scripts/run_expectation_large.py
import csv, math
import matplotlib.pyplot as plt
from src.metrics import expected_length

protocols = ["ANY", "TOK", "SPI", "CO", "LNS"]  # 如已实现 ATK 也可加上 "ATK"
ns = range(11, 16)
runs = 2000

results = {}
for proto in protocols:
    means = []
    for n in ns:
        mu, _ = expected_length(proto, n, runs=runs)  # 你的 expected_length 如只返回 mean，就改为 mu = expected_length(...)
        means.append(mu)
    results[proto] = means
    plt.plot(ns, means, marker='o', label=proto)

ref = [n * math.log2(n) for n in ns]
plt.plot(ns, ref, 'k--', label='n log n (scaled)')
plt.xlabel("Agents (n)")
plt.ylabel("Expected calls")
plt.legend()
plt.tight_layout()
plt.savefig("benchmarks/expectation_n11_15.png", dpi=300)

with open("benchmarks/expectation_n11_15.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["n"] + protocols)
    for i, n in enumerate(ns):
        w.writerow([n] + [results[p][i] for p in protocols])

print("Done: benchmarks/expectation_n11_15.png & .csv")
