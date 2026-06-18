"""Main app for fixture4-py-secure.

Demonstrates a tiny Python app that uses a known-vulnerable dependency version
(pinned in requirements.txt). The dependency scanner should detect this.
"""
import requests


def fetch_user(user_id: int) -> dict:
    """Fetch user from API."""
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()


def list_users() -> list:
    """List all users."""
    response = requests.get("https://api.example.com/users")
    return response.json()


if __name__ == "__main__":
    print(list_users())
