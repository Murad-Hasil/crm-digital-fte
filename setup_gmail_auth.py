"""
One-time Gmail OAuth2 setup script.

Steps:
  1. Download OAuth2 Desktop credentials from Google Cloud Console
  2. Save as: credentials/client_secret.json
  3. Run: python setup_gmail_auth.py
  4. Browser opens → login → allow access
  5. Token saved to: credentials/gmail_credentials.json

After this, the app uses gmail_credentials.json automatically.
"""

import json
import os

SCOPES = ["https://mail.google.com/"]
CLIENT_SECRET_FILE = "credentials/client_secret.json"
TOKEN_FILE = "credentials/gmail_credentials.json"


def main():
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"ERROR: {CLIENT_SECRET_FILE} not found!")
        print()
        print("Steps to get it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. APIs & Services → Credentials")
        print("  3. Create Credentials → OAuth 2.0 Client ID → Desktop App")
        print("  4. Download JSON → rename to client_secret.json")
        print(f"  5. Place it at: {CLIENT_SECRET_FILE}")
        return

    from google_auth_oauthlib.flow import InstalledAppFlow

    print("Starting OAuth2 flow — browser will open...")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token in authorized_user format (what gmail_handler.py expects)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    os.makedirs("credentials", exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nSuccess! Token saved to: {TOKEN_FILE}")
    print("You can now start the app.")


if __name__ == "__main__":
    main()
