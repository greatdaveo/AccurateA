from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import Anomaly, Transaction
from app.agents.anomaly_detection_agent import AnomalyDetectionAgent

class AnomalyService:
    """Orchestrates anomaly detection and management"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def scan_for_anomalies(self) -> Dict[str, Any]:
        """Run anomaly detection scan"""
        agent = AnomalyDetectionAgent(self.db, self.company_id)
        results = agent.scan_all_transactions()

        return {
            "anomalies_found": results["anomalies_found"],
            "scanned": results["scanned"],
            "critical": results["by_severity"]["critical"],
            "high": results["by_severity"]["high"],
            "medium": results["by_severity"]["medium"],
            "low": results["by_severity"]["low"],
            "by_type": results.get("by_type", {}),
            "by_severity": results["by_severity"]  # Keep original structure too
        }

    def get_pending_anomalies(
        self,
        severity: str = None
    ) -> List[Dict[str, Any]]:
        """Get pending anomalies"""
        anomalies = Anomaly.get_pending(self.db, self.company_id, severity)

        return [
            {
                "id": str(a.id),
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "risk_score": float(a.risk_score),
                "title": a.title,
                "description": a.description,
                "transaction_id": str(a.transaction_id) if a.transaction_id else None,
                "detected_at": str(a.detected_at),
                "evidence": a.evidence
            }
            for a in anomalies
        ]

    def get_anomaly_summary(self) -> Dict[str, Any]:
        """Get summary of anomalies"""

        # Count by status
        total = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.deleted_at.is_(None)
        ).count()

        pending = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.status == "pending",
            Anomaly.deleted_at.is_(None)
        ).count()

        resolved = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.status == "resolved",
            Anomaly.deleted_at.is_(None)
        ).count()

        false_positives = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.status == "false_positive",
            Anomaly.deleted_at.is_(None)
        ).count()

        # Count by severity
        critical = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.severity == "critical",
            Anomaly.status == "pending",
            Anomaly.deleted_at.is_(None)
        ).count()

        high = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.severity == "high",
            Anomaly.status == "pending",
            Anomaly.deleted_at.is_(None)
        ).count()

        medium = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.severity == "medium",
            Anomaly.status == "pending",
            Anomaly.deleted_at.is_(None)
        ).count()

        low = self.db.query(Anomaly).filter(
            Anomaly.company_id == self.company_id,
            Anomaly.severity == "low",
            Anomaly.status == "pending",
            Anomaly.deleted_at.is_(None)
        ).count()

        return {
            "total": total,
            "pending": pending,
            "resolved": resolved,
            "false_positives": false_positives,
            "by_severity": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low
            }
        }

    def resolve_anomaly(
        self,
        anomaly_id: str,
        user_id: str,
        resolution_notes: str,
        is_false_positive: bool = False
    ) -> Dict[str, Any]:
        """Resolve an anomaly"""

        anomaly = self.db.query(Anomaly).filter(
            Anomaly.id == anomaly_id,
            Anomaly.company_id == self.company_id
        ).first()

        if not anomaly:
            raise ValueError("Anomaly not found")

        anomaly.mark_reviewed(
            self.db,
            user_id=user_id,
            resolution_notes=resolution_notes,
            is_false_positive=is_false_positive
        )

        return {
            "id": str(anomaly.id),
            "status": anomaly.status,
            "resolved_at": str(anomaly.reviewed_at),
            "message": "Anomaly resolved"
        }
