"""
Orchestrates AI year-end adjustments.

Flow:
  1. suggest_adjustments() -> AI agent generates suggestions -> creates draft JEs
  2. get_pending() -> returns all draft adjustment entries
  3. approve(id) -> posts a draft entry
  4. reject(id) -> soft-deletes a draft entry
  5. approve_all() -> bulk-posts all pending entries
"""

from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session

from app.models import JournalEntry, JournalEntryLine
from app.agents.adjustment_agent import AdjustmentAgent


class AdjustmentService:
    """Handles the suggest -> review -> approve flow for adjustments."""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self.agent = AdjustmentAgent(db, company_id)

    def suggest_adjustments(
        self, period_start: date, period_end: date
    ) -> Dict[str, Any]:
        """
        Run AI checks, create draft journal entries for each suggestion,
        and return the suggestions with their entry IDs.
        """
        # Clean up any existing unapproved adjustment drafts for this period
        # to avoid duplicates on re-run
        existing_drafts = self.db.query(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "draft",
            JournalEntry.entry_date >= period_start,
            JournalEntry.entry_date <= period_end,
            JournalEntry.deleted_at.is_(None),
        ).all()

        for draft in existing_drafts:
            draft.delete(self.db, soft=True)

        # Get suggestions from the AI agent
        raw_suggestions = self.agent.suggest_all(period_start, period_end)

        # Create a draft journal entry for each suggestion
        results = []
        for suggestion in raw_suggestions:
            try:
                entry = JournalEntry.create_entry(
                    self.db,
                    company_id=self.company_id,
                    entry_date=date.fromisoformat(suggestion["entry_date"]),
                    description=suggestion["description"],
                    lines=self._map_lines(suggestion["journal_lines"]),
                    source="adjustment",
                    reference=suggestion.get("reference"),
                )

                results.append({
                    "id": str(entry.id),
                    "entry_number": entry.entry_number,
                    "type": suggestion["type"],
                    "description": suggestion["description"],
                    "reason": suggestion["reason"],
                    "confidence": suggestion["confidence"],
                    "entry_date": suggestion["entry_date"],
                    "lines": self._format_entry_lines(entry),
                    "status": "pending",
                })
            except Exception as e:
                print(f"[AdjustmentService] Failed to create entry: {e}")
                continue

        return {
            "period_start": str(period_start),
            "period_end": str(period_end),
            "count": len(results),
            "suggestions": results,
        }

    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending (draft) adjustment entries."""
        entries = self.db.query(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "draft",
            JournalEntry.deleted_at.is_(None),
        ).order_by(JournalEntry.entry_date).all()

        return [
            {
                "id": str(e.id),
                "entry_number": e.entry_number,
                "description": e.description,
                "entry_date": str(e.entry_date),
                "reference": e.reference,
                "lines": self._format_entry_lines(e),
                "status": "pending",
            }
            for e in entries
        ]

    def approve(self, entry_id: str) -> Dict[str, Any]:
        """Approve (post) a single adjustment entry."""
        entry = self.db.query(JournalEntry).filter(
            JournalEntry.id == entry_id,
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "draft",
            JournalEntry.deleted_at.is_(None),
        ).first()

        if not entry:
            raise ValueError("Adjustment entry not found or already processed")

        entry.post(self.db, posted_by_id=None)

        return {
            "id": str(entry.id),
            "entry_number": entry.entry_number,
            "status": "posted",
            "message": f"Adjustment {entry.entry_number} approved and posted",
        }

    def reject(self, entry_id: str) -> Dict[str, Any]:
        """Reject (soft-delete) a single adjustment entry."""
        entry = self.db.query(JournalEntry).filter(
            JournalEntry.id == entry_id,
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "draft",
            JournalEntry.deleted_at.is_(None),
        ).first()

        if not entry:
            raise ValueError("Adjustment entry not found or already processed")

        entry.delete(self.db, soft=True)

        return {
            "id": str(entry.id),
            "entry_number": entry.entry_number,
            "status": "rejected",
            "message": f"Adjustment {entry.entry_number} rejected",
        }

    def approve_all(self) -> Dict[str, Any]:
        """Bulk-approve all pending adjustment entries."""
        entries = self.db.query(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "draft",
            JournalEntry.deleted_at.is_(None),
        ).all()

        approved = []
        for entry in entries:
            try:
                entry.post(self.db, posted_by_id=None)
                approved.append(str(entry.id))
            except Exception as e:
                print(f"[AdjustmentService] Failed to post {entry.entry_number}: {e}")

        return {
            "approved_count": len(approved),
            "approved_ids": approved,
            "message": f"Approved {len(approved)} adjustment(s)",
        }

    # Helpers
    def _map_lines(self, suggestion_lines: list) -> list:
        """Map suggestion line format to JournalEntry.create_entry format."""
        return [
            {
                "account_id": line["account_id"],
                "debit": line.get("debit", 0),
                "credit": line.get("credit", 0),
                "description": line.get("description", ""),
            }
            for line in suggestion_lines
        ]

    def _format_entry_lines(self, entry: JournalEntry) -> list:
        """Format journal entry lines for API response."""
        lines = self.db.query(JournalEntryLine).filter(
            JournalEntryLine.journal_entry_id == entry.id,
        ).all()

        return [
            {
                "account_id": str(line.account_id),
                "account_code": line.account.account_code if line.account else "",
                "account_name": line.account.account_name if line.account else "",
                "debit": float(line.debit or 0),
                "credit": float(line.credit or 0),
                "description": line.description or "",
            }
            for line in lines
        ]
