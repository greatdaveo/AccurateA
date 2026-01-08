from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Company, Transaction
from app.services.scheduler_service import scheduler
from app.services.plaid_service import PlaidService
from app.agents.classification_agent import ClassificationAgent
from app.services.reconciliation_service import ReconciliationService
from app.services.anomaly_service import AnomalyService
from app.services.tax_service import TaxService

router = APIRouter(
    prefix="/automation",
    tags=["Automation"]
)

@router.post(
    "/run-daily",
    summary="Run daily automation",
    description="Manually trigger the daily automation job for current company"
)
async def run_daily_automation(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run daily automation manually, useful for testing or on demand processing"""
    company = db.query(Company).filter(
        Company.id == current_user.company_id
    ).first()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    # Run in background
    background_tasks.add_task(
        scheduler.process_company,
        db,
        company
    )

    return {
        'success': True,
        'message': f'Daily automation started for {company.name}',
        'note': 'Processing in background - check logs for progress'
    }

@router.post(
    "/sync-banks",
    summary="Sync all banks",
    description="Sync transactions from all connected banks"
)
async def sync_banks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync all banks"""
    try:
        results = PlaidService.sync_all_active_items(
            db,
            str(current_user.company_id)
        )

        return {
            'success': True,
            'synced': results['synced'],
            'imported': results['total_imported'],
            'reconciled': results['total_reconciled']
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/classify-pending",
    summary="Classify pending transactions",
    description="Run AI classification on all pending transactions"
)
async def classify_pending(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Classify all pending transactions"""
    try:
        pending = db.query(Transaction).filter(
            Transaction.company_id == current_user.company_id,
            Transaction.classification_status == 'pending_review',
            Transaction.deleted_at.is_(None)
        ).all()

        classified = 0
        agent = ClassificationAgent(db, str(current_user.company_id))

        for txn in pending:
            try:
                result = agent.classify_transaction(txn)
                if result['auto_approved']:
                    classified += 1
            except Exception as e:
                print(f"Classification error: {e}")
                continue

        return {
            'success': True,
            'total': len(pending),
            'classified': classified,
            'message': f'Classified {classified}/{len(pending)} transactions'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/reconcile",
    summary="Auto-reconcile",
    description="Match bank transactions to internal transactions"
)
async def auto_reconcile(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Run auto-reconciliation"""
    try:
        service = ReconciliationService(db, str(current_user.company_id))
        results = service.auto_reconcile()

        return {
            'success': True,
            'matched': results['matched'],
            'message': f"Reconciled {results['matched']} transactions"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/scan-anomalies",
    summary="Scan for anomalies",
    description="Run anomaly detection on all transactions"
)
async def scan_anomalies(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Scan for anomalies"""
    try:
        service = AnomalyService(db, str(current_user.company_id))
        results = service.scan_for_anomalies()

        return {
            'success': True,
            'anomalies_found': results['anomalies_found'],
            'low': results['low'],
            'medium': results['medium'],
            'high': results['high'],
            'critical': results['critical'],
            'message': f"Found {results['anomalies_found']} anomalies"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/scheduler-status",
    summary="Get scheduler status",
    description="Check if background jobs are running"
)
async def scheduler_status():
    """Get scheduler status"""
    jobs = scheduler.scheduler.get_jobs()

    return {
        'running': scheduler.scheduler.running,
        'jobs': [
            {
                'id': job.id,
                'name': job.name,
                # 'next_run': str(getattr(job, 'next_run_time', None) or getattr(job, 'next_run', None) or 'N/A')
            }
            for job in jobs
        ]
    }