"""Configuration for fixture1-py-messy.

Intentionally contains a hardcoded credential for testing the secret scanner.
The value below is a FAKE, randomly-typed test string (not a real provider key),
so it exercises detection without being a usable credential.
"""
import os

# Hardcoded credential (FAKE — for testing the secret scanner only)
SERVICE_API_KEY = "d3adb33fc4fef00d1234567890abcdef"
DATABASE_URL = "postgresql://user:pass@localhost:5432/db"

def get_config():
    return {
        "service_key": SERVICE_API_KEY,
        "database_url": DATABASE_URL,
    }
