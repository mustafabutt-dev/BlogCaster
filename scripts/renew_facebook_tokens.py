"""
Facebook Token Renewal Script

Refreshes long-lived Facebook Page Access Tokens before they expire.

Flow per brand (aspose-cloud, groupdocs):
  1. Exchange the stored user access token for a fresh long-lived one
     (~60 day validity) via the fb_exchange_token grant.
  2. Use that long-lived user token to re-derive the Page Access Token
     for the brand's page.
  3. Emit the two refreshed values as GitHub Actions outputs (masked in
     logs) so a workflow step can push them to repo secrets via `gh secret set`.

Run standalone (no GITHUB_OUTPUT set) to dry-run against local .env and
print expiry info without touching any secrets.
"""

import asyncio
import os
import sys

import httpx

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
HTTP_TIMEOUT = 30.0

BRANDS = [
    {
        "label": "aspose",
        "app_id_env": "FACEBOOK_APP_ID",
        "app_secret_env": "FACEBOOK_APP_SECRET",
        "user_token_env": "FACEBOOK_USER_ACCESS_TOKEN",
        "page_id_env": "FACEBOOK_PAGE_ID",
    },
    {
        "label": "groupdocs",
        "app_id_env": "FACEBOOK_GROUPDOCS_APP_ID",
        "app_secret_env": "FACEBOOK_GROUPDOCS_APP_SECRET",
        "user_token_env": "FACEBOOK_GROUPDOCS_USER_ACCESS_TOKEN",
        "page_id_env": "FACEBOOK_GROUPDOCS_PAGE_ID",
    },
]


def mask(value: str) -> None:
    """Tell the GitHub Actions runner to redact this value from logs."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{value}")


async def exchange_long_lived_user_token(
    client: httpx.AsyncClient, app_id: str, app_secret: str, current_token: str
) -> str:
    response = await client.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": current_token,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def get_page_access_token(client: httpx.AsyncClient, user_token: str, page_id: str) -> str:
    response = await client.get(
        f"{GRAPH_API_BASE}/{page_id}",
        params={"fields": "access_token", "access_token": user_token},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def get_days_remaining(client: httpx.AsyncClient, token: str) -> int | None:
    response = await client.get(
        f"{GRAPH_API_BASE}/debug_token",
        params={"input_token": token, "access_token": token},
    )
    response.raise_for_status()
    expires_at = response.json().get("data", {}).get("expires_at", 0)
    if not expires_at:
        return None
    import time

    return int((expires_at - time.time()) // 86400)


async def renew_brand(client: httpx.AsyncClient, brand: dict, outputs: dict) -> bool:
    label = brand["label"]
    app_id = os.environ.get(brand["app_id_env"], "")
    app_secret = os.environ.get(brand["app_secret_env"], "")
    current_user_token = os.environ.get(brand["user_token_env"], "")
    page_id = os.environ.get(brand["page_id_env"], "")

    missing = [
        name
        for name, val in [
            (brand["app_id_env"], app_id),
            (brand["app_secret_env"], app_secret),
            (brand["user_token_env"], current_user_token),
            (brand["page_id_env"], page_id),
        ]
        if not val
    ]
    if missing:
        print(f"[{label}] SKIPPED - missing env vars: {', '.join(missing)}")
        return False

    try:
        new_user_token = await exchange_long_lived_user_token(client, app_id, app_secret, current_user_token)
        mask(new_user_token)

        new_page_token = await get_page_access_token(client, new_user_token, page_id)
        mask(new_page_token)

        days_remaining = await get_days_remaining(client, new_user_token)
        expiry_desc = f"{days_remaining} days remaining" if days_remaining is not None else "no expiry"
        print(f"[{label}] Renewed OK - user token: {expiry_desc}")

        outputs[f"{label}_user_token"] = new_user_token
        outputs[f"{label}_page_token"] = new_page_token
        return True

    except httpx.HTTPStatusError as e:
        print(f"[{label}] FAILED - {e.response.status_code}: {e.response.text[:300]}", file=sys.stderr)
        return False
    except httpx.RequestError as e:
        print(f"[{label}] FAILED - network error: {e}", file=sys.stderr)
        return False


async def main() -> int:
    outputs: dict[str, str] = {}
    all_ok = True

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for brand in BRANDS:
            ok = await renew_brand(client, brand, outputs)
            all_ok = all_ok and ok

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            for key, value in outputs.items():
                f.write(f"{key}={value}\n")
    else:
        print("\n(dry run - GITHUB_OUTPUT not set, no secrets written)")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
