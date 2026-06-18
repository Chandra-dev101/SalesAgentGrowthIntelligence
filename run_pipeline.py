"""Run the full Sales Agent Growth Intelligence pipeline.

Usage:
  python run_pipeline.py              # full run (all sources)
  python run_pipeline.py --skip-pull  # skip data pull, use cached JSONs
  python run_pipeline.py --pbi-only   # only pull Power BI (skip Kusto/Hub)
  python run_pipeline.py --step N     # run only step N (1=pull, 2=merge, 3=build)
"""
import sys, os, argparse, time

# Ensure the skill directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _config import DATA_DIR, OUTPUT_HTML


def main():
    parser = argparse.ArgumentParser(description='Sales Agent Growth Intelligence Pipeline')
    parser.add_argument('--skip-pull', action='store_true', help='Skip data pull, use cached JSONs')
    parser.add_argument('--pbi-only', action='store_true', help='Only pull Power BI data')
    parser.add_argument('--kusto-only', action='store_true', help='Only pull Kusto data')
    parser.add_argument('--step', type=int, help='Run only step N (1=pull, 2=merge, 3=build)')
    args = parser.parse_args()

    print("=" * 60)
    print("  Sales Agent Growth Intelligence — Pipeline")
    print("=" * 60)
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Output:   {OUTPUT_HTML}")
    print()

    t0 = time.time()

    # Step 1: Pull data
    if args.step is None or args.step == 1:
        if not args.skip_pull:
            print("━" * 40)
            print("STEP 1: Pull live data")
            print("━" * 40)

            if not args.kusto_only:
                print("\n[PBI] Pulling Power BI data...")
                try:
                    from _pull_pbi import pull_all
                    pull_all()
                except Exception as e:
                    print(f"  PBI pull failed: {e}")
                    print("  Continuing with cached data if available...")

            if not args.pbi_only:
                print("\n[Kusto] Pulling Kusto telemetry...")
                try:
                    from _pull_kusto import pull_kusto
                    pull_kusto()
                except Exception as e:
                    print(f"  Kusto pull failed: {e}")
                    print("  Continuing with cached data if available...")

            if not args.pbi_only and not args.kusto_only:
                print("\n[SuccessHub] Pulling community members...")
                try:
                    from _pull_successhub import pull_community_members
                    pull_community_members()
                except Exception as e:
                    print(f"  SuccessHub pull failed: {e}")
                    print("  Continuing with cached data if available...")
        else:
            print("STEP 1: SKIPPED (--skip-pull)")

    # Step 2: Merge
    if args.step is None or args.step == 2:
        print("\n" + "━" * 40)
        print("STEP 2: Merge data sources")
        print("━" * 40)
        from _merge_data import merge
        merge()

    # Step 3: Build HTML
    if args.step is None or args.step == 3:
        print("\n" + "━" * 40)
        print("STEP 3: Build HTML")
        print("━" * 40)
        from _build_html import build_html
        build_html()

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"  ✓ Pipeline complete in {elapsed:.1f}s")
    print(f"  Output: {OUTPUT_HTML}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
