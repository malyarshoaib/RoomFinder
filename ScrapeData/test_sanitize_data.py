import csv
import json
from pathlib import Path
import tempfile
import unittest

from sanitize_data import REDACTED, sanitize_data, sanitize_file


class SanitizationTests(unittest.TestCase):
    def test_nested_faculty_removed_and_schedule_preserved(self):
        source = {"faculty": [{"displayName": "Example Person", "bannerId": "N123"}],
                  "meetingsFaculty": [{"faculty": [{"emailAddress": "person@example.edu"}],
                                       "meetingTime": {"room": "201", "beginTime": "0900"}}]}
        clean = sanitize_data(source)
        self.assertEqual(clean["faculty"], [])
        self.assertEqual(clean["meetingsFaculty"][0]["faculty"], [])
        self.assertEqual(clean["meetingsFaculty"][0]["meetingTime"], source["meetingsFaculty"][0]["meetingTime"])
        self.assertTrue(source["faculty"])
        self.assertEqual(sanitize_data(clean), clean)

    def test_sessions_cleared_in_url_and_query(self):
        clean = sanitize_data({"url": "https://example.edu/search?uniqueSessionId=secret&txt_term=202680",
                               "query": {"uniqueSessionId": ["secret"]}, "uniqueSessionId": "secret"})
        self.assertNotIn("secret", json.dumps(clean))
        self.assertEqual(clean["query"]["uniqueSessionId"], [""])
        self.assertIn("txt_term=202680", clean["url"])

    def test_csv_keeps_column_positions_quoted_cells_and_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            fields = ["CRN", "Instructor", "Meeting Times", "Title"]
            row = {"CRN": "123", "Instructor": "Example Person", "Meeting Times": "MW | 9:00 AM - 10:00 AM | Building Room 201", "Title": "Course, part one"}
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(row)
            sanitize_file(path)
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, fields)
                rows = list(reader)
            self.assertEqual(rows, [{**row, "Instructor": REDACTED}])

    def test_standalone_identity_fields_and_embedded_emails(self):
        clean = sanitize_data({"bannerId": "N123", "emailAddress": "person@example.edu",
                               "displayName": "Example Person", "note": "Contact person@example.edu", "id": 123})
        self.assertEqual(clean["bannerId"], REDACTED)
        self.assertEqual(clean["displayName"], REDACTED)
        self.assertNotIn("person@example.edu", json.dumps(clean))
        self.assertEqual(clean["id"], 123)


if __name__ == "__main__":
    unittest.main()
