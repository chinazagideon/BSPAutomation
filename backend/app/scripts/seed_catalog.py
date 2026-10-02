"""CLI Runner for Multi-Vertical Catalog Seeding (ADR-0044).

Usage:
    python -m app.scripts.seed_catalog [--reset] [--merchant-slug <slug>]

Examples:
    docker exec bsp_api python -m app.scripts.seed_catalog --reset
    docker exec bsp_api python -m app.scripts.seed_catalog --merchant-slug alaba-agro
"""

import sys
import asyncio
import argparse
import structlog

from app.core.database import async_session_factory
from app.contexts.knowledge.seeder import CatalogSeeder

logger = structlog.get_logger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Seed multi-vertical catalog offerings and warm Redis manifests.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing catalog entries for target merchants before seeding",
    )
    parser.add_argument(
        "--merchant-slug",
        type=str,
        default=None,
        help="Seed only a specific merchant (e.g. alaba-agro, lekki-glow, horizon-tech)",
    )

    args = parser.parse_args()

    print("\n🌱 ========================================================")
    print("   BSP WHATSAPP ENTERPRISE: MULTI-VERTICAL CATALOG SEEDER")
    print("==========================================================")
    print(f" Mode: {'RESET & RELOAD' if args.reset else 'IDEMPOTENT UPSERT'}")
    if args.merchant_slug:
        print(f" Target Merchant: {args.merchant_slug}")
    else:
        print(" Target Merchants: ALL (Alaba Agro, Lekki Glow, Horizon Tech)")
    print("==========================================================\n")

    async with async_session_factory() as session:
        try:
            summary = await CatalogSeeder.seed_all(
                session=session,
                reset=args.reset,
                merchant_slug=args.merchant_slug,
            )
            print("✅ Seeding completed successfully!")
            print(f"   • Merchants Provisioned: {summary['merchants_seeded']}")
            print(f"   • Offerings Upserted:    {summary['offerings_seeded']}")
            print(f"   • Redis Manifests Cached:{summary['manifests_warmed']}")
            print("==========================================================\n")
            sys.exit(0)
        except Exception as err:
            print(f"\n❌ Seeding failed with error: {err}")
            logger.exception("seeding_cli_failed", error=str(err))
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
