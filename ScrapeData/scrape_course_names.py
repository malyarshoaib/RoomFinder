import csv
import time

from playwright.sync_api import sync_playwright


def scrape_course_names(url):
    with sync_playwright() as p:
        # Launch Chromium headless browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Proceed to the requested page
        page.goto(url)

        # Ensure elements are ready before interaction
        page.wait_for_selector('span.title')

        # Extract all elements with the class 'title'
        course_elements = page.query_selector_all('span.title')

        course_names = []
        with open("output.txt", "w") as file:

            for element in course_elements:
                # Extract the element text content
                title = element.inner_text()
                file.write(title.strip())
                file.write("\n")
                if title:
                    course_names.append(title.strip())


            # Close the browser
            browser.close()

        return course_names

if __name__ == "__main__":
    #Replace with the actual URL containing the courses
    target_url = "https://www.unf.edu/catalog/courses/index.html"
    courses = scrape_course_names(target_url)