"""
HMRC Making Tax Digital (MTD) Service

Handles:
- OAuth 2.0 authorization flow with HMRC
- Fetching VAT obligations (filing deadlines)
- Submitting VAT returns electronically
- Checking return status
- Token refresh
"""

import os
import json
import uuid
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models.vat import VATReturn, VATScheme

# ============================================================
# CONFIGURATION
# ============================================================
HMRC_ENV = os.getenv("HMRC_ENVIRONMENT", "sandbox")

HMRC_BASE_URLS = {
    "sandbox": "https://test-api.service.hmrc.gov.uk",
    "production": "https://api.service.hmrc.gov.uk",
}

HMRC_AUTH_URLS = {
    "sandbox": "https://test-api.service.hmrc.gov.uk/oauth/authorize",
    "production": "https://api.service.hmrc.gov.uk/oauth/authorize",
}

HMRC_TOKEN_URLS = {
    "sandbox": "https://test-api.service.hmrc.gov.uk/oauth/token",
    "production": "https://api.service.hmrc.gov.uk/oauth/token",
}

BASE_URL = HMRC_BASE_URLS.get(HMRC_ENV, HMRC_BASE_URLS["sandbox"])
AUTH_URL = HMRC_AUTH_URLS.get(HMRC_ENV, HMRC_AUTH_URLS["sandbox"])
TOKEN_URL = HMRC_TOKEN_URLS.get(HMRC_ENV, HMRC_TOKEN_URLS["sandbox"])

CLIENT_ID = os.getenv("HMRC_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("HMRC_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("HMRC_REDIRECT_URI", "http://localhost:8000/api/hmrc/callback")

# ============================================================
# TOKEN STORAGE (in-memory for now — move to DB for production)
# ============================================================

# In production, store tokens per company in the database
_token_store: Dict[str, Dict] = {}


def _store_token(company_id: str, token_data: Dict):
    """Store OAuth token for a company."""
    _token_store[company_id] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 14400)),
        "scope": token_data.get("scope", ""),
    }


def _get_token(company_id: str) -> Optional[Dict]:
    """Retrieve stored token for a company."""
    return _token_store.get(company_id)


# ============================================================
# FRAUD PREVENTION HEADERS
# ============================================================
def _get_fraud_prevention_headers(
        user_ip: str = "0.0.0.0",
        user_agent: str = "AccurateA/1.0",
) -> Dict[str, str]:
    """
    Generate HMRC fraud prevention headers.

    HMRC requires these on EVERY API call in production.
    Missing headers = rejected request.
    """
    return {
        "Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER",
        "Gov-Client-User-IDs": f"AccurateA={uuid.uuid4()}",
        "Gov-Client-Timezone": "UTC+00:00",
        "Gov-Client-Local-IPs": user_ip,
        "Gov-Client-User-Agent": user_agent,
        "Gov-Vendor-Version": "AccurateA=1.0.0",
        "Gov-Vendor-Product-Name": "AccurateA",
    }


# ============================================================
# HMRC MTD SERVICE CLASS
# ============================================================
class HMRCMTDService:
    """Service for interacting with HMRC's Making Tax Digital API."""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self.scheme = VATScheme.get_active_scheme(db, company_id)


    # OAUTH 2.0 FLOW
    @staticmethod
    def get_authorization_url(state: str) -> str:
        """
        Generate the HMRC OAuth authorization URL.

        Redirect the user's browser to this URL. They'll log into their
        HMRC Government Gateway account and grant permission.

        Args:
            state: A random string to prevent CSRF — store in session and verify on callback

        Returns:
            URL to redirect the user to
        """
        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "scope": "read:vat write:vat",
            "state": state,
            "redirect_uri": REDIRECT_URI,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{AUTH_URL}?{query}"

    @staticmethod
    def exchange_code_for_token(authorization_code: str) -> Dict[str, Any]:
        """
        Exchange the authorization code for access + refresh tokens.

        Called after the user returns from HMRC's login page with a ?code= parameter.
        """
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise Exception(
                f"HMRC token exchange failed: {response.status_code} — {response.text}"
            )

        return response.json()

    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh an expired access token using the refresh token.

        HMRC access tokens expire after 4 hours. Refresh tokens last 18 months.
        """
        token = _get_token(self.company_id)
        if not token or not token.get("refresh_token"):
            raise Exception("No refresh token available. User must re-authorize with HMRC.")

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise Exception(
                f"HMRC token refresh failed: {response.status_code} — {response.text}"
            )

        token_data = response.json()
        _store_token(self.company_id, token_data)
        return token_data

    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        token = _get_token(self.company_id)
        if not token:
            raise Exception(
                "Not connected to HMRC. The company must authorize via OAuth first."
            )

        # Check expiry
        if token["expires_at"] <= datetime.utcnow():
            self.refresh_access_token()
            token = _get_token(self.company_id)

        return token["access_token"]

    def _make_request(
            self,
            method: str,
            path: str,
            data: Optional[Dict] = None,
            params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the HMRC API."""
        access_token = self._get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.hmrc.1.0+json",
            "Content-Type": "application/json",
            **_get_fraud_prevention_headers(),
        }

        url = f"{BASE_URL}{path}"

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data,
            params=params,
        )

        if response.status_code >= 400:
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = json.dumps(error_json, indent=2)
            except Exception:
                pass

            raise Exception(
                f"HMRC API error {response.status_code}: {error_detail}"
            )

        # Some responses are 204 No Content
        if response.status_code == 204:
            return {"status": "success"}

        return response.json()

    # VAT OBLIGATIONS
    def get_obligations(
            self,
            from_date: str,
            to_date: str,
            status: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get VAT filing obligations from HMRC.

        Returns the periods you need to file for, with their due dates
        and whether they've been fulfilled.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            status: "O" (open/outstanding) or "F" (fulfilled/filed)

        Returns:
            List of obligation objects from HMRC
        """
        if not self.scheme or not self.scheme.vat_registration_number:
            raise Exception("Company has no VAT registration number set.")

        vrn = self.scheme.vat_registration_number.replace(" ", "")

        params = {
            "from": from_date,
            "to": to_date,
        }
        if status:
            params["status"] = status

        result = self._make_request(
            "GET",
            f"/organisations/vat/{vrn}/obligations",
            params=params,
        )

        return result.get("obligations", [])


    # SUBMIT VAT RETURN
    def submit_return(
            self,
            vat_return: VATReturn,
            finalised: bool = False,
    ) -> Dict[str, Any]:
        """
        Submit a VAT return to HMRC via MTD.

        CRITICAL: Once submitted, it CANNOT be undone. HMRC treats this
        as a legal declaration. The `finalised` flag must be True.

        The 9-box data is sent exactly as HMRC expects it.
        Boxes 1-5 and 9 are in pounds and pence (2dp).
        Boxes 6-8 are whole pounds only (rounded down).

        Args:
            vat_return: The VATReturn model instance
            finalised: Must be True to actually submit

        Returns:
            HMRC's response with processing date and receipt
        """
        if not finalised:
            raise ValueError(
                "You must set finalised=True to submit to HMRC. "
                "This is a legal declaration and cannot be reversed."
            )

        if not self.scheme or not self.scheme.vat_registration_number:
            raise Exception("Company has no VAT registration number set.")

        vrn = self.scheme.vat_registration_number.replace(" ", "")

        # HMRC expects specific field names and types
        # Boxes 6, 7, 8 are whole pounds (no decimals)
        payload = {
            "periodKey": self._get_period_key(vat_return),
            "vatDueSales": float(vat_return.box1_vat_due_sales or 0),
            "vatDueAcquisitions": float(vat_return.box2_vat_due_acquisitions or 0),
            "totalVatDue": float(vat_return.box3_total_vat_due or 0),
            "vatReclaimedCurrPeriod": float(vat_return.box4_vat_reclaimed or 0),
            "netVatDue": abs(float(vat_return.box5_net_vat or 0)),  # HMRC wants absolute value
            "totalValueSalesExVAT": int(vat_return.box6_total_sales_excl_vat or 0),
            "totalValuePurchasesExVAT": int(vat_return.box7_total_purchases_excl_vat or 0),
            "totalValueGoodsSuppliedExVAT": int(vat_return.box8_total_supplies_eu or 0),
            "totalAcquisitionsExVAT": int(vat_return.box9_total_acquisitions_eu or 0),
            "finalised": True,
        }

        result = self._make_request(
            "POST",
            f"/organisations/vat/{vrn}/returns",
            data=payload,
        )

        # Update the VATReturn record with HMRC's response
        vat_return.status = "submitted"
        vat_return.submitted_at = datetime.utcnow()
        vat_return.hmrc_receipt_id = result.get("formBundleNumber", "")
        vat_return.hmrc_processing_date = (
            datetime.fromisoformat(result["processingDate"].replace("Z", "+00:00"))
            if result.get("processingDate")
            else None
        )
        vat_return.update(self.db)

        return {
            "success": True,
            "receipt_id": result.get("formBundleNumber"),
            "processing_date": result.get("processingDate"),
            "charge_ref_number": result.get("chargeRefNumber"),
            "payment_indicator": result.get("paymentIndicator"),
        }


    # VIEW SUBMITTED RETURN
    def get_submitted_return(self, period_key: str) -> Dict[str, Any]:
        """
        Retrieve a previously submitted VAT return from HMRC.

        Useful for confirming what HMRC holds on record.

        Args:
            period_key: The HMRC period key (e.g., "#001")
        """
        if not self.scheme or not self.scheme.vat_registration_number:
            raise Exception("Company has no VAT registration number set.")

        vrn = self.scheme.vat_registration_number.replace(" ", "")

        return self._make_request(
            "GET",
            f"/organisations/vat/{vrn}/returns/{period_key}",
        )


    # VIEW LIABILITIES AND PAYMENTS
    def get_liabilities(
            self,
            from_date: str,
            to_date: str,
    ) -> List[Dict]:
        """Get outstanding VAT liabilities (what you owe HMRC)."""
        vrn = self.scheme.vat_registration_number.replace(" ", "")

        result = self._make_request(
            "GET",
            f"/organisations/vat/{vrn}/liabilities",
            params={"from": from_date, "to": to_date},
        )
        return result.get("liabilities", [])

    def get_payments(
            self,
            from_date: str,
            to_date: str,
    ) -> List[Dict]:
        """Get VAT payments made to HMRC."""
        vrn = self.scheme.vat_registration_number.replace(" ", "")

        result = self._make_request(
            "GET",
            f"/organisations/vat/{vrn}/payments",
            params={"from": from_date, "to": to_date},
        )
        return result.get("payments", [])


    # HELPERS
    def _get_period_key(self, vat_return: VATReturn) -> str:
        """
        Derive the HMRC period key from the return dates.

        HMRC uses period keys like "#001", "#002", "#003", "#004" for
        quarterly returns within a year. In the sandbox, you may need
        specific test period keys.

        For production, you should get the period key from the obligations
        endpoint and store it with the return.
        """
        # Map quarter to period key
        quarter = (vat_return.period_start.month - 1) // 3 + 1
        year_suffix = str(vat_return.period_start.year)[-2:]
        return f"{year_suffix}A{quarter}"

    def is_connected(self) -> bool:
        """Check if the company has a valid HMRC connection."""
        token = _get_token(self.company_id)
        return token is not None
