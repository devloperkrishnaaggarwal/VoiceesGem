import os
import json
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

# Load existing environment variables
load_dotenv()

# The scopes required for the voice agent
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

def main():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    flow = None

    # Try credentials.json first
    if os.path.exists("credentials.json"):
        print("--- Using credentials.json ---")
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", 
            scopes=SCOPES
        )
    # Then try .env variables
    elif client_id and client_secret:
        print("--- Using credentials from .env ---")
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost"]
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=SCOPES
        )
    else:
        print("Error: No credentials found.")
        print("Please either:")
        print("1. Download 'credentials.json' from Google Cloud Console.")
        print("2. OR Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file.")
        return

    # Run the local server flow
    # This will open a browser window for authentication
    print("Opening browser for authentication...")
    creds = flow.run_local_server(port=0)

    print("\n" + "="*50)
    print("SUCCESS! AUTHENTICATED SUCCESSFULLY")
    print("="*50)
    print(f"REFRESH TOKEN: {creds.refresh_token}")
    print("="*50)
    print("\nUpdate your .env file with:")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("="*50)

if __name__ == "__main__":
    main()
