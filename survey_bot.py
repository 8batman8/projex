"""
Qualtrics survey bot — "Will Finance Settle Onchain"
URL: https://endicott.qualtrics.com/jfe/form/SV_a9LBISadTNUsjDo

Install deps:
    pip install playwright
    playwright install chromium

Run:
    python survey_bot.py
"""

import asyncio
import os
import random
import time
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SURVEY_URL = "https://endicott.qualtrics.com/jfe/form/SV_a9LBISadTNUsjDo"
TOTAL_RUNS = int(os.environ.get("TOTAL_RUNS", 250))

# Seconds to wait between full survey runs
BETWEEN_RUN_DELAY = (3, 10)

# Seconds to wait between answering individual questions
BETWEEN_QUESTION_DELAY = (0.5, 2.5)

# Seconds to wait after clicking Next/Submit
AFTER_NAVIGATION_DELAY = (1.0, 3.0)

# ---------------------------------------------------------------------------
# User agents — a realistic mix of desktop browsers
# ---------------------------------------------------------------------------

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

# ---------------------------------------------------------------------------
# Answer pools — weighted to feel realistic (slight pro-blockchain skew
# matching the survey's framing, mixed with genuine neutral/skeptic voices)
# ---------------------------------------------------------------------------

# Q1: How often do hidden intermediary fees catch you by surprise?
Q1_OPTIONS = ["Never", "Sometimes", "About half the time", "Most of the time", "Always"]
Q1_WEIGHTS  = [0.10,   0.30,        0.25,                  0.25,               0.10]

# Q2: Does a $1,000 transfer cost more via traditional banking than stablecoin?
Q2_OPTIONS = ["Negligible", "Inexpensive", "Expensive", "Very Expensive"]
Q2_WEIGHTS  = [0.05,         0.15,          0.45,        0.35]

# Q3: Gas fees vs tiered fee structures — predictability
Q3_OPTIONS = ["Not predictable", "Somewhat predictable", "Highly predictable"]
Q3_WEIGHTS  = [0.15,              0.40,                   0.45]

# Q4: How many business days for a traditional wire to clear?
Q4_OPTIONS = ["<1 Day", "1-3 Days", "3-5 Days", ">7 Days"]
Q4_WEIGHTS  = [0.05,     0.30,       0.45,        0.20]

# Q6: Frustration with weekend/holiday delays
Q6_OPTIONS = [
    "None",
    "Somewhat Frustrated",
    "High Frustration",
    "Extreme Disappointment (Seeking an alternative)",
]
Q6_WEIGHTS  = [0.08, 0.25, 0.35, 0.32]

# Q7: Intermediary banks are the primary reason for high costs & slow speeds
Q7_OPTIONS = ["None at all", "A little", "A moderate amount", "A lot", "A great deal"]
Q7_WEIGHTS  = [0.05,          0.10,       0.25,                0.35,    0.25]

# Q8: Real-time ledger tracking vs "black box" bank transfer
Q8_OPTIONS = ["Decreases Confidence", "Doesn't change my opinion", "Increases Confidence"]
Q8_WEIGHTS  = [0.05,                   0.20,                        0.75]

# Q9: Difficulty identifying which institution is holding delayed funds
Q9_OPTIONS = ["Very Difficult", "Difficult", "Easy", "Very Easy"]
Q9_WEIGHTS  = [0.35,             0.40,        0.18,   0.07]

# Q10: 24/7 automated operation advantage over correspondent banking
Q10_OPTIONS = ["No Advantage", "Some Advantage", "Significant Advantage"]
Q10_WEIGHTS  = [0.08,           0.32,              0.60]

ALL_QUESTIONS = [
    Q1_OPTIONS,
    Q2_OPTIONS,
    Q3_OPTIONS,
    Q4_OPTIONS,
    Q6_OPTIONS,
    Q7_OPTIONS,
    Q8_OPTIONS,
    Q9_OPTIONS,
    Q10_OPTIONS,
]
ALL_WEIGHTS = [
    Q1_WEIGHTS,
    Q2_WEIGHTS,
    Q3_WEIGHTS,
    Q4_WEIGHTS,
    Q6_WEIGHTS,
    Q7_WEIGHTS,
    Q8_WEIGHTS,
    Q9_WEIGHTS,
    Q10_WEIGHTS,
]


def pick(options, weights):
    """Weighted random choice."""
    return random.choices(options, weights=weights, k=1)[0]


def random_delay(lo, hi):
    """Sleep for a random duration in [lo, hi] seconds."""
    time.sleep(random.uniform(lo, hi))


async def click_radio_by_label(page, question_container, answer_text):
    """
    Find and click a radio-button answer inside a Qualtrics question block.
    Qualtrics renders answers as <label> elements whose text matches the choice.
    We try clicking the label; fall back to clicking the underlying <input>.
    """
    # Qualtrics wraps each answer in a label — find by visible text
    label = question_container.locator(
        f"label", has_text=answer_text
    ).first

    if await label.count() == 0:
        # Try broader: any element with that exact text that is clickable
        label = question_container.locator(f"*", has_text=answer_text).first

    await label.scroll_into_view_if_needed()
    await label.click()


async def run_survey(browser, run_index: int):
    """Complete one full survey run."""
    ua = random.choice(USER_AGENTS)

    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": random.randint(1280, 1920), "height": random.randint(768, 1080)},
        locale=random.choice(["en-US", "en-GB", "en-CA", "en-AU"]),
        timezone_id=random.choice([
            "America/New_York", "America/Chicago", "America/Denver",
            "America/Los_Angeles", "Europe/London", "Europe/Berlin",
            "Australia/Sydney", "America/Toronto",
        ]),
    )

    page = await context.new_page()

    try:
        print(f"[Run {run_index+1}/{TOTAL_RUNS}] UA: {ua[:60]}...")
        await page.goto(SURVEY_URL, wait_until="networkidle", timeout=30_000)

        # Qualtrics may spread questions across multiple pages.
        # We loop: answer every visible question block, then hit Next/Submit.
        page_num = 0
        while True:
            page_num += 1
            await page.wait_for_load_state("networkidle", timeout=15_000)

            # Gather all visible question containers on this page
            # Qualtrics uses data-qid or class="QuestionBody" / "question-container"
            q_containers = await page.query_selector_all(
                ".QuestionBody, [class*='question-container'], [data-qid]"
            )

            if not q_containers:
                # Fallback: try any fieldset (Qualtrics sometimes uses these)
                q_containers = await page.query_selector_all("fieldset")

            answered = 0
            for container in q_containers:
                # Find all answer labels in this container
                labels = await container.query_selector_all(
                    "label.q-radio, label[for*='QR'], .ChoiceStructure label, "
                    ".choice-wrapper label, li label, label"
                )
                if not labels:
                    continue

                # Pick a random label (answer) and click it
                chosen_label = random.choice(labels)
                await chosen_label.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.2, 0.6))
                await chosen_label.click()
                answered += 1
                await asyncio.sleep(random.uniform(*BETWEEN_QUESTION_DELAY))

            print(f"  Page {page_num}: answered {answered} question(s)")

            await asyncio.sleep(random.uniform(*AFTER_NAVIGATION_DELAY))

            # Look for Submit button first, then Next
            submit_btn = page.locator(
                "button#submitButton, input#submitButton, "
                "button[type=submit], [data-action='submit'], "
                "button:has-text('Submit'), button:has-text('submit')"
            ).first
            next_btn = page.locator(
                "button#NextButton, input#NextButton, "
                "button:has-text('Next'), button:has-text('next'), "
                "[data-action='advance']"
            ).first

            submit_visible = await submit_btn.is_visible().catch_any() if hasattr(submit_btn, "catch_any") else False
            try:
                submit_visible = await submit_btn.is_visible()
            except Exception:
                submit_visible = False

            try:
                next_visible = await next_btn.is_visible()
            except Exception:
                next_visible = False

            if submit_visible:
                print(f"  Submitting...")
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15_000)
                print(f"  [Run {run_index+1}] Done — survey submitted.")
                break
            elif next_visible:
                await next_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15_000)
            else:
                # No navigation button found — check if we landed on a confirmation page
                body_text = await page.inner_text("body")
                if any(w in body_text.lower() for w in ["thank", "complete", "response recorded", "finished"]):
                    print(f"  [Run {run_index+1}] Confirmation page detected — done.")
                else:
                    print(f"  [Run {run_index+1}] WARNING: no Next/Submit button found. Stopping.")
                break

    except Exception as e:
        print(f"  [Run {run_index+1}] ERROR: {e}")
    finally:
        await context.close()


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        for i in range(TOTAL_RUNS):
            await run_survey(browser, i)

            if i < TOTAL_RUNS - 1:
                delay = random.uniform(*BETWEEN_RUN_DELAY)
                print(f"  Waiting {delay:.1f}s before next run...\n")
                await asyncio.sleep(delay)

        await browser.close()
        print("\nAll runs complete.")


if __name__ == "__main__":
    asyncio.run(main())
