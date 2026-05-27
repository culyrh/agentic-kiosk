import csv, statistics
from pathlib import Path

def load_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))

old = load_csv("tests/results/stt_20260513_024112.csv")
new = load_csv("tests/results/stt_20260520_180628.csv")

def stats(data, label):
    vals = [int(r["stt_ms"]) for r in data if int(r["stt_ms"]) < 100000]
    print(f"{label}: count={len(vals)} avg={statistics.mean(vals):.0f}ms median={statistics.median(vals):.0f}ms max={max(vals)}ms")
    # by speaker
    from collections import defaultdict
    spk = defaultdict(list)
    for r in data:
        ms = int(r["stt_ms"])
        if ms < 100000:
            spk[r["speaker"]].append(ms)
    for k, v in sorted(spk.items()):
        print(f"  {k}: avg={statistics.mean(v):.0f}ms  median={statistics.median(v):.0f}ms")

stats(old, "OLD (20260513)")
print()
stats(new, "NEW (20260520_180628)")
