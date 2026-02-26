"""
prusa_bridge.py — Prusa Connect API client for the Prusa XL (5-toolhead).

Credentials are loaded from secrets.py (which reads from .env).
Constructor args are kept for backwards compatibility and testing overrides.
"""

from typing import Optional
import requests
import config as cfg


class PrusaXLBridge:
    def __init__(
        self,
        api_key:    Optional[str] = None,
        printer_id: Optional[str] = None,
        server_url: Optional[str] = None,
    ):
        """
        Initialise the bridge. All args default to values from secrets.py / .env.

        Args:
            api_key:    Prusa Connect API key (overrides .env value if provided).
            printer_id: Printer UUID from Prusa Connect (overrides .env if provided).
            server_url: Base Prusa Connect URL (default: https://connect.prusa3d.com).
        """
        self.api_key    = api_key    or cfg.prusa_api_key()
        self.printer_id = printer_id or cfg.prusa_printer_id()
        self.base_url   = (server_url or cfg.prusa_server_url()).rstrip("/") + "/api/v1"
        self.headers    = {"X-Api-Key": self.api_key}

    # ── Public API ────────────────────────────────────────────────────────────

    def upload_and_print(self, file_path: str) -> bool:
        """
        Upload a .bgcode file to the printer and start the print job.

        Returns:
            True if the upload was accepted (HTTP 201), False otherwise.
        """
        endpoint = f"{self.base_url}/printers/{self.printer_id}/files"
        with open(file_path, "rb") as f:
            response = requests.post(endpoint, headers=self.headers, files={"file": f})
        return response.status_code == 201

    def get_status(self) -> dict:
        """Fetch current printer status from Prusa Connect."""
        endpoint = f"{self.base_url}/printers/{self.printer_id}"
        return requests.get(endpoint, headers=self.headers).json()

    def emergency_stop(self) -> requests.Response:
        """Send an immediate cancel/e-stop command to the printer."""
        endpoint = f"{self.base_url}/printers/{self.printer_id}/commands"
        return requests.post(endpoint, headers=self.headers, json={"command": "CANCEL_PRINT"})