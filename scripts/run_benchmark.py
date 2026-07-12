"""Generate the §5.2 instance suite and produce the measured Table 5.1 data.

Run:  .venv\\Scripts\\python.exe scripts\\run_benchmark.py [--per-tier 10]
          [--tiers N14,N24] [--backends exact,sa,greedy,qaoa_sim]
          [--telemetry path/to/events.jsonl]

With --telemetry the generator is refitted to real registry profiles (§6.4);
otherwise it uses the shipped default fit. QAOA backends only run on tiers
whose variable count fits the statevector cap; skips are recorded, never
silent. Results land in results/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.experiments import FittedParams, SIZE_TIERS, generate_suite, run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-tier", type=int, default=10)
    parser.add_argument("--tiers", default="N14,N24,N40,N54,N84")
    parser.add_argument("--backends", default="exact,sa,greedy")
    parser.add_argument("--restarts", type=int, default=3)
    parser.add_argument("--budget-s", type=float, default=60.0)
    parser.add_argument("--qaoa-p", type=int, default=2)
    parser.add_argument("--telemetry", default="")
    args = parser.parse_args()

    params = FittedParams()
    if args.telemetry:
        from src.registry import Registry
        params = FittedParams.from_registry(Registry.from_telemetry(args.telemetry))
        print(f"refit from telemetry: u_dom={params.u_dominant_mean:.3f} "
              f"u_other={params.u_other_mean:.3f} k={params.n_categories}")

    wanted = {t.strip() for t in args.tiers.split(",")}
    tiers = [t for t in SIZE_TIERS if t[0] in wanted]
    print(f"generating {args.per_tier} instances/tier for {[t[0] for t in tiers]} "
          "(CBC-certified, brute-force cross-checked below 22 vars) ...")
    suite = generate_suite(per_tier=args.per_tier, params=params, tiers=tiers)
    print(f"  {len(suite)} instances certified")

    backends = [b.strip() for b in args.backends.split(",")]
    detail, summary = run_benchmark(suite, backends=backends,
                                    restarts=args.restarts,
                                    budget_s=args.budget_s, qaoa_p=args.qaoa_p)
    print(f"wrote {detail}\nwrote {summary}\n")
    for line in summary.read_text(encoding="utf-8").splitlines():
        print("  " + line)


if __name__ == "__main__":
    main()
