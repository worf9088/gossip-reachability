import csv
import matplotlib.pyplot as plt
from src.metrics import expected_length

protocols = ["ANY", "TOK", "SPI", "CO", "LNS"]
ns = range(2, 11)
runs = 5000

results = {}

for proto in protocols:
    means = []
    for n in ns:
        mean_len, _ = expected_length(proto, n, runs=runs)
        means.append(mean_len)
    results[proto] = means
    plt.plot(ns, means, marker='o', label=proto)

# 参考线 n log2 n
import math
ref = [n * math.log2(n) for n in ns]
plt.plot(ns, ref, 'k--', label='n log n (scaled)')
plt.xlabel("Agents (n)")
plt.ylabel("Expected calls")
plt.legend()
plt.tight_layout()
plt.savefig("benchmarks/expectation_n2_10.png", dpi=300)

# 导出 CSV
with open("benchmarks/expectation_table.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["n"] + list(protocols))
    for i, n in enumerate(ns):
        writer.writerow([n] + [results[p][i] for p in protocols])

print("Finished. Plot and CSV saved in benchmarks/.")
