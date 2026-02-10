"""Google API Authentication (Simplified).

Handles credential management using direct OAuth2 credentials:
  - Client ID
  - Client Secret
  - Refresh Token
"""

import os
from loguru import logger

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def get_direct_credentials(scopes: list[str]):
    """Load credentials directly from environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        logger.warning(
            "Missing Google OAuth2 credentials. Please set GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN in your .env file."
        )
        return None

    try:
        creds = Credentials(
            None,  # No access token, we will refresh it
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

        # Refresh the credentials to get a valid access token
        creds.refresh(Request())
        logger.info("Successfully authenticated with direct OAuth2 credentials")
        return creds
    except Exception as e:
        logger.error(f"Failed to authenticate with direct credentials: {e}")
        return None


def get_google_service(service_name: str, version: str, scopes: list[str], **kwargs):
    """Build an authenticated Google API service client."""
    creds = get_direct_credentials(scopes)

    if not creds:
        return None

    try:
        service = build(service_name, version, credentials=creds)
        logger.info(f"Built Google {service_name} {version} service")
        return service
    except Exception as e:
        logger.error(f"Failed to build {service_name} service: {e}")
        return None
