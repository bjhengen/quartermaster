"""
One-time Gmail OAuth2 setup script for Quartermaster.

Usage:
  1. Create a Google Cloud project at https://console.cloud.google.com
  2. Enable the Gmail API
  3. Create OAuth2 credentials (Desktop application type)
  4. Download credentials JSON
  5. Run: python scripts/gmail_oauth_setup.py --credentials <path> --account-name <name>
  6. Complete the browser auth flow
  7. Credential file written to credentials/gmail_<account_name>.json

Scope: gmail.modify (read, compose, send, draft — everything except permanent deletion)
"""

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gmail OAuth2 setup for Quartermaster"
    )
    parser.add_argument(
        "--credentials",
        required=True,
        help="Path to Google OAuth client credentials JSON",
    )
    parser.add_argument(
        "--account-name",
        required=True,
        help="Account name (e.g., 'personal', 'friendly-robots')",
    )
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
    creds = flow.run_local_server(port=0)

    project_root = Path(__file__).parent.parent
    output_path = project_root / f"credentials/gmail_{args.account_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cred_data = json.loads(creds.to_json())
    output_path.write_text(json.dumps(cred_data, indent=2))

    print(f"\n--- Gmail OAuth2 Setup Complete ---")
    print(f"Account: {args.account_name}")
    print(f"Credentials saved to: {output_path}")
    print(f"\nAdd this to your config/settings.yaml:")
    print(f"  {args.account_name}:")
    print(f'    provider: gmail')
    print(f'    credential_file: "{output_path}"')
    print(f'    label: "Your Label Here"')


if __name__ == "__main__":
    main()
