from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.utils.database import SessionLocal
from app.models import Company, Transaction, JournalEntry, PlaidItem
from app.services.plaid_service import PlaidService
from app.agents.classification_agent import ClassificationAgent
from app.agents.journal_entry_agent import JournalEntryAgent
from app.services.reconciliation_service import ReconciliationService
from app.services.anomaly_service import AnomalyService
from app.services.tax_service import TaxService
from app.services.depreciation_service import DepreciationService


class SchedulerService:
    """Runs daily jobs to keep all accounting data up to date automatically"""
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.setup_jobs()

    def setup_jobs(self):
        """Configure all scheduled jobs"""
        #Daily automation at 2 AM
        self.scheduler.add_job(
            func=self.daily_automation_job,
            trigger=CronTrigger(hour=2, minute=0), #2:00 AM Daily
            id="daily_automation",
            name="Daily Automation - Sync & Process All",
            replace_existing=True
        )

        # self.scheduler.add_job(
        #     func=self.hourly_sync_job,
        #     trigger=CronTrigger(minute=0),  # Every hour
        #     id='hourly_sync',
        #     name='Hourly Transaction Sync',
        #     replace_existing=True
        # )

        #Anomaly scan twice daily
        self.scheduler.add_job(
            func=self.anomaly_scan_job,
            trigger=CronTrigger(hour='6,18', minute=0),  # 6 AM and 6 PM
            id='anomaly_scan',
            name='Anomaly Detection Scan',
            replace_existing=True
        )

        #Email monitoring
        self.scheduler.add_job(
            func=self.email_monitoring_job,
            trigger=CronTrigger(minute='*/5'),  # Every 5 minutes
            id='email_monitoring',
            name='Email Receipt Monitoring',
            replace_existing=True
        )

        #Monthly depreciation - last day of month at 11pm
        self.scheduler.add_job(
            func=self.monthly_depreciation_job,
            trigger=CronTrigger(day='last', hour=23, minute=0),
            id='monthly_depreciation',
            name='Monthly Asset Depreciation',
            replace_existing=True
        )

        # print("Scheduled jobs configured:")
        # print("Daily Automation: 2:00 AM")
        # print("Anomaly Scan: 6:00 AM, 6:00 PM")
        # print("Email Monitoring: Every 5 minutes")

    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self):
        """STop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()


    def daily_automation_job(self):
        """Complete automation pipeline
        Sync all bank account, classify transactions to generating financial statements"""
        db = SessionLocal()

        try:
            companies = db.query(Company).filter(
                Company.deleted_at.is_(None)
            )

            for company in companies:
                try:
                    self.process_company(db, company)
                except Exception as e:
                    print(f"Error processing {company.name}: {e}")
                    continue

        except Exception as e:
            print(f"Daily automation error: {e}")

        finally:
            db.close()


    def process_company(self, db: Session, company: Company):
        """"process a single company through the automation pipeline"""
        company_id = str(company.id)

        #Sync bank accounts
        plaid_results = PlaidService.sync_all_active_items(db, company_id)

        #Classifying transactions
        pending_txns = db.query(Transaction).filter(
            Transaction.company_id == company_id,
            Transaction.classification_status == "pending_review",
            Transaction.deleted_at.is_(None)
        ).all()

        classify_count = 0
        for txn in pending_txns:
            try:
                agent = ClassificationAgent(db, company_id)
                result = agent.classify_transaction(txn)

                if result["auto_approved"]:
                    classify_count += 1

            except Exception as e:
                print(f"Classification error for {txn.id}: {e}")
                continue

        #Generate journal entries
        # classified_txns = db.query(Transaction).filter(
        #     Transaction.company_id == company_id,
        #     Transaction.classification_status == 'auto_approved',
        #     Transaction.journal_entry_id.is_(None),
        #     Transaction.deleted_at.is_(None)
        # ).all()

        classified_txns = db.query(Transaction).outerjoin(
            JournalEntry,
            JournalEntry.transaction_id == Transaction.id
        ).filter(
            Transaction.company_id == company_id,
            Transaction.classification_status == 'auto_approved',
            JournalEntry.id.is_(None), #No journal entry exists
            Transaction.deleted_at.is_(None)
        ).all()

        journal_count = 0
        for txn in classified_txns:
            try:
                agent = JournalEntryAgent(db, company_id)
                entry = agent.generate_entry_for_transaction(txn)

                if entry:
                    journal_count += 1

            except Exception as e:
                print(f"Journal entry error for {txn.id}: {e}")
                continue

        #Auto reconciliation
        recon_service = ReconciliationService(db, company_id)
        recon_results = recon_service.auto_reconcile()

        #Tax analysis
        tax_service = TaxService(db, company_id)
        tax_results = tax_service.analyze_all_pending()
        print(f"Analyzed {tax_results['analyzed']} transactions for tax")

        #Anomaly detection
        anomaly_service = AnomalyService(db, company_id)
        anomaly_results = anomaly_service.scan_for_anomalies()

        if anomaly_results["anomalies_found"] > 0:
            print(f"{anomaly_results['critical']} critical issues detected")

        #Generate financial statements
        print(f"\nUPDATING {company.name} FINANCIAL STATEMENTS...")

    def hourly_sync_job(self):
        """Quick sync of bank transactions only (no processing), for real time updates"""
        db = SessionLocal()

        try:
            companies = db.query(Company).filter(
                Company.deleted_at.is_(None)
            ).all()

            for company in companies:
                try:
                    PlaidService.sync_all_active_items(db, str(company.id))
                except Exception as e:
                    print(f"Sync error for {company.name}: {e}")
                    continue
        finally:
            db.close()

    def anomaly_scan_job(self):
        """Scan for unusual transactions and patterns"""
        db = SessionLocal()

        try:
            companies = db.query(Company).filter(
                Company.deleted_at.is_(None)
            ).all()

            total_anomalies = 0
            critical_count = 0

            for company in companies:
                try:
                    anomaly_service = AnomalyService(db, str(company.id))
                    results = anomaly_service.scan_for_anomalies()

                    total_anomalies += results["anomalies_found"]
                    critical_count += results["critical"]

                    if results["critical"] > 0:
                        print(f"{company.name}: {results['critical']} critical anomalies")

                except Exception as e:
                    print(f"Anomaly scan error for {company.name}: {e}")
                    continue
        finally:
            db.close()

    def email_monitoring_job(self):
        """Check Gmail and forwarding inboxes for new receipts"""
        try:
            # Monitor Gmail connections
            GmailService.monitor_all_gmail_connections(db)

            # Monitor forwarding addresses
            IMAPService.monitor_all_forwarding_addresses(db)

        except Exception as e:
            print(f"Email monitoring error: {e}")

        finally:
            db.close()

    def monthly_depreciation_job(self):
        """Records depreciation for all assets on last day of month."""
        db = SessionLocal()

        try:
            today = date.today()

            companies = db.query(Company).filter(
                Company.deleted_at.is_(None)
            ).all()

            print(f"Processing depreciation for {len(companies)} companies")

            for company in companies:
                try:
                    service = DepreciationService(db, str(company.id))
                    result = service.record_monthly_depreciation(
                        today.month,
                        today.year
                    )

                    print(f"{company.name}: ${result['total_depreciation']:.2f}")

                except Exception as e:
                    print(f"{company.name}: {e}")
                    continue

        except Exception as e:
            print(f"Monthly depreciation error: {e}")

        finally:
            db.close()


scheduler = SchedulerService()