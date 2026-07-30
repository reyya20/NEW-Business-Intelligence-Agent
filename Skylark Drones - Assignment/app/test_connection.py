import requests

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOjY4NjY1NTIyNSwiYWFpIjoxMSwidWlkIjoxMTE1MTA1MzIsImlhZCI6IjIwMjYtMDctMjdUMDU6NTI6MTEuNTc4WiIsInBlciI6Im1lOndyaXRlIiwiYWN0aWQiOjM2MjI0NjAzLCJyZ24iOiJhcHNlMiJ9.ccPNGf4jGgQWdDsmBNJO-Y6aCaMYR4iSY9dMCa2qxNs"
BOARD_ID = "5030218479"  # Deal Funnel - corrected

query = """
query ($boardId: [ID!]) {
  boards (ids: $boardId) {
    name
    items_page(limit: 3) {
      items { name column_values { column { title } text } }
    }
  }
}
"""
resp = requests.post(
    "https://api.monday.com/v2",
    json={"query": query, "variables": {"boardId": [BOARD_ID]}},
    headers={"Authorization": TOKEN, "Content-Type": "application/json"},
)
print(resp.status_code)
print(resp.json())