"""
One-time Outlook OAuth2 setup script for Quartermaster.

Uses MSAL device code flow — works on headless servers.

Pre-requisites:
  1. Register an app in Entra ID (https://entra.microsoft.com)
  2. Set as Public client with redirect URI http://localhost
  3. Add API permissions: Mail.ReadWrite, User.Read, offline_access
  4. Enable "Allow public client flows"
  5. Note the Application (client) ID and Directory (tenant) ID

Usage:
  python scripts/outlook_oauth_setup.py \\
    --client-id <app-client-id> \\
    --tenant-id <tenant-id> \\
    --account-name fr-brian
"""

import argparse
import json
import sys
from pathlib import Path

from msal import PublicClientApplication, SerializableTokenCache

SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    # offline_access is reserved — MSAL adds it automatically
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Outlook OAuth2 setup for Quartermaster (device code flow)"
    )
    parser.add_argument("--client-id", required=True, help="Entra app client ID")
    parser.add_argument("--tenant-id", required=True, help="Entra directory tenant ID")
    parser.add_argument("--account-name", required=True, help="Account name (e.g. 'fr-brian')")
    args = parser.parse_args()

    cache = SerializableTokenCache()
    authority = f"https://login.microsoftonline.com/{args.tenant_id}"
    app = PublicClientApplication(
        client_id=args.client_id,
        authority=authority,
        token_cache=cache,
    )

    # Initiate device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print(f"Error initiating device flow: {flow.get('error_description', 'unknown')}")
        sys.exit(1)

    print(f"\nTo sign in, open: {flow['verification_uri']}")
    print(f"Enter code: {flow['user_code']}")
    print("Waiting for authentication...\n")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        print(f"Authentication failed: {result.get('error_description', 'unknown')}")
        sys.exit(1)

    # Get email address from token claims or /me endpoint
    import httpx  # noqa: PLC0415
    resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {result['access_token']}"},
    )
    email_address = ""
    if resp.status_code == 200:
        user_data = resp.json()
        email_address = user_data.get("mail") or user_data.get("userPrincipalName", "")

    # Save credentials
    project_root = Path(__file__).parent.parent
    output_path = project_root / f"credentials/outlook_{args.account_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cred_data = {
        "client_id": args.client_id,
        "tenant_id": args.tenant_id,
        "email_address": email_address,
        "token_cache": cache.serialize(),
    }
    output_path.write_text(json.dumps(cred_data, indent=2))

    print("--- Outlook OAuth2 Setup Complete ---")
    print(f"Account: {args.account_name}")
    print(f"Email: {email_address}")
    print(f"Credentials saved to: {output_path}")
    print("\nAdd this to your config/settings.yaml:")
    print(f"  {args.account_name}:")
    print("    provider: outlook")
    print(f'    credential_file: "{output_path}"')
    print('    label: "Your Label Here"')


if __name__ == "__main__":
    main()
