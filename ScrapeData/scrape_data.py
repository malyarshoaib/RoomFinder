import csv
import json
import os
import re
import time
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright
from sanitize_data import sanitize_data, scrub_text


# ============================================================
# CONFIG
# ============================================================

START_URL = (
    "https://banregister.your_univercity.edu/" # example https://banregister.uf.edu/  example https://banregister.unf.edu/ 
    "StudentRegistrationSsb/ssb/courseSearch/courseSearch"
)

SEARCH_RESULTS_PATH = (
    "/StudentRegistrationSsb/ssb/searchResults/searchResults"
)

RESET_PATH = (
    "/StudentRegistrationSsb/ssb/classSearch/resetDataForm"
)

TERM_NAME = "Fall 2026"  #current term
DEFAULT_TERM_CODE = "202680" # current term code 

# Banner supports up to 500 according to the endpoint behavior.
PAGE_SIZE = 500

RAW_JSON_FILE = "fall_2026_raw.json"
ALL_CSV_FILE = "all_classes.csv"
IN_PERSON_CSV_FILE = "in_person_classes.csv"


# ============================================================
# BROWSER FETCH
# ============================================================

def browser_fetch(
    page,
    path,
    method="GET",
    params=None,
):
    """
    Runs fetch() INSIDE Chromium.

    This means:
      - uses the existing Banner session
      - uses Banner cookies
      - avoids Playwright APIRequestContext TLS problem
    """

    result = page.evaluate(
        """
        async ({path, method, params}) => {

            const url = new URL(
                path,
                window.location.origin
            );

            if (params) {
                for (
                    const [key, value]
                    of Object.entries(params)
                ) {
                    url.searchParams.set(
                        key,
                        value === null ||
                        value === undefined
                            ? ""
                            : String(value)
                    );
                }
            }

            const controller =
                new AbortController();

            const timer = setTimeout(
                () => controller.abort(),
                60000
            );

            try {

                const response = await fetch(
                    url.toString(),
                    {
                        method: method,

                        credentials: "include",

                        cache: "no-store",

                        signal: controller.signal,

                        headers: {
                            "Accept":
                                "application/json, " +
                                "text/javascript, */*; q=0.01",

                            "X-Requested-With":
                                "XMLHttpRequest"
                        }
                    }
                );

                const text =
                    await response.text();

                let json = null;

                try {
                    json = JSON.parse(text);
                }
                catch (error) {
                    // Some Banner endpoints return plain text.
                }

                return {
                    ok: response.ok,
                    status: response.status,
                    statusText:
                        response.statusText,
                    url: response.url,
                    text: text,
                    json: json
                };
            }

            catch (error) {

                return {
                    ok: false,
                    status: 0,
                    statusText:
                        String(error),
                    url: url.toString(),
                    text: String(error),
                    json: null
                };
            }

            finally {
                clearTimeout(timer);
            }
        }
        """,
        {
            "path": path,
            "method": method,
            "params": params or {},
        }
    )

    if not result["ok"]:
        raise RuntimeError(
            "\nBanner request failed\n"
            f"Status: {result['status']} "
            f"{scrub_text(result['statusText'])}\n"
            f"URL: {scrub_text(result['url'])}\n"
        )

    return result


# ============================================================
# ESTABLISH BANNER SESSION
# ============================================================

def establish_banner_session(page):
    """
    Selects Fall 2026 and performs ONE sacrificial search
    so we can capture Banner's uniqueSessionId.

    We reset that search immediately afterward.
    """

    print()
    print("=" * 70)
    print("ESTABLISHING BANNER SESSION")
    print("=" * 70)

    print("Opening UNF Banner...")

    page.goto(
        START_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print(f"Selecting {TERM_NAME}...")

    page.locator(
        "#classSearch-desc"
    ).click()

    page.locator(
        "#select2-chosen-1"
    ).click()

    page.get_by_text(
        TERM_NAME,
        exact=True
    ).click()

    page.get_by_role(
        "button",
        name="Continue"
    ).click()

    page.wait_for_url(
        "**/classSearch/classSearch**",
        timeout=60000
    )

    course_input = page.locator(
        "#txt_courseNumber"
    )

    course_input.wait_for(
        state="visible",
        timeout=30000
    )

    print(
        "Performing one test search "
        "to capture uniqueSessionId..."
    )

    # We already know 2021 exists from your captured data.
    with page.expect_response(
        lambda response:
            "/searchResults/searchResults"
            in response.url,
        timeout=60000
    ) as response_info:

        course_input.fill("2021")
        course_input.press("Enter")

    response = response_info.value

    # Ensure body has actually arrived before resetting.
    try:
        response.text()
    except Exception:
        pass

    parsed = urlparse(response.url)
    query = parse_qs(parsed.query)

    unique_session_id = (
        query.get(
            "uniqueSessionId",
            [None]
        )[0]
    )

    term_code = (
        query.get(
            "txt_term",
            [DEFAULT_TERM_CODE]
        )[0]
    )

    if not unique_session_id:
        raise RuntimeError(
            "Could not capture Banner uniqueSessionId."
        )

    print(
        f"Term code: {term_code}"
    )

    print(
        "Banner session established."
    )

    return term_code, unique_session_id


# ============================================================
# RESET BANNER SEARCH STATE
# ============================================================

def reset_search_state(page):
    """
    THIS IS THE PIECE THE PREVIOUS SCRIPT WAS MISSING.

    Banner remembers the last search server-side.
    We reset it before starting the all-term query.
    """

    print(
        "Resetting Banner's previous search state..."
    )

    result = browser_fetch(
        page,
        RESET_PATH,
        method="POST"
    )

    print(
        f"Reset response status: {result['status']}"
    )


# ============================================================
# SAVE RAW JSON CHECKPOINT
# ============================================================

def save_raw_json(sections):
    """
    Writes what we've downloaded so far.

    Called after every page so even if something dies,
    the downloaded data isn't lost.
    """

    with open(
        RAW_JSON_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            sanitize_data(sections),
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# FETCH ENTIRE FALL 2026 TERM
# ============================================================

def fetch_all_fall_sections(
    page,
    term_code,
    unique_session_id,
):
    """
    Fetch ALL sections for Fall 2026.

    No subject filter.
    No course-number filter.

    500 results at a time.
    """

    print()
    print("=" * 70)
    print("DOWNLOADING ALL FALL 2026 SECTIONS")
    print("=" * 70)

    all_sections = []

    # Protect against accidental duplicate pages.
    seen_crns = set()

    offset = 0
    total_count = None
    page_number = 1

    while True:

        print()
        print(
            f"Requesting page {page_number} "
            f"(offset {offset})..."
        )

        params = {
            # ------------------------------------------------
            # BLANK = ALL SUBJECTS / ALL COURSE NUMBERS
            # ------------------------------------------------

            "txt_subject": "",
            "txt_courseNumber": "",

            "txt_term": term_code,

            "startDatepicker": "",
            "endDatepicker": "",

            "uniqueSessionId":
                unique_session_id,

            "pageOffset":
                offset,

            "pageMaxSize":
                PAGE_SIZE,

            "sortColumn":
                "subjectDescription",

            "sortDirection":
                "asc",
        }

        # Retry a page up to three times.
        payload = None

        for attempt in range(1, 4):

            try:

                response = browser_fetch(
                    page,
                    SEARCH_RESULTS_PATH,
                    method="GET",
                    params=params
                )

                payload = response["json"]

                if payload is None:
                    raise RuntimeError(
                        "Banner did not return JSON."
                    )

                if not payload.get(
                    "success",
                    False
                ):
                    raise RuntimeError(
                        "Banner returned "
                        "success=false."
                    )

                break

            except Exception as error:

                print(
                    f"Attempt {attempt}/3 failed:"
                )

                print(error)

                if attempt == 3:
                    raise

                time.sleep(2)

        batch = payload.get("data") or []

        reported_total = (
            payload.get("totalCount", 0)
            or 0
        )

        if total_count is None:
            total_count = reported_total

            print()
            print(
                "Banner reports "
                f"{total_count:,} total "
                "Fall 2026 sections."
            )

        print(
            f"Received {len(batch):,} records."
        )

        if not batch:
            print(
                "No more records returned."
            )
            break

        # ----------------------------------------------------
        # VERIFY THIS IS ACTUALLY A NEW PAGE
        # ----------------------------------------------------

        new_sections = []

        for section in batch:

            crn = str(
                section.get(
                    "courseReferenceNumber",
                    ""
                )
            ).strip()

            if crn and crn in seen_crns:
                continue

            if crn:
                seen_crns.add(crn)

            new_sections.append(
                section
            )

        print(
            f"New unique records on page: "
            f"{len(new_sections):,}"
        )

        # This catches exactly the bug that caused the
        # previous 23,850 fake/repeated records.
        if batch and not new_sections:

            raise RuntimeError(
                "\nBanner repeated the exact same "
                "page instead of advancing.\n"
                "Stopping instead of silently "
                "duplicating thousands of records."
            )

        all_sections.extend(
            new_sections
        )

        # ----------------------------------------------------
        # CHECKPOINT
        # ----------------------------------------------------

        save_raw_json(
            all_sections
        )

        print(
            f"Unique sections downloaded so far: "
            f"{len(all_sections):,}"
        )

        print(
            f"Checkpoint saved to "
            f"{RAW_JSON_FILE}"
        )

        # ----------------------------------------------------
        # FINISHED?
        # ----------------------------------------------------

        if (
            total_count
            and len(all_sections)
            >= total_count
        ):
            break

        # Banner offset = index, not page number.
        offset += len(batch)
        page_number += 1

    print()
    print(
        f"FINISHED DOWNLOAD: "
        f"{len(all_sections):,} "
        f"unique sections."
    )

    return all_sections


# ============================================================
# INSTRUCTOR
# ============================================================

def clean_instructor_name(name):
    if not name:
        return ""

    name = str(name).strip()

    # Remove Banner's trailing "(Primary)" / "(" junk.
    name = re.sub(
        r"\s*\(.*$",
        "",
        name
    )

    return name.strip()


def get_instructors(section):
    faculty = (
        section.get("faculty")
        or []
    )

    names = []

    for professor in faculty:

        name = clean_instructor_name(
            professor.get(
                "displayName",
                ""
            )
        )

        if (
            name
            and name not in names
        ):
            names.append(name)

    if not names:
        return "TBA"

    return "; ".join(names)


# ============================================================
# TIME FORMATTING
# ============================================================

def format_time(value):
    if not value:
        return ""

    value = str(value).strip().zfill(4)

    if len(value) != 4:
        return value

    try:
        hour = int(value[:2])
        minute = int(value[2:])

    except ValueError:
        return value

    suffix = (
        "AM"
        if hour < 12
        else "PM"
    )

    display_hour = hour % 12

    if display_hour == 0:
        display_hour = 12

    return (
        f"{display_hour}:"
        f"{minute:02d} "
        f"{suffix}"
    )


# ============================================================
# MEETING INFORMATION
# ============================================================

def format_meetings(section):
    meetings = (
        section.get(
            "meetingsFaculty"
        )
        or []
    )

    output = []

    day_fields = [
        ("monday", "M"),
        ("tuesday", "T"),
        ("wednesday", "W"),
        ("thursday", "R"),
        ("friday", "F"),
        ("saturday", "S"),
        ("sunday", "U"),
    ]

    for meeting in meetings:

        meeting_time = (
            meeting.get(
                "meetingTime"
            )
            or {}
        )

        days = "".join(
            abbreviation
            for field, abbreviation
            in day_fields
            if meeting_time.get(field)
        )

        begin = format_time(
            meeting_time.get(
                "beginTime"
            )
        )

        end = format_time(
            meeting_time.get(
                "endTime"
            )
        )

        building = str(
            meeting_time.get(
                "buildingDescription"
            )
            or meeting_time.get(
                "building"
            )
            or ""
        ).strip()

        room = str(
            meeting_time.get(
                "room"
            )
            or ""
        ).strip()

        pieces = []

        if days:
            pieces.append(days)

        if begin and end:
            pieces.append(
                f"{begin} - {end}"
            )

        elif begin:
            pieces.append(begin)

        if building:

            location = building

            if room:
                location += (
                    f" Room {room}"
                )

            pieces.append(location)

        if pieces:
            output.append(
                " | ".join(pieces)
            )

    if not output:
        return "TBA"

    return "; ".join(output)


# ============================================================
# ONLINE DETECTION
# ============================================================

def is_online(section):
    """
    Determine whether section is an online/distance-learning
    section based on Banner's actual fields.
    """

    campus = str(
        section.get(
            "campusDescription",
            ""
        )
    ).lower()

    if (
        "distance learning" in campus
        or campus.strip() == "online"
    ):
        return True

    method_code = str(
        section.get(
            "instructionalMethod",
            ""
        )
    ).upper()

    method_description = str(
        section.get(
            "instructionalMethodDescription",
            ""
        )
    ).lower()

    if method_code == "OL":
        return True

    if (
        "online"
        in method_description
        or
        "distance learning"
        in method_description
    ):
        return True

    # Section attributes
    for attribute in (
        section.get(
            "sectionAttributes"
        )
        or []
    ):

        code = str(
            attribute.get(
                "code",
                ""
            )
        ).upper()

        description = str(
            attribute.get(
                "description",
                ""
            )
        ).lower()

        if code == "LDL":
            return True

        if (
            "distance learning"
            in description
        ):
            return True

    # Meeting-specific data
    for meeting in (
        section.get(
            "meetingsFaculty"
        )
        or []
    ):

        meeting_time = (
            meeting.get(
                "meetingTime"
            )
            or {}
        )

        campus_code = str(
            meeting_time.get(
                "campus",
                ""
            )
        ).upper()

        building = str(
            meeting_time.get(
                "building",
                ""
            )
        ).upper()

        if campus_code == "DL":
            return True

        if building == "ONLINE":
            return True

    return False


# ============================================================
# STATUS
# ============================================================

def get_status(section):
    seats = section.get(
        "seatsAvailable"
    )

    wait_available = section.get(
        "waitAvailable"
    )

    if seats is None:
        return ""

    try:
        seats = int(seats)
    except (
        ValueError,
        TypeError
    ):
        return ""

    if seats > 0:
        return "OPEN"

    try:
        if (
            wait_available is not None
            and int(wait_available) > 0
        ):
            return (
                "FULL - WAITLIST AVAILABLE"
            )
    except (
        ValueError,
        TypeError
    ):
        pass

    return "FULL"


# ============================================================
# SECTION -> CSV ROW
# ============================================================

def section_to_row(section):
    subject = str(
        section.get(
            "subject",
            ""
        )
    ).strip()

    course_number = str(
        section.get(
            "courseNumber",
            ""
        )
    ).strip()

    return {
        "CRN":
            section.get(
                "courseReferenceNumber",
                ""
            ),

        "Subject":
            subject,

        "Course Number":
            course_number,

        "Course":
            (
                f"{subject} "
                f"{course_number}"
            ).strip(),

        "Title":
            str(
                section.get(
                    "courseTitle",
                    ""
                )
            ).strip(),

        "Instructor":
            get_instructors(
                section
            ),

        "Meeting Times":
            format_meetings(
                section
            ),

        "Campus":
            section.get(
                "campusDescription",
                ""
            ),

        "Instructional Method":
            section.get(
                "instructionalMethodDescription",
                ""
            ),

        "Status":
            get_status(
                section
            ),

        "Seats Available":
            section.get(
                "seatsAvailable",
                ""
            ),

        "Enrollment":
            section.get(
                "enrollment",
                ""
            ),

        "Maximum Enrollment":
            section.get(
                "maximumEnrollment",
                ""
            ),

        "Waitlist Available":
            section.get(
                "waitAvailable",
                ""
            ),
    }


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    sections,
    filename,
):
    fieldnames = [
        "CRN",
        "Subject",
        "Course Number",
        "Course",
        "Title",
        "Instructor",
        "Meeting Times",
        "Campus",
        "Instructional Method",
        "Status",
        "Seats Available",
        "Enrollment",
        "Maximum Enrollment",
        "Waitlist Available",
    ]

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            lineterminator="\n"
        )

        writer.writeheader()

        for section in sections:

            writer.writerow(
                sanitize_data(section_to_row(
                    section
                ))
            )

    print(
        f"Saved {len(sections):,} "
        f"rows to {filename}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            ignore_https_errors=True
        )

        page = context.new_page()

        try:

            # ------------------------------------------------
            # 1. Establish Fall 2026 session
            # ------------------------------------------------

            (
                term_code,
                unique_session_id
            ) = establish_banner_session(
                page
            )

            # ------------------------------------------------
            # 2. CRITICAL: clear the sacrificial 2021 search
            # ------------------------------------------------

            reset_search_state(
                page
            )

            # ------------------------------------------------
            # 3. Download ENTIRE Fall 2026 semester
            # ------------------------------------------------

            sections = (
                fetch_all_fall_sections(
                    page,
                    term_code,
                    unique_session_id
                )
            )

            # ------------------------------------------------
            # 4. Save EVERYTHING first
            # ------------------------------------------------

            print()
            print("=" * 70)
            print("SAVING ALL SECTIONS")
            print("=" * 70)

            save_csv(
                sections,
                ALL_CSV_FILE
            )

            # ------------------------------------------------
            # 5. Filter online LOCALLY
            # ------------------------------------------------

            in_person_sections = [
                section
                for section in sections
                if not is_online(section)
            ]

            online_count = (
                len(sections)
                - len(in_person_sections)
            )

            print()
            print("=" * 70)
            print("FILTERING SUMMARY")
            print("=" * 70)

            print(
                f"Total unique sections: "
                f"{len(sections):,}"
            )

            print(
                f"Online/distance sections: "
                f"{online_count:,}"
            )

            print(
                f"In-person sections: "
                f"{len(in_person_sections):,}"
            )

            # ------------------------------------------------
            # 6. Save filtered result separately
            # ------------------------------------------------

            save_csv(
                in_person_sections,
                IN_PERSON_CSV_FILE
            )

            print()
            print("=" * 70)
            print("DONE")
            print("=" * 70)

            print(
                "Raw JSON:"
            )
            print(
                os.path.abspath(
                    RAW_JSON_FILE
                )
            )

            print()
            print(
                "ALL Fall 2026 sections:"
            )
            print(
                os.path.abspath(
                    ALL_CSV_FILE
                )
            )

            print()
            print(
                "In-person Fall 2026 sections:"
            )
            print(
                os.path.abspath(
                    IN_PERSON_CSV_FILE
                )
            )

        finally:
            browser.close()


if __name__ == "__main__":
    main()