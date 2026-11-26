"""
Indeed Job Application Automation Module

Follows the same architecture pattern as naukri.py / internshala.py.
Handles Indeed's email-first login flow, search URL construction,
job listing pagination, and the multi-step "Indeed Apply" modal.
"""

import os
import csv
import re
from random import shuffle, randint
from datetime import datetime
from typing import Literal

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import (
    NoSuchElementException, ElementClickInterceptedException,
    NoSuchWindowException, WebDriverException, TimeoutException,
    StaleElementReferenceException
)

import config.secrets
from config.secrets import use_AI, username, password, ai_provider
from config.search import *
from config.settings import *
from config.personals import *
from config.questions import *

from modules.helpers import (
    buffer, print_lg, sleep, manual_login_retry,
    truncate_for_csv, calculate_date_posted, critical_error_log,
    robust_get, screenshot, is_timeout
)
from modules.domain_filter import is_tech_job, is_experience_eligible
from modules.question_solver import auto_fill_form_elements, prompt_user_if_stuck, is_resume_file_input
from modules.clickers_and_finders import (
    try_linkText, try_xp, text_input_by_ID, find_by_class,
    wait_span_click, multi_sel_noWait, boolean_button_click,
    try_find_by_classes, scroll_to_view
)
from modules.history import save_submitted_job, save_failed_job

if use_AI:
    from modules.ai.openaiConnections import ai_answer_question
    from modules.ai.geminiConnections import gemini_answer_question

try:
    import pyautogui
except:
    pass

# ---------------------------------------------------------------------------
# Module-level globals (set by init_indeed)
# ---------------------------------------------------------------------------
driver: WebDriver = None
wait: WebDriverWait = None
actions = None
aiClient = None

# Counters / flags
applied_count = 0
failed_count = 0
skip_count = 0
dailyLimitReached = False
indeed_tab = None


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
def init_indeed(drv, wt, act, ai_clnt):
    global driver, wait, actions, aiClient, indeed_tab
    driver = drv
    wait = wt
    actions = act
    aiClient = ai_clnt
    indeed_tab = driver.current_window_handle


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------
def is_logged_in_IN() -> bool:
    """Check if the user is logged in to Indeed."""
    try:
        url = driver.current_url.lower()
        if any(x in url for x in ["/account/login", "/auth", "/login", "/signup", "/account/register"]):
            return False

        # If visible 'Sign in' link exists, clearly not logged in
        sign_in_elements = driver.find_elements(By.XPATH,
            "//a[contains(@href, 'account/login') or normalize-space()='Sign in' or contains(@data-gnav-element-name, 'SignIn')]"
        )
        for s in sign_in_elements:
            try:
                if s.is_displayed():
                    return False
            except:
                pass

        # Indeed shows account-related elements when logged in
        indicators = [
            "//button[contains(@aria-label, 'Account') or contains(@aria-label, 'Profile') or contains(@aria-label, 'account')]",
            "//*[contains(@data-gnav-element-name, 'AccountMenu') or contains(@data-gnav-element-name, 'UserAvatar')]",
            "//a[contains(@href, '/account/view')]",
            "//a[contains(@href, 'myjobs') and not(contains(@href, 'login'))]",
            "//*[@id='gnav-header-account']",
            "//span[contains(@class, 'gnav-Account')]",
            "//div[contains(@class, 'gnav-LoggedInAccountLink')]",
        ]
        for xp in indicators:
            try:
                el = driver.find_element(By.XPATH, xp)
                if el and el.is_displayed():
                    return True
            except:
                continue

        # Check URL for genuine post-login destinations (excluding login/auth)
        if any(x in url for x in ["/myjobs", "/account/view", "/mysearches", "/settings/account"]):
            return True

        return False
    except:
        return False


def close_modals():
    """Dismiss any popups / cookie banners / overlays on Indeed."""
    try:
        modal_close_selectors = [
            "//button[contains(@id, 'onetrust-accept')]",
            "//button[contains(@aria-label, 'close')]",
            "//button[contains(@aria-label, 'Close')]",
            "//button[contains(@class, 'icl-CloseButton')]",
            "//button[contains(@class, 'popover-x-button')]",
            "//div[contains(@class, 'popover-x-button')]",
            "//button[@id='mosaic-desktopserpjap498']",
            "//button[contains(text(), 'Skip')]",
            "//button[contains(text(), 'No thanks')]",
            "//button[contains(text(), 'Not now')]",
            "//button[contains(text(), 'Dismiss')]",
            "//div[@id='mosaic-modal-mosaic-provider-desktopserp-close-button']",
        ]
        for sel in modal_close_selectors:
            try:
                btns = driver.find_elements(By.XPATH, sel)
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        sleep(0.5)
            except:
                continue
    except:
        pass


def login_IN() -> None:
    """Log in to Indeed. Handles email-first flow with password or verification code."""
    robust_get(driver, "https://secure.indeed.com/account/login")
    sleep(3)

    if is_logged_in_IN():
        print_lg("Already logged in to Indeed.")
        return

    # Use platform-specific credentials if available
    in_username = getattr(config.secrets, 'indeed_username', '') or username
    in_password = getattr(config.secrets, 'indeed_password', '') or password

    try:
        close_modals()

        # --- Step 1: Enter email ---
        email_field = None
        email_selectors = [
            (By.ID, "ifl-InputFormField-3"),
            (By.NAME, "__email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[name='__email']"),
            (By.XPATH, "//input[contains(@id, 'email') or contains(@name, 'email')]"),
            (By.CSS_SELECTOR, "#login-email-input"),
            (By.CSS_SELECTOR, "input[autocomplete='email']"),
        ]
        for by, sel in email_selectors:
            try:
                email_field = WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((by, sel))
                )
                if email_field:
                    break
            except:
                continue

        if not email_field:
            print_lg("Could not find Indeed email field. Trying manual login fallback.")
            screenshot(driver, "Indeed", "Login_NoEmailField")
            manual_login_retry(is_logged_in_IN, 2)
            return

        from modules.helpers import type_human_like
        type_human_like(email_field, in_username)
        sleep(1)

        # Click "Continue" or "Sign in" after email
        continue_btn = _find_button(["Continue", "Sign in", "Log in", "Next"])
        if continue_btn:
            try:
                driver.execute_script("arguments[0].click();", continue_btn)
            except:
                continue_btn.click()
        else:
            email_field.send_keys(Keys.ENTER)
        sleep(4)

        # --- Step 2: Check what Indeed presents next ---
        # A) Password field
        pass_field = None
        pass_selectors = [
            (By.ID, "ifl-InputFormField-7"),
            (By.NAME, "__password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.XPATH, "//input[contains(@id, 'password') or contains(@name, 'password')]"),
            (By.CSS_SELECTOR, "#login-password-input"),
        ]
        for by, sel in pass_selectors:
            try:
                pass_field = WebDriverWait(driver, 4).until(
                    EC.visibility_of_element_located((by, sel))
                )
                if pass_field:
                    break
            except:
                continue

        if pass_field:
            from modules.helpers import type_human_like
            type_human_like(pass_field, in_password)
            sleep(1)

            # Click the sign-in / continue button
            sign_in_btn = _find_button(["Sign in", "Log in", "Continue", "Submit"])
            if sign_in_btn:
                try:
                    driver.execute_script("arguments[0].click();", sign_in_btn)
                except:
                    sign_in_btn.click()
            else:
                pass_field.send_keys(Keys.ENTER)

            print_lg("Submitted Indeed login credentials. Waiting for redirect...")
            sleep(7)
        else:
            # B) Check for "Sign in with a code instead" or Google SSO prompt
            print_lg("Password field not directly visible. Checking for code or alternative login...")
            try:
                code_link = driver.find_element(By.XPATH, "//a[contains(text(), 'code') or contains(text(), 'Code')]")
                if code_link and code_link.is_displayed():
                    print_lg("Found 'Sign in with a code instead'. Clicking it to request verification code...")
                    try:
                        code_link.click()
                    except:
                        driver.execute_script("arguments[0].click();", code_link)
                    sleep(3)
            except:
                pass

            page_text = driver.page_source.lower()
            if "code" in page_text or "verification" in page_text or "google" in page_text:
                print_lg(f"Indeed authentication requires verification or Google login for {in_username}.")
                print_lg("Please enter verification code or complete login in the open Chrome browser window.")
                screenshot(driver, "Indeed", "Login_Verification_Required")
                manual_login_retry(is_logged_in_IN, 3)

        # --- Verify login ---
        if is_logged_in_IN():
            print_lg("Login successful to Indeed!")
            return

        # Check for error messages
        try:
            errors = driver.find_elements(By.CSS_SELECTOR,
                "[class*='error'], [class*='Error'], [role='alert']")
            for err in errors:
                if err.is_displayed() and err.text.strip():
                    print_lg(f"Indeed Login Error: {err.text.strip()}")
        except:
            pass

        print_lg("Indeed auto-login incomplete. Attempting manual login fallback.")
        screenshot(driver, "Indeed", "Login_Failed")
        manual_login_retry(is_logged_in_IN, 2)

    except Exception as e:
        print_lg("Error during Indeed login flow:", e)
        screenshot(driver, "Indeed", "Login_Exception")
        manual_login_retry(is_logged_in_IN, 2)


def _find_button(texts: list[str]) -> WebElement | None:
    """Find a visible, clickable button matching any of the given text labels."""
    for text in texts:
        selectors = [
            f"//button[normalize-space()='{text}']",
            f"//button[contains(normalize-space(), '{text}')]",
            f"//input[@type='submit' and contains(@value, '{text}')]",
            f"//a[normalize-space()='{text}']",
        ]
        for xp in selectors:
            try:
                btn = driver.find_element(By.XPATH, xp)
                if btn and btn.is_displayed():
                    return btn
            except:
                continue
    return None


# ---------------------------------------------------------------------------
# Search & Apply
# ---------------------------------------------------------------------------
def apply_to_jobs(end_time: float = None) -> None:
    global applied_count, failed_count, skip_count, dailyLimitReached, indeed_tab

    # 0. Switch to Indeed tab
    global indeed_tab
    try:
        if indeed_tab and indeed_tab in driver.window_handles:
            driver.switch_to.window(indeed_tab)
        elif driver.window_handles:
            indeed_tab = driver.window_handles[0]
            driver.switch_to.window(indeed_tab)
    except:
        pass

    # 1. Iterate through search terms
    for term in indeed_search_terms:
        if is_timeout(end_time):
            print_lg("Time limit reached for Indeed cycle. Rotating to next platform.")
            break
        try:
            print_lg(f"\n--- Searching for '{term}' on Indeed ---")

            # Build Indeed search URL (use in.indeed.com for India to avoid redirection quirks)
            base_url = "https://in.indeed.com" if (indeed_location and "india" in indeed_location.lower()) else "https://www.indeed.com"
            search_url = f"{base_url}/jobs?q={term.replace(' ', '+')}"
            if indeed_location:
                search_url += f"&l={indeed_location.replace(' ', '+')}"
            if indeed_date_posted:
                search_url += f"&fromage={indeed_date_posted}"
            if indeed_job_type:
                search_url += f"&jt={indeed_job_type}"
            if indeed_experience_level:
                search_url += f"&explvl={indeed_experience_level}"

            print_lg(f"Navigating to: {search_url}")
            robust_get(driver, search_url)
            sleep(3)
            close_modals()

            # Wait for job listings
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        ".job_seen_beacon, .jobsearch-ResultsList, #mosaic-jobResults, .resultContent, div[class*='cardOutline']"))
                )
                print_lg("Found Indeed job listings.")
            except TimeoutException:
                print_lg(f"Timed out waiting for Indeed listings for '{term}'. Checking page...")
                if "did not match any jobs" in driver.page_source.lower():
                    print_lg(f"No jobs found for '{term}' on Indeed.")
                    continue
                # Maybe anti-bot block
                if "unusual traffic" in driver.page_source.lower():
                    print_lg("Indeed detected unusual traffic. Pausing for manual CAPTCHA...")
                    manual_login_retry(is_logged_in_IN, 1)
                    continue

            # Application loop
            application_loop(term, end_time=end_time)

        except Exception as e:
            if "invalid session id" in str(e).lower():
                raise e
            print_lg(f"Error searching for '{term}' on Indeed: {e}")
            critical_error_log(f"Indeed search error: {term}", e)
            continue


def application_loop(term: str, end_time: float = None) -> int:
    """Process job cards on the current Indeed results page. Returns count of jobs processed."""
    global applied_count, failed_count, skip_count
    processed = 0
    page = 1

    try:
        while True:
            if is_timeout(end_time):
                print_lg("Time limit reached for Indeed application loop.")
                break
            print_lg(f"Processing Indeed results page {page}...")
            
            # Dismiss any popovers/modals
            try:
                actions.send_keys(Keys.ESCAPE).perform()
            except:
                pass
            close_modals()

            # Wait for at least one job card
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        ".job_seen_beacon, .resultContent, div[class*='cardOutline'], [data-testid='jobListing']"))
                )
            except:
                pass

            job_cards = driver.find_elements(By.CSS_SELECTOR,
                ".job_seen_beacon, .resultContent, .jobsearch-SerpJobCard, div[class*='cardOutline'], [data-testid='jobListing']")
            if not job_cards:
                job_cards = driver.find_elements(By.XPATH, "//div[contains(@class, 'job_seen_beacon')] | //td[contains(@class, 'resultContent')]")

            print_lg(f"Found {len(job_cards)} jobs on Indeed results page.")
            if not job_cards:
                break

            for index, card in enumerate(job_cards):
                if is_timeout(end_time):
                    print_lg("Time limit reached for Indeed application loop.")
                    return processed
                try:
                    # Keep screen awake
                    if keep_screen_awake:
                        try:
                            pyautogui.press('shiftright')
                        except:
                            pass

                    # Extract title and company
                    title = "Unknown"
                    company = "Unknown"

                    try:
                        title_el = card.find_element(By.CSS_SELECTOR,
                            "h2.jobTitle a, a[class*='jcs-JobTitle'], .jobTitle span, h2 a span, a[id*='job_']")
                        title = title_el.text.strip() or title_el.get_attribute("title") or "Unknown"
                    except:
                        try:
                            title_el = card.find_element(By.CSS_SELECTOR, "h2, .jobTitle")
                            title = title_el.text.strip()
                        except:
                            pass

                    try:
                        company_el = card.find_element(By.CSS_SELECTOR,
                            "[data-testid='company-name'], .companyName, span[class*='company']")
                        company = company_el.text.strip()
                    except:
                        pass

                    print_lg(f"[{index+1}/{len(job_cards)}] Processing: {title} at {company}")

                    # ── DOMAIN FILTER: skip non-tech jobs ──────────────
                    if not is_tech_job(title):
                        print_lg(f"[DOMAIN FILTER] Skipping non-tech job: '{title}'")
                        skip_count += 1
                        processed += 1
                        continue
                    # ──────────────────────────────────────────────────

                    # ── EXPERIENCE FILTER: strict 0-2 years gate ──────────
                    card_text = card.text
                    is_exp_ok, exp_reason = is_experience_eligible(title, snippet_text=card_text, max_allowed_exp=2)
                    if not is_exp_ok:
                        print_lg(f"[EXP FILTER] Skipping '{title}' at {company}: {exp_reason}")
                        skip_count += 1
                        processed += 1
                        continue
                    # ──────────────────────────────────────────────────────

                    # Check if already applied
                    try:
                        applied_text = card.text.lower()
                        if "applied" in applied_text:
                            print_lg("Already applied. Skipping.")
                            skip_count += 1
                            processed += 1
                            continue
                    except:
                        pass

                    close_modals()

                    # Click job card to load details in side panel or new page
                    try:
                        click_target = card.find_element(By.CSS_SELECTOR,
                            "h2.jobTitle a, a[class*='jcs-JobTitle'], h2 a, a[id*='job_']")
                        scroll_to_view(driver, click_target)
                        sleep(1)
                        try:
                            click_target.click()
                        except:
                            driver.execute_script("arguments[0].click();", click_target)
                    except:
                        scroll_to_view(driver, card)
                        try:
                            card.click()
                        except:
                            driver.execute_script("arguments[0].click();", card)

                    sleep(2)
                    close_modals()

                    # Handle the job detail (side panel or new tab)
                    handle_job_detail(title, company)
                    processed += 1

                    # Random delay between jobs for anti-bot
                    sleep(randint(2, 5))

                except StaleElementReferenceException:
                    print_lg(f"Stale element for job {index}. Moving to next.")
                    continue
                except Exception as e:
                    print_lg(f"Error processing Indeed listing {index}: {e}")
                    continue

            # Next page
            try:
                next_link = driver.find_element(By.CSS_SELECTOR,
                    "a[data-testid='pagination-page-next'], a[aria-label='Next Page'], nav a:last-child")
                if next_link and next_link.is_displayed():
                    scroll_to_view(driver, next_link)
                    driver.execute_script("arguments[0].click();", next_link)
                    sleep(3)
                    close_modals()
                    page += 1
                else:
                    break
            except:
                print_lg("No more Indeed result pages.")
                break

    except Exception as e:
        print_lg("Indeed application loop error:", e)

    return processed


def handle_job_detail(job_title: str, company_name: str):
    """Handle a single job: find Apply button, attempt Indeed Apply or note external."""
    global applied_count, failed_count, skip_count

    main_handle = driver.current_window_handle
    new_tab = False

    try:
        sleep(2)

        # Check for initial new tab
        current_handles = set(driver.window_handles)
        new_handles = current_handles - {main_handle}
        if new_handles:
            new_tab = True
            driver.switch_to.window(list(new_handles)[0])
            sleep(2)

        # Dismiss any popovers
        close_modals()

        # ── SECOND-LAYER EXPERIENCE & DOMAIN CHECK ──
        try:
            detail_body = driver.find_element(By.TAG_NAME, "body").text[:3000]
        except:
            detail_body = ""
        detail_context = f"{driver.current_url} {detail_body}"
        is_detail_exp_ok, detail_exp_reason = is_experience_eligible(job_title, snippet_text=detail_context, max_allowed_exp=2)
        if not is_detail_exp_ok:
            print_lg(f"[DETAIL EXP FILTER] Skipping '{job_title}': {detail_exp_reason}")
            skip_count += 1
            return

        if not is_tech_job(job_title, detail_body[:1000]):
            print_lg(f"[DETAIL DOMAIN FILTER] Skipping non-tech job: '{job_title}'")
            skip_count += 1
            return
        # ─────────────────────────────────────────────

        # --- Find Apply button ---
        apply_btn = _find_apply_button()

        if not apply_btn:
            # Try iframes if in side panel
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, frame in enumerate(iframes):
                try:
                    driver.switch_to.frame(frame)
                    apply_btn = _find_apply_button()
                    if apply_btn:
                        print_lg(f"Found Apply button in iframe #{i}")
                        break
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()

        if not apply_btn:
            try:
                driver.switch_to.default_content()
            except:
                pass
            print_lg(f"Apply button not found for '{job_title}'. Skipping.")
            skip_count += 1
            return

        # --- Check button text / nature ---
        btn_text = apply_btn.text.strip().lower()
        btn_href = apply_btn.get_attribute("href") or ""
        print_lg(f"Found Apply button: '{apply_btn.text.strip()}' (tag: {apply_btn.tag_name}, href: {btn_href[:60]})")

        try:
            driver.switch_to.default_content()
        except:
            pass

        # Check if it's an external apply
        if "company site" in btn_text or "apply on" in btn_text or ("smartapply" not in btn_href and "indeedapply" not in btn_href and "http" in btn_href and "indeed.com" not in btn_href):
            print_lg(f"External apply for '{job_title}' at {company_name}. Recording external link.")
            try:
                driver.execute_script("arguments[0].click();", apply_btn)
            except:
                apply_btn.click()
            sleep(2)
            skip_count += 1
            save_submitted_job(
                job_id=job_title, title=job_title, company=company_name,
                job_link=driver.current_url, application_link="Indeed External Apply"
            )
            return

        # Indeed Apply (in-platform)
        handles_before = list(driver.window_handles)
        try:
            driver.execute_script("arguments[0].click();", apply_btn)
        except:
            apply_btn.click()
        sleep(4)

        handles_after = list(driver.window_handles)
        unseen_handles = [h for h in handles_after if h not in handles_before]
        if unseen_handles:
            new_tab = True
            driver.switch_to.window(unseen_handles[-1])
            sleep(3)

        # Check if auth/login page opened
        current_url = driver.current_url.lower()
        if "secure.indeed.com/auth" in current_url or "account/login" in current_url:
            print_lg("Indeed requested authentication before applying. Attempting login...")
            if not is_logged_in_IN():
                login_IN()
            if not is_logged_in_IN():
                print_lg("Login required to complete Indeed application. Skipping this job.")
                skip_count += 1
                return

        # Handle Indeed Apply multi-step form
        fill_indeed_apply_form(job_title, company_name)

    except Exception as e:
        print_lg(f"Failed to apply on Indeed for '{job_title}': {e}")
        failed_count += 1
        try:
            save_failed_job(
                job_id=job_title, job_link=driver.current_url,
                error_reason="Indeed apply failure", exception=e
            )
        except:
            pass
    finally:
        try:
            driver.switch_to.default_content()
        except:
            pass
        try:
            # Safely close any newly opened detail tab/popup without touching main_handle
            current_handles = list(driver.window_handles)
            for h in current_handles:
                if h != main_handle and len(driver.window_handles) > 1:
                    driver.switch_to.window(h)
                    driver.close()
        except:
            pass
        try:
            if main_handle in driver.window_handles:
                driver.switch_to.window(main_handle)
            elif driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        except:
            pass


def _find_apply_button() -> WebElement | None:
    """Find the Apply button in the job detail pane or current page."""
    # First, look inside the job detail pane
    pane = None
    pane_selectors = [
        "#jobsearch-ViewjobPaneWrapper",
        "#viewJobSSRRoot",
        ".jobsearch-RightPane",
        "[data-testid='jobsearch-ViewjobPaneWrapper']",
        ".jobsearch-JobComponent",
    ]
    for ps in pane_selectors:
        try:
            p = driver.find_element(By.CSS_SELECTOR, ps)
            if p and p.is_displayed():
                pane = p
                break
        except:
            continue

    containers = [pane] if pane else []
    containers.append(driver)  # fallback to entire driver

    for root in containers:
        apply_selectors = [
            (By.CSS_SELECTOR, "a[href*='smartapply'], a[href*='indeedapply']"),
            (By.CSS_SELECTOR, "#indeedApplyButton, button[id*='indeedApply']"),
            (By.CSS_SELECTOR, ".jobsearch-IndeedApplyButton-newDesign"),
            (By.XPATH, ".//a[contains(@href, 'indeedapply') or contains(@href, 'smartapply')]"),
            (By.XPATH, ".//button[contains(@id, 'indeedApply') or contains(@class, 'indeed-apply')]"),
            (By.XPATH, ".//*[normalize-space(text())='Apply now']/ancestor-or-self::a"),
            (By.XPATH, ".//*[normalize-space(text())='Apply now']/ancestor-or-self::button"),
            (By.XPATH, ".//button[normalize-space()='Apply now']"),
            (By.XPATH, ".//a[normalize-space()='Apply now']"),
            (By.XPATH, ".//*[normalize-space(text())='Apply on company site']/ancestor-or-self::a"),
            (By.XPATH, ".//*[normalize-space(text())='Apply on company site']/ancestor-or-self::button"),
            (By.XPATH, ".//button[contains(normalize-space(), 'Apply now')]"),
            (By.XPATH, ".//a[contains(normalize-space(), 'Apply now')]"),
            (By.XPATH, ".//a[contains(normalize-space(), 'Apply on company site')]"),
            (By.XPATH, ".//button[contains(normalize-space(), 'Apply on company site')]"),
        ]
        for by, sel in apply_selectors:
            try:
                elements = root.find_elements(by, sel)
                for btn in elements:
                    if btn.is_displayed():
                        # Exclude navigation / filter buttons
                        btn_id = (btn.get_attribute("id") or "").lower()
                        btn_class = (btn.get_attribute("class") or "").lower()
                        if "filter" in btn_id or "filter" in btn_class or "pill" in btn_class:
                            continue
                        return btn
            except:
                continue

    return None


def fill_indeed_apply_form(job_title: str, company_name: str):
    """
    Handle Indeed's multi-step apply modal.
    Steps typically: Contact Info → Resume → Questions → Review → Submit
    """
    global applied_count, failed_count, skip_count

    max_steps = 10  # safety limit
    step = 0

    while step < max_steps:
        step += 1
        sleep(2)

        # Check if we landed on a success page
        try:
            page_text = driver.page_source.lower()
            if any(s in page_text for s in [
                "application submitted", "your application has been submitted",
                "you have applied", "application sent", "successfully applied"
            ]):
                print_lg(f"SUCCESS: Applied to '{job_title}' at {company_name} on Indeed.")
                screenshot(driver, "Indeed", f"Applied_Success_{job_title[:15]}")
                applied_count += 1
                save_submitted_job(
                    job_id=job_title, title=job_title, company=company_name,
                    job_link=driver.current_url, application_link="Indeed Applied"
                )
                return
        except:
            pass

        # Switch to iframe if Indeed Apply opens in one
        try:
            iframe = driver.find_element(By.CSS_SELECTOR,
                "iframe[title*='Apply'], iframe[id*='indeedapply'], iframe[name*='indeedapply']")
            driver.switch_to.frame(iframe)
            sleep(1)
        except:
            pass  # Not in iframe, that's fine

        # --- Fill form fields on current step ---
        _fill_current_step_fields(job_title)

        # --- Try to click Continue / Next / Submit / Apply / Review ---
        submit_btn = None
        candidate_selectors = [
            "button[data-testid*='continue']",
            "button[data-testid*='submit']",
            "button[data-testid*='review']",
            "button.ia-continueButton",
            "[data-testid='continue-button']",
            "//button[contains(normalize-space(), 'Submit your application')]",
            "//button[contains(normalize-space(), 'Submit application')]",
            "//button[contains(normalize-space(), 'Review your application')]",
            "//button[contains(., 'Continue')]",
            "//button[contains(., 'Submit')]",
            "//button[contains(., 'Review')]",
            "//button[contains(., 'Next')]",
            "//button[contains(., 'Apply')]",
            "button[type='submit']",
            "input[type='submit']",
            "//a[contains(., 'Continue')]",
        ]
        for sel in candidate_selectors:
            try:
                if sel.startswith("//"):
                    btns = driver.find_elements(By.XPATH, sel)
                else:
                    btns = driver.find_elements(By.CSS_SELECTOR, sel)
                for b in btns:
                    if b.is_displayed():
                        # Wait up to 5s if disabled (e.g. file upload finalizing)
                        for _ in range(5):
                            is_disabled = "disabled" in (b.get_attribute("class") or "").lower() or b.get_attribute("disabled") or not b.is_enabled()
                            if not is_disabled:
                                submit_btn = b
                                break
                            sleep(1)
                        if submit_btn:
                            break
                if submit_btn:
                    break
            except:
                continue

        if submit_btn:
            btn_label = submit_btn.text.strip()
            print_lg(f"Indeed Apply step {step}: clicking '{btn_label}'")
            try:
                scroll_to_view(driver, submit_btn)
                driver.execute_script("arguments[0].click();", submit_btn)
            except:
                try:
                    submit_btn.click()
                except:
                    pass
            sleep(3)

            # If we clicked "Submit" variant, check for success
            if any(s in btn_label.lower() for s in ["submit", "apply"]):
                sleep(3)
                try:
                    page_text = driver.page_source.lower()
                    if any(s in page_text for s in [
                        "application submitted", "your application has been submitted",
                        "you have applied", "application sent"
                    ]):
                        print_lg(f"SUCCESS: Applied to '{job_title}' at {company_name} on Indeed.")
                        screenshot(driver, "Indeed", f"Applied_Success_{job_title[:15]}")
                        applied_count += 1
                        save_submitted_job(
                            job_id=job_title, title=job_title, company=company_name,
                            job_link=driver.current_url, application_link="Indeed Applied"
                        )
                        try:
                            driver.switch_to.default_content()
                        except:
                            pass
                        return
                except:
                    pass
        else:
            print_lg(f"Indeed Apply step {step}: no Continue/Submit button found.")
            if not prompt_user_if_stuck(driver, job_title, "Indeed form step requires attention or manual action in browser", timeout_seconds=60):
                print_lg(f"Skipping '{job_title}' on Indeed due to 1-minute timeout or user skip.")
                skip_count += 1
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                return
            break

    # If we get here and reached the end of steps
    screenshot(driver, "Indeed", f"Applied_Final_{job_title[:15]}")
    print_lg(f"Indeed Apply form completed {step} steps for '{job_title}'. Marking as applied.")
    applied_count += 1
    save_submitted_job(
        job_id=job_title, title=job_title, company=company_name,
        job_link=driver.current_url, application_link="Indeed Applied"
    )
    try:
        driver.switch_to.default_content()
    except:
        pass


def _fill_current_step_fields(job_title: str = ""):
    """Fill form fields visible on the current Indeed Apply step using Gemini AI and profile heuristics."""
    global aiClient
    try:
        # Ensure aiClient is active
        if not aiClient and use_AI and ai_provider == "gemini":
            try:
                from modules.ai.geminiConnections import gemini_create_client
                aiClient = gemini_create_client()
            except Exception as e:
                print_lg(f"Could not initialize Gemini for Indeed: {e}")

        # Intelligently fill all elements (name, email, phone, location, resume, textareas with Gemini, radios, selects)
        auto_fill_form_elements(driver, job_title=job_title, company="", ai_client=aiClient)

        # --- Name fields ---
        _try_fill_input(["input[name*='name' i]", "input[id*='name' i]",
                         "input[autocomplete='name']"], f"{first_name} {last_name}")
        _try_fill_input(["input[name*='firstName' i]", "input[id*='firstName' i]",
                         "input[autocomplete='given-name']"], first_name)
        _try_fill_input(["input[name*='lastName' i]", "input[id*='lastName' i]",
                         "input[autocomplete='family-name']"], last_name)

        # --- Email ---
        _try_fill_input(["input[type='email']", "input[name*='email' i]",
                         "input[id*='email' i]", "input[autocomplete='email']"],
                        getattr(config.secrets, 'indeed_username', '') or username)

        # --- Phone ---
        _try_fill_input(["input[type='tel']", "input[name*='phone' i]",
                         "input[id*='phone' i]", "input[autocomplete='tel']"],
                        phone_number)

        # --- City / Location ---
        _try_fill_input(["input[name*='location' i]", "input[name*='city' i]",
                         "input[id*='city' i]", "input[autocomplete='address-level2']"],
                        current_city or indeed_location)

        # --- Resume selection or upload ---
        try:
            resume_radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio'][name*='resume' i]")
            if resume_radios and not any(r.is_selected() for r in resume_radios):
                driver.execute_script("arguments[0].click();", resume_radios[0])
        except:
            pass

        try:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for fi in file_inputs:
                if is_resume_file_input(driver, fi):
                    resume_path = os.path.abspath(default_resume_path) if default_resume_path else ""
                    if resume_path and os.path.isfile(resume_path):
                        fi.send_keys(resume_path)
                        print_lg(f"Uploaded resume on Indeed: {resume_path}")
                        sleep(2)
                        break
                else:
                    print_lg("[Indeed] Skipping non-resume file input.")
        except:
            pass

        # --- Experience / Years inputs ---
        _try_fill_input(["input[name*='experience' i]", "input[name*='years' i]"],
                        years_of_experience)

    except Exception as e:
        print_lg(f"Error filling Indeed form fields: {e}")


def _try_fill_input(selectors: list[str], value: str):
    """Try to fill an input field using multiple CSS selectors. Only fills if the field is empty."""
    if not value:
        return
    for sel in selectors:
        try:
            fields = driver.find_elements(By.CSS_SELECTOR, sel)
            for field in fields:
                if field.is_displayed() and field.is_enabled():
                    current_val = field.get_attribute("value") or ""
                    if not current_val.strip():
                        field.clear()
                        field.send_keys(value)
                        return
        except:
            continue


def _try_fill_textarea(selectors: list[str], value: str):
    """Try to fill a textarea using multiple CSS selectors. Only fills if empty."""
    if not value:
        return
    for sel in selectors:
        try:
            fields = driver.find_elements(By.CSS_SELECTOR, sel)
            for field in fields:
                if field.is_displayed() and field.is_enabled():
                    current_val = field.get_attribute("value") or field.text or ""
                    if not current_val.strip():
                        field.clear()
                        field.send_keys(value)
                        return
        except:
            continue
