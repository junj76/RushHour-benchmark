#!/usr/bin/env python3
"""Model zswap's two-sided capacity limit on this device.

zswap pages are compressed into a zsmalloc pool (RAM, unreclaimable here: the kernel exposes no
shrinker) and each stored page still occupies one swap slot on the flash swap file. So the usable
amount of swapped data is bounded from two sides:

    U_eff = min(S, P_eff / Cr)

    S     flash swap file size (MiB)                        -> slot-bound regime
    Cr    compression ratio compressed/uncompressed          (~0.33 measured)
    P_eff the pool size the system actually tolerates (MiB)  -> lmkd fires before max_pool_percent
          is reached, so the configured cap p*R is NOT the binding one

Calibration on tokay (measured):
  * Cr  = 0.326 / 0.339 (zswap runs), 0.341 (zram)          -> use 0.33
  * pool peaks: 330 MiB (S=1024), 696 MiB (S=2048)          -> both slot-bound, so they only bound
    P_eff from below (P_eff >= 696). The live device held 824 MiB with MemFree at 248 MiB, so
    P_eff >= 824 MiB.
  * configured cap = max_pool_percent * MemTotal = 20% * 7556 MiB = 1511 MiB -> upper bound.
  Hence P_eff in [824, 1511] MiB and U_eff(saturation) = P_eff/Cr in [2497, 4579] MiB.

Usage:
  python3 tools/zswap_model.py
  python3 tools/zswap_model.py --p-eff 824 --cr 0.33
"""
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mem-total-mib", type=float, default=7556.0, help="MemTotal in MiB")
    parser.add_argument("--max-pool-percent", type=float, default=20.0)
    parser.add_argument("--cr", type=float, default=0.33, help="compression ratio")
    parser.add_argument("--p-eff", type=float, default=824.0, help="pool MiB the system tolerates")
    parser.add_argument("--sizes", default="512,1024,2048,4096,8192")
    args = parser.parse_args()

    p_cap = args.mem_total_mib * args.max_pool_percent / 100.0
    u_ceiling = args.p_eff / args.cr
    s_star = u_ceiling

    print("parameters")
    print("  MemTotal            %.0f MiB" % args.mem_total_mib)
    print("  pool cap (p*R)      %.0f MiB  (%.0f%% of RAM)" % (p_cap, args.max_pool_percent))
    print("  tolerated pool P_eff %.0f MiB  (%.1f%% of RAM)  -> bound from measurements" % (
        args.p_eff, args.p_eff / args.mem_total_mib * 100.0))
    print("  compression ratio   %.2f" % args.cr)
    print("  slot-bound ceiling  U = P_eff/Cr = %.0f MiB" % u_ceiling)
    print("  crossover           S* = %.0f MiB  (file sizes above this stop helping)" % s_star)
    print()
    print("| swap file S (MiB) | regime | U_eff (MiB) | pool P (MiB) | P / cap | marginal gain |")
    print("|---|---|---|---|---|---|")
    previous = None
    for size in [float(x) for x in args.sizes.split(",")]:
        u_eff = min(size, u_ceiling)
        pool = args.cr * u_eff
        regime = "slot-bound" if size <= u_ceiling else "pool/pressure-bound"
        gain = "" if previous in (None, 0) else "%+.0f%%" % ((u_eff - previous) / previous * 100.0)
        print("| %.0f | %s | %.0f | %.0f | %.0f%% | %s |" % (
            size, regime, u_eff, pool, pool / p_cap * 100.0, gain))
        previous = u_eff
    print()
    print("predictions to verify on the device")
    print("  1. -t 3 -f 4096: pool should plateau at ~%.0f MiB (not %.0f MiB), and swap usage"
          % (args.p_eff, args.cr * 4096.0))
    print("     should stop near %.0f MiB, not near 4096 MiB." % u_ceiling)
    print("  2. -t 3 -f 2048 vs -f 4096: expect little to no improvement (both near saturation).")
    print("  3. lower max_pool_percent to 5%% (~%.0f MiB): accept_threshold_percent then rejects pages"
          % (args.mem_total_mib * 5.0 / 100.0))
    print("     so the pool plateaus at the CAP and the excess goes to flash -> first regime where")
    print("     the flash file size really matters.")


if __name__ == "__main__":
    main()
