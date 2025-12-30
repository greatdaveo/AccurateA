import json
from typing import Dict, Any, List, Optional
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Anomaly, Company


class AnomalyDetectionAgent(BaseAgent):
    """Analyze transactions and patterns to detect
    Duplicate transactions, Unusual amounts, frequency anomalies, New vendors, compliance issues"""

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="AnomalyDetectionAgent")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)

        self.DUPLICATE_WINDOW_DAYS = 7  # Check for duplicates within 7 days
        self.UNUSUAL_AMOUNT_STD_DEV = 3  # 3 standard deviations
        self.HIGH_RISK_THRESHOLD = 70
        self.MEDIUM_RISK_THRESHOLD = 40

    def scan_all_transactions(self) -> Dict[str, Any]:
        """Scan all transactions for anomalies"""
        self.log("Starting anomaly detection scan...")

        results = {
            "scanned": 0,
            "anomalies_found": 0,
            "by_type": {},
            "by_severity": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            }
        }

        # Get all unreviewed transactions
        transactions = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.deleted_at.is_(None)
        ).order_by(Transaction.transaction_date.desc()).limit(1000).all()

        results["scanned"] = len(transactions)

        for txn in transactions:
            anomalies = self._detect_transaction_anomalies(txn)

            for anomaly in anomalies:
                results["anomalies_found"] += 1

                #Count by type
                anom_type = anomaly["anomaly_type"]
                results["by_type"][anom_type] = results["by_type"].get(anom_type, 0) + 1

                # Count by severity
                severity = anomaly["severity"]
                results["by_severity"][severity] += 1

        self.log(f"Scan complete: Found {results['anomalies_found']} anomalies")

        return results

    def _detect_transaction_anomalies(
        self,
        transaction: Transaction
    ) -> List[Dict[str, Any]]:
        """Detect anomalies for a single transaction"""

        anomalies = []

        # Check for duplicates
        duplicate = self._check_duplicate(transaction)
        if duplicate:
            anomalies.append(duplicate)

        # Check for unusual amount
        unusual_amount = self._check_unusual_amount(transaction)
        if unusual_amount:
            anomalies.append(unusual_amount)

        # Check frequency
        frequency = self._check_frequency(transaction)
        if frequency:
            anomalies.append(frequency)

        # Check if new vendor
        new_vendor = self._check_new_vendor(transaction)
        if new_vendor:
            anomalies.append(new_vendor)

        # Check round number
        round_number = self._check_round_number(transaction)
        if round_number:
            anomalies.append(round_number)

        # Create anomaly records
        for anom_data in anomalies:
            self._create_anomaly_record(transaction, anom_data)

        return anomalies


    def _check_duplicate(
        self,
        transaction: Transaction
    ) -> Optional[Dict[str, Any]]:
        """Check for duplicate transactions"""
        #Look for similar transaction within window
        start_date = transaction.transaction_date - timedelta(days=self.DUPLICATE_WINDOW_DAYS)
        end_date = transaction.transaction_date + timedelta(days=self.DUPLICATE_WINDOW_DAYS)

        similar = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.id != transaction.id,
            Transaction.counterparty_name == transaction.counterparty_name,
            Transaction.amount == transaction.amount,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
            Transaction.deleted_at.is_(None)
        ).all()

        if similar:
            return {
                "anomaly_type": "duplicate",
                "severity": "high",
                "risk_score": 80.0,
                "title": "Possible duplicate transaction",
                "description": f"Found {len(similar)} similar transaction(s) within {self.DUPLICATE_WINDOW_DAYS} days: "
                               f"{transaction.counterparty_name} - ${transaction.amount}",
                "evidence": {
                    "similar_transactions": [str(t.id) for t in similar],
                    "count": len(similar)
                }
            }

        return None

    def _check_unusual_amount(
        self,
        transaction: Transaction
    ) -> Optional[Dict[str, Any]]:
        """Check if amount is unusually high/low"""

        #Get historical transactions for this vendor
        historical = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.counterparty_name == transaction.counterparty_name,
            Transaction.id != transaction.id,
            Transaction.deleted_at.is_(None)
        ).all()

        if len(historical) < 3:
            #Not enough data
            return None

        #Calculate statistics
        amounts = [float(t.amount) for t in historical]
        mean = sum(amounts) / len(amounts)
        variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
        std_dev = variance ** 0.5

        if std_dev == 0:
            return None

        #Calculate Z-score
        z_score = (float(transaction.amount) - mean) / std_dev

        if abs(z_score) >= self.UNUSUAL_AMOUNT_STD_DEV:
            severity = "high" if abs(z_score) >= 4 else "medium"
            risk_score = min(100, abs(z_score) * 20)

            return {
                "anomaly_type": "unusual_amount",
                "severity": severity,
                "risk_score": risk_score,
                "title": "Unusual transaction amount",
                "description": f"${transaction.amount} is {abs(z_score):.1f} standard deviations from average "
                               f"${mean:.2f} for {transaction.counterparty_name}",
                "evidence": {
                    "amount": float(transaction.amount),
                    "mean": mean,
                    "std_dev": std_dev,
                    "z_score": z_score,
                    "historical_count": len(historical)
                }
            }

        return None

    def _check_frequency(
        self,
        transaction: Transaction
    ) -> Optional[Dict[str, Any]]:
        """Check if vendor frequency is unusual"""

        #Count transactions in last 30 days
        thirty_days_ago = transaction.transaction_date - timedelta(days=30)

        recent_count = self.db.query(func.count(Transaction.id)).filter(
            Transaction.company_id == self.company_id,
            Transaction.counterparty_name == transaction.counterparty_name,
            Transaction.transaction_date >= thirty_days_ago,
            Transaction.deleted_at.is_(None)
        ).scalar()

        #Check historical average (90days ago to 30days ago
        ninety_days_ago = transaction.transaction_date - timedelta(days=90)

        historical_count = self.db.query(func.count(Transaction.id)).filter(
            Transaction.company_id == self.company_id,
            Transaction.counterparty_name == transaction.counterparty_name,
            Transaction.transaction_date >= ninety_days_ago,
            Transaction.transaction_date < thirty_days_ago,
            Transaction.deleted_at.is_(None)
        ).scalar()

        historical_avg = historical_count / 2 #60 days = 2 months

        if historical_avg > 0 and recent_count > historical_avg * 3:
            return {
                "anomaly_type": "frequency",
                "severity": "medium",
                "risk_score": 60.0,
                "title": "Unusual transaction frequency",
                "description": f"{recent_count} transactions with {transaction.counterparty_name} in last 30 days "
                               f"(average: {historical_avg:.1f})",
                "evidence": {
                    "recent_count": recent_count,
                    "historical_average": historical_avg,
                    "increase_factor": recent_count / historical_avg
                }
            }

        return None

    def _check_new_vendor(
        self,
        transaction: Transaction
    ) -> Optional[Dict[str, Any]]:
        """Check if this is a new vendor with large amount"""

        # Check if vendor exists historically
        historical = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.counterparty_name == transaction.counterparty_name,
            Transaction.id != transaction.id,
            Transaction.deleted_at.is_(None)
        ).count()

        if historical == 0 and float(transaction.amount) > 500:
            severity = "high" if float(transaction.amount) > 1000 else "medium"
            risk_score = min(100, float(transaction.amount) / 50)

            return {
                "anomaly_type": "new_vendor",
                "severity": severity,
                "risk_score": risk_score,
                "title": "New vendor with large amount",
                "description": f"First transaction with {transaction.counterparty_name}: ${transaction.amount}",
                "evidence": {
                    "vendor": transaction.counterparty_name,
                    "amount": float(transaction.amount),
                    "is_first": True
                }
            }

        return None

    def _check_round_number(
        self,
        transaction: Transaction
    ) -> Optional[Dict[str, Any]]:
        """Check if amount is suspiciously round"""

        amount = float(transaction.amount)

        # Check if it's a round number (100, 500, 1000 etc.)
        if amount >= 100 and amount % 100 == 0:
            return {
                "anomaly_type": "round_number",
                "severity": "low",
                "risk_score": 30.0,
                "title": "Round number amount",
                "description": f"${amount:.0f} is a perfectly round number (may indicate estimate)",
                "evidence": {
                    "amount": amount,
                    "is_round": True
                }
            }

        return None

    def _create_anomaly_record(
        self,
        transaction: Transaction,
        anomaly_data: Dict[str, Any]
    ):
        """Create anomaly record in database"""

        # Check if already exists
        existing = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.transaction_id == transaction.id,
            Anomaly.anomaly_type == anomaly_data['anomaly_type'],
            Anomaly.status == "pending"
        ).first()

        if existing:
            return  # Already flagged

        Anomaly.create_anomaly(
            self.db,
            company_id=self.company_id,
            transaction_id=str(transaction.id),
            **anomaly_data
        )

        self.log(f"{anomaly_data['severity'].upper()}: {anomaly_data['title']}")









