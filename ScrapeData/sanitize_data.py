"""Remove faculty identities and captured sessions from repository data.

Run from any directory: python3 /path/to/RoomFinder/ScrapeData/sanitize_data.py
Only the known JSON/CSV datasets are rewritten; column order is preserved.
"""
import csv
import json
import re
from pathlib import Path

REDACTED = "[REDACTED]"
EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SESSION = re.compile(r"(uniqueSessionId=)[^&#\s]*", re.I)
IDENTITY_FIELDS = {"bannerid", "emailaddress", "email", "displayname", "instructor"}


def scrub_text(value):
    return EMAIL.sub(REDACTED, SESSION.sub(r"\1", value))


def sanitize_data(value):
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = key.lower()
            if normalized == "faculty":
                result[key] = []
            elif normalized == "uniquesessionid":
                result[key] = [""] if isinstance(item, list) else ""
            elif normalized in IDENTITY_FIELDS:
                result[key] = REDACTED if item else ""
            else:
                result[key] = sanitize_data(item)
        return result
    if isinstance(value, str):
        return scrub_text(value)
    return value


def sanitize_file(path):
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(sanitize_data(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = [sanitize_data(row) for row in reader]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main():
    directory = Path(__file__).resolve().parent
    paths = [directory / name for name in (
        "banner_requests.json", "fall_2026_raw.json", "all_classes.csv", "in_person_classes.csv"
    )]
    paths.append(directory.parent / "room-finder/src/main/resources/in_person_classes.csv")
    for path in paths:
        if path.is_file():
            sanitize_file(path)
            print(f"Sanitized: {path.name}")


if __name__ == "__main__":
    main()
