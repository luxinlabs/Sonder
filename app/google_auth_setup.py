"""One-time interactive Google Calendar OAuth grant.

Run this yourself, in your own terminal, from sonder/:

    source venv/bin/activate
    python3 app/google_auth_setup.py

It opens your browser for consent, then caches a refresh token at
credentials/token.json so the agent never has to do this again.
"""

import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRET_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRET_FILE", "credentials/client_secret.json"
)
TOKEN_FILE = os.path.join(os.path.dirname(CLIENT_SECRET_FILE), "token.json")


def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"Saved credentials to {TOKEN_FILE}")


if __name__ == "__main__":
    main()
