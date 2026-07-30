"""
monday.com API client — READ ONLY.

Design decision: rather than relying on monday's native column *type* (Status,
Date, Numbers, etc.), we pull every column via its `.text` representation.
`.text` is monday's own normalized string rendering of a cell regardless of
the underlying column type, which makes this client robust to however the
CSV importer auto-typed the columns during manual import. All real type
coercion (dates, numbers, categories) happens in our own normalization layer
(normalize.py), not here. This was a deliberate trade-off to avoid spending
build time scripting monday's column-metadata API. See DECISION_LOG.md.
"""

import os
import time
import requests
from typing import Any

MONDAY_API_URL = "https://api.monday.com/v2"


class MondayAPIError(Exception):
    pass


class MondayClient:
    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or os.environ.get("MONDAY_API_TOKEN")
        if not self.api_token:
            raise MondayAPIError(
                "No monday.com API token found. Set MONDAY_API_TOKEN env var "
                "or pass api_token explicitly."
            )
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }

    def _post(self, query: str, variables: dict | None = None, retries: int = 3) -> dict:
        payload = {"query": query, "variables": variables or {}}
        last_err = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    MONDAY_API_URL, json=payload, headers=self.headers, timeout=30
                )
            except requests.RequestException as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code == 429:
                # rate limited — back off and retry
                time.sleep(2 * (attempt + 1))
                continue

            if resp.status_code != 200:
                raise MondayAPIError(
                    f"monday.com API returned HTTP {resp.status_code}: {resp.text[:500]}"
                )

            data = resp.json()
            if "errors" in data:
                raise MondayAPIError(f"monday.com GraphQL errors: {data['errors']}")
            return data

        raise MondayAPIError(f"monday.com API failed after {retries} retries: {last_err}")

    def get_board_name(self, board_id: str) -> str:
        query = """
        query ($boardId: [ID!]) {
          boards (ids: $boardId) { name }
        }
        """
        data = self._post(query, {"boardId": [board_id]})
        boards = data.get("data", {}).get("boards", [])
        return boards[0]["name"] if boards else "Unknown board"

    def fetch_board_items(self, board_id: str) -> list[dict[str, Any]]:
        """
        Fetch all items from a board as a list of plain dicts:
        { "<Column Title>": "<text value>", ... }
        Handles pagination via items_page cursors.
        """
        query = """
        query ($boardId: ID!, $cursor: String) {
          boards (ids: [$boardId]) {
            items_page (limit: 100, cursor: $cursor) {
              cursor
              items {
                id
                name
                column_values {
                  id
                  text
                  column { title }
                }
              }
            }
          }
        }
        """
        rows: list[dict[str, Any]] = []
        cursor = None

        # Board name only affects which compatibility key we add per row,
        # and it's constant for the whole board — fetch it once, outside
        # the pagination loop, instead of once per item.
        board_name = self.get_board_name(board_id).lower()

        while True:
            data = self._post(query, {"boardId": str(board_id), "cursor": cursor})
            boards = data.get("data", {}).get("boards", [])
            if not boards:
                raise MondayAPIError(
                    f"Board {board_id} not found or token lacks access. "
                    f"Check MONDAY_BOARD ids and API token permissions."
                )
            page = boards[0]["items_page"]
            items = page["items"]

            for item in items:
                row: dict[str, Any] = {}

                # monday.com primary item name
                row["Name"] = item["name"]

                for cv in item["column_values"]:
                    title = cv["column"]["title"]
                    row[title] = cv["text"]

                # ------------------------------------------------------------------
                # Compatibility with original CSV column names
                # ------------------------------------------------------------------
                if "deal" in board_name:
                    row["Deal Name"] = row["Name"]

                if "work" in board_name:
                    row["Deal name masked"] = row["Name"]

                rows.append(row)

            # Advance pagination: monday returns cursor=None once there's
            # no next page, which is also our termination condition.
            cursor = page["cursor"]
            if not cursor:
                break

        return rows