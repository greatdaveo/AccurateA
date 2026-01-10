"""
Database Optimization Utilities
Add indexes for better query performance.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def add_performance_indexes(db: Session):
    """
    Add database indexes for common queries
    Run this once after initial setup.
    """
    indexes = [
        # Transactions - most queried table
        "CREATE INDEX IF NOT EXISTS idx_txn_company_date ON transactions(company_id, transaction_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_txn_company_status ON transactions(company_id, classification_status)",
        "CREATE INDEX IF NOT EXISTS idx_txn_company_category ON transactions(company_id, category)",
        "CREATE INDEX IF NOT EXISTS idx_txn_amount ON transactions(amount DESC)",

        # Journal Entries
        "CREATE INDEX IF NOT EXISTS idx_je_company_date ON journal_entries(company_id, entry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_je_status ON journal_entries(status)",
        "CREATE INDEX IF NOT EXISTS idx_jel_entry_account ON journal_entry_lines(journal_entry_id, account_id)",

        # Accounts
        "CREATE INDEX IF NOT EXISTS idx_account_company_type ON accounts(company_id, account_type)",
        "CREATE INDEX IF NOT EXISTS idx_account_code ON accounts(company_id, account_code)",

        # Assets
        "CREATE INDEX IF NOT EXISTS idx_asset_company_status ON assets(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_asset_depreciable ON assets(company_id, is_depreciable) WHERE is_depreciable = true",

        # Anomalies
        "CREATE INDEX IF NOT EXISTS idx_anomaly_company_severity ON anomalies(company_id, severity)",
        "CREATE INDEX IF NOT EXISTS idx_anomaly_status ON anomalies(company_id, status)",
    ]

    print("\nAdding performance indexes...")

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
            print(f"{idx_sql.split('idx_')[1].split(' ON')[0]}")
        except Exception as e:
            print(f"Error: {e}")

    db.commit()
    print("Indexes added\n")