# fixture1-py-messy
# A messy Python repo with:
# - Hardcoded secret in config.py
# - Duplicated function across 3 files
# - No tests

def parse_user_data(data):
    """Parse user data from dict."""
    name = data.get("name", "")
    email = data.get("email", "")
    return {"name": name, "email": email}

def process_record(rec):
    """Process a record."""
    name = rec.get("name", "")
    email = rec.get("email", "")
    return {"name": name, "email": email}

def transform_entry(entry):
    """Transform an entry."""
    name = entry.get("name", "")
    email = entry.get("email", "")
    return {"name": name, "email": email}
