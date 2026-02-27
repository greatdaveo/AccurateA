"""
Standalone script to seed UK Chart of Accounts.

Usage:
    python -m scripts.seed_uk_coa --template limited_company_uk
    python -m scripts.seed_uk_coa --template sole_trader_uk --company-id <uuid>
    python -m scripts.seed_uk_coa --list
"""

import argparse
import sys
from app.utils.database import SessionLocal
from app.services.coa_template_service import COATemplateService
from app.models.company import Company


def main():
    parser = argparse.ArgumentParser(description="Seed UK Chart of Accounts")
    parser.add_argument(
        "--template",
        choices=["limited_company_uk", "sole_trader_uk", "micro_entity_uk"],
        help="Template to seed",
    )
    parser.add_argument(
        "--company-id",
        help="Company ID to seed (if omitted, seeds the first company found)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Deactivate existing accounts before seeding",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available templates and exit",
    )

    args = parser.parse_args()

    if args.list:
        print("\nAvailable templates:")
        print("=" * 60)
        for tmpl in COATemplateService.list_templates():
            print(f"\n  {tmpl['key']}")
            print(f"  {tmpl['name']}")
            print(f"  {tmpl['description']}")
            print(f"  Accounts: {tmpl['account_count']}")
        print()
        return

    if not args.template:
        parser.error("--template is required (unless using --list)")

    db = SessionLocal()

    try:
        # Find company
        if args.company_id:
            company = db.query(Company).filter(
                Company.id == args.company_id
            ).first()
        else:
            company = db.query(Company).first()

        if not company:
            print("Error: No company found. Create a company first.")
            sys.exit(1)

        print(f"\nSeeding '{args.template}' for company: {company.name}")
        print(f"Company ID: {company.id}")

        if args.clear:
            print("Clearing existing accounts...")

        service = COATemplateService(db)
        result = service.seed_template(
            company_id=str(company.id),
            template_key=args.template,
            clear_existing=args.clear,
        )

        print(f"\n Done!")
        print(f"Template: {result['template_name']}")
        print(f"Created: {result['created']} accounts")
        print(f"Skipped: {result['skipped']} (already existed)")
        print(f"Total in template: {result['total_in_template']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
