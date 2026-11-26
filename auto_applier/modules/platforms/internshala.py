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
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException, NoSuchWindowException, WebDriverException

import config.secrets
from config.secrets import use_AI, username, password, ai_provider
from config.search import *
from config.settings import *
from config.personals import *
from config.questions import *

from modules.helpers import buffer, print_lg, sleep, manual_login_retry, truncate_for_csv, calculate_date_posted, critical_error_log, robust_get, screenshot, is_timeout
from modules.domain_filter import is_tech_job, is_experience_eligible
from modules.question_solver import auto_fill_form_elements, prompt_user_if_stuck, is_resume_file_input
from modules.clickers_and_finders import try_linkText, try_xp, text_input_by_ID, find_by_class, wait_span_click, multi_sel_noWait, boolean_button_click, try_find_by_classes, scroll_to_view
from modules.history import save_submitted_job, save_failed_job

if use_AI:
    from modules.ai.openaiConnections import ai_answer_question
    from modules.ai.geminiConnections import gemini_answer_question

try:
    import pyautogui
except:
    pass

# AI integration helper (copied/adapted from LinkedIn logic or shared AI modules if they existed)
# For now, we'll assume we can use the main script's AI logic or implement a basic one here
# Actually, runAiBot.py has ai_answer_question, gemini_answer_question etc.
# I will need to ensure these are accessible or re-implement for Internshala context.

# To be set by the main caller
driver: WebDriver = None
wait: WebDriverWait = None
actions = None
aiClient = None

# Global counters/flags for Internshala
applied_count = 0
failed_count = 0
skip_count = 0
dailyLimitReached = False
internshala_tab = None

def init_internshala(drv, wt, act, ai_clnt):
    global driver, wait, actions, aiClient, internshala_tab
    driver = drv
    wait = wt
    actions = act
    aiClient = ai_clnt
    internshala_tab = driver.current_window_handle

def is_logged_in_IS() -> bool:
    '''
    Function to check if user is logged-in in Internshala
    '''
    global driver
    if not driver: return False
    try:
        # Check URL as the most reliable indicator
        current_url = driver.current_url.lower()
        if "/dashboard" in current_url or "/my_applications" in current_url or "/student/results" in current_url:
            return True

        # Check for elements that ONLY exist when logged in
        if try_xp(driver, "//li[@id='profile_container_hover']"): return True # Active Profile Dropdown
        if try_xp(driver, "//a[contains(@href, '/dashboard')]") or try_xp(driver, "//a[contains(@href, '/my_applications')]"): return True
        if try_linkText(driver, "Log out") or try_linkText(driver, "Logout"): return True
        if try_linkText(driver, "My applications") or try_linkText(driver, "Dashboard"): return True
        if try_xp(driver, "//a[contains(@href, 'internshala.com/student/dashboard')]"): return True
        
        # Check for user name or initials which usually appear in the top right
        if try_xp(driver, "//div[contains(@class, 'profile_name')]"): return True
        if try_xp(driver, "//div[contains(@class, 'nav-profile')]"): return True

        # Check if "Login / Register" is still there (indicates NOT logged in)
        if try_xp(driver, "//li[contains(., 'Login / Register')]"): return False
        if try_xp(driver, "//li[contains(., 'Login')]"): return False
        
        return False
    except:
        return False

def close_modals(driver):
    '''
    Try to close any overlaying modals that might block interaction
    '''
    try:
        # Aggressive JavaScript-based clearing (Brute-force)
        driver.execute_script("""
            var backdrops = document.querySelectorAll('.modal-backdrop');
            for(var i=0; i<backdrops.length; i++) { backdrops[i].remove(); }
            var modals = document.querySelectorAll('.modal.in, .modal.show, #login-modal, #sign-up-modal');
            for(var i=0; i<modals.length; i++) { 
                modals[i].style.display = 'none'; 
                modals[i].classList.remove('in', 'show');
            }
            document.body.classList.remove('modal-open');
        """)
        
        # Selenium-based closing for known close buttons
        close_selectors = [
            "//i[@id='close_pwa_popup']",
            "//button[contains(@class, 'close')]",
            "//div[contains(@class, 'close')]",
            "//i[contains(@class, 'close')]",
            "//span[contains(@class, 'close')]",
            "//div[@id='close_popup']",
            "//*[@data-dismiss='modal']",
            "//i[contains(@class, 'ic-24-cross')]"
        ]
        for sel in close_selectors:
            try:
                btns = driver.find_elements(By.XPATH, sel)
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
            except: continue
    except: pass

def login_IS() -> None:
    '''
    Function to login for Internshala
    '''
    if not driver:
        print_lg("Error: Internshala driver not initialized!")
        return

    robust_get(driver, "https://internshala.com")
    
    if is_logged_in_IS():
        print_lg("Already logged in to Internshala.")
        return

    # Use platform-specific credentials if available
    is_username = getattr(config.secrets, 'internshala_username', username)
    is_password = getattr(config.secrets, 'internshala_password', password)
    
    if not is_username or not is_password:
        print_lg("Error: Internshala credentials not found in secrets.py!")
        return

    try:
        # Direct login page attempt
        robust_get(driver, "https://internshala.com/login")
        sleep(2)
        close_modals(driver)
        
        if is_logged_in_IS():
            print_lg("Login successful via direct URL.")
            return

        # 1. Ensure "Student" tab is selected
        student_selectors = [
            "//a[contains(text(), 'Student')]",
            "//li[contains(@class, 'student_login')]/a",
            "//a[@id='student-login-tab']"
        ]
        for sel in student_selectors:
            try:
                student_tab = driver.find_element(By.XPATH, sel)
                if "active" not in student_tab.get_attribute("class"):
                    print_lg(f"Selecting Student tab using: {sel}")
                    student_tab.click()
                    sleep(1)
                    break
            except: continue

        # 2. Fill credentials
        email_selectors = ["email", "modal_email", "modal_login_email"]
        email_field = None
        for sel in email_selectors:
            try:
                email_field = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, sel)))
                if email_field: break
            except: continue
            
        if email_field:
            password_selectors = ["password", "modal_password", "modal_login_password"]
            password_field = None
            for sel in password_selectors:
                try:
                    password_field = driver.find_element(By.ID, sel)
                    if password_field: break
                except: continue
            
            if password_field:
                from modules.helpers import type_human_like
                type_human_like(email_field, is_username)
                
                type_human_like(password_field, is_password)
                
                submit_selectors = ["login_submit", "modal_login_submit"]
                submit_btn = None
                for sel in submit_selectors:
                    try:
                        submit_btn = driver.find_element(By.ID, sel)
                        if submit_btn: break
                    except: continue
                
                if submit_btn:
                    try:
                        submit_btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", submit_btn)
                    print_lg("Clicked Internshala login submit button.")
                
                # Check for immediate success or specific error modals
                sleep(2)
                if is_logged_in_IS():
                    print_lg("Login successful to Internshala!")
                    return

                # Error modal check
                try:
                    error_modal = driver.find_element(By.CLASS_NAME, "modal-content")
                    if error_modal.is_displayed():
                        error_text = error_modal.text.strip().replace('\n', ' ')
                        if "captcha" in error_text.lower():
                            print_lg("⚠️ CAPTCHA detected. Please solve it in the browser.")
                            manual_login_retry(is_logged_in_IS, 1)
                            if is_logged_in_IS(): return
                        elif "TypeError" in error_text or "validationError" in error_text:
                            print_lg("Internal page error in modal, ignoring...")
                        else:
                            print_lg(f"❌ Login error: {error_text}")
                        close_modals(driver)
                except: pass

        # 3. Success loop (wait for redirect)
        for _ in range(5):
            if is_logged_in_IS():
                print_lg("Login successful to Internshala!")
                return
            sleep(2)

        # 4. Fallback for dynamic login button flow (Homepage modal)
        if not is_logged_in_IS():
            print_lg("Direct login failed, trying homepage modal flow...")
            robust_get(driver, "https://internshala.com")
            close_modals(driver)
            
            login_btn_selectors = [
                "//button[contains(normalize-space(), 'Login')]",
                "//a[contains(normalize-space(), 'Login')]",
                "//span[contains(normalize-space(), 'Login')]"
            ]
            login_btn = None
            for xpath in login_btn_selectors:
                try:
                    if not driver: break
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed():
                            login_btn = btn
                            driver.execute_script("arguments[0].click();", login_btn)
                            sleep(2)
                            break
                    if login_btn: break
                except: continue

            if login_btn:
                try:
                    driver.find_element(By.ID, "modal_email").send_keys(is_username)
                    driver.find_element(By.ID, "modal_password").send_keys(is_password)
                    driver.find_element(By.ID, "modal_login_submit").click()
                    sleep(3)
                except: pass
                if is_logged_in_IS():
                    print_lg("Login verified via modal flow.")
                    return

        # 5. Desperate Manual Fallback
        if not is_logged_in_IS():
            print_lg("Internshala auto-login failed. Attempting manual login fallback.")
            manual_login_retry(is_logged_in_IS, 1)
            
    except Exception as e:
        print_lg(f"Critical error during Internshala login: {e}")
        try:
            screenshot(driver, "Internshala", "Login_Failed")
        except: pass
        manual_login_retry(is_logged_in_IS, 1)

INTERNSHALA_SLUG_MAP = {
    "python developer": "python",
    "python": "python",
    "python django": "python-django",
    "software developer": "software-development",
    "software engineer": "software-development",
    "software development": "software-development",
    "ai engineer": "artificial-intelligence",
    "ai developer": "artificial-intelligence",
    "artificial intelligence": "artificial-intelligence",
    "backend developer": "backend-development",
    "backend engineer": "backend-development",
    "data scientist": "data-science",
    "data science": "data-science",
    "machine learning engineer": "machine-learning",
    "machine learning": "machine-learning",
    "web developer": "web-development",
    "full stack developer": "full-stack-development",
}

def build_internshala_url(category=None):
    '''
    Build an Internshala search URL for a given category with filters baked in.
    Supports URL-based filtering, e.g.:
      /jobs/python-jobs?min_exp=0&max_exp=2
      /jobs/software-development-jobs?min_exp=0&max_exp=2
    Experience filter appended as query params: ?min_exp=0&max_exp=2 (for 0-2 yrs)
    '''
    base = f"https://internshala.com/{internshala_listing_type}"

    # Use provided category or fall back to first configured category
    chosen_category = category or (internshala_categories[0] if internshala_categories else "")
    if chosen_category:
        norm_cat = chosen_category.lower().replace("-", " ").replace("(", "").replace(")", "").strip()
        slug = INTERNSHALA_SLUG_MAP.get(norm_cat)
        if not slug:
            sub_cat = norm_cat.replace(" developer", "").replace(" engineer", "").strip()
            slug = INTERNSHALA_SLUG_MAP.get(sub_cat, norm_cat.replace(" ", "-"))

        if internshala_listing_type == "jobs":
            base += f"/{slug}-jobs"
        else:
            base += f"/{slug}-internship"

    # Add location slug into the URL path
    if internshala_location:
        loc_slug = internshala_location.lower().replace(" ", "-")
        base += f"-in-{loc_slug}"

    # Work-from-home filter as an extra path segment
    if internshala_work_from_home:
        base += "/work-from-home"

    # Build query params
    query_parts = []

    # Experience filter (0-2 years for junior/fresher roles)
    min_exp = globals().get("internshala_min_exp", 0)
    max_exp = globals().get("internshala_max_exp", 2)
    if internshala_listing_type == "jobs":
        query_parts.append(f"min_exp={min_exp}&max_exp={max_exp}")

    if query_parts:
        base += "?" + "&".join(query_parts)

    return base

def set_filters():
    '''
    Apply search filters on Internshala using URL-based navigation.
    Internshala's filter UI uses mobile-style pills that are unreliable to automate.
    Instead, we construct the filtered URL directly.
    '''
    global driver
    if not driver: return
    print_lg("Filters are applied via URL on Internshala (URL-based filtering).")

def apply_to_jobs(end_time: float = None) -> None:
    '''
    Main loop for Internshala job applications.
    Iterates over every configured category with URL-based filtering.
    '''
    global applied_count, failed_count, skip_count, dailyLimitReached, internshala_tab

    # 0. Switch to Internshala tab
    global internshala_tab
    try:
        if internshala_tab and internshala_tab in driver.window_handles:
            driver.switch_to.window(internshala_tab)
        elif driver.window_handles:
            internshala_tab = driver.window_handles[0]
            driver.switch_to.window(internshala_tab)
    except:
        pass

    # Iterate over ALL configured categories
    categories = internshala_categories if internshala_categories else [""]
    for category in categories:
        if is_timeout(end_time):
            print_lg("Time limit reached for Internshala cycle. Stopping.")
            break

        url = build_internshala_url(category=category)
        print_lg(f"\n--- Searching Internshala: '{category}' ---")
        print_lg(f"Navigating to: {url}")
        robust_get(driver, url)
        sleep(3)
        close_modals(driver)

        try:
            print_lg(f"Waiting for listings on Internshala ({internshala_listing_type}) ...")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "individual_internship"))
                )
                print_lg("Found listings. Starting application loop.")
            except:
                print_lg(f"No listings found (page timed out) for '{category}'. Skipping.")
                continue

            while True:  # Pagination loop
                if is_timeout(end_time):
                    print_lg("Time limit reached for Internshala application loop.")
                    break

                # Re-fetch listings — skip promoted/ad entries
                job_elements = []
                try:
                    all_listings = driver.find_elements(By.CLASS_NAME, "individual_internship")
                    for listing in all_listings:
                        try:
                            listing_text = listing.text
                            listing_html = listing.get_attribute("innerHTML") or ""
                            if "Promoted" in listing_text or "trainings.internshala.com" in listing_html:
                                continue
                            # Only include listings with a proper job/internship detail link
                            links = listing.find_elements(By.TAG_NAME, "a")
                            has_job_link = any(
                                pat in (link.get_attribute("href") or "")
                                for link in links
                                for pat in ["/job-detail/", "/internship-detail/",
                                            "/job/detail/", "/internship/detail/"]
                            )
                            if has_job_link:
                                job_elements.append(listing)
                            else:
                                # Accept if any internshala.com link exists (non-training)
                                for link in links:
                                    href = link.get_attribute("href") or ""
                                    if "internshala.com" in href and "trainings" not in href:
                                        job_elements.append(listing)
                                        break
                        except:
                            job_elements.append(listing)
                except:
                    pass

                print_lg(f"Found {len(job_elements)} actual job listings (ads skipped).")
                if not job_elements:
                    print_lg("No listings on this page.")
                    break

                main_handle = driver.current_window_handle

                for index, job in enumerate(job_elements):
                    if is_timeout(end_time):
                        break
                    try:
                        # Keep screen awake
                        try:
                            if keep_screen_awake:
                                pyautogui.press('shiftright')
                        except:
                            pass

                        from selenium.common.exceptions import StaleElementReferenceException

                        # Extract title
                        title = ""
                        for ts in ["h3.job-internship-name a", ".job-title-href", ".profile",
                                   "h3 a", "a.job-title-href", ".heading_4_5"]:
                            try:
                                els = job.find_elements(By.CSS_SELECTOR, ts)
                                if els and els[0].text.strip():
                                    title = els[0].text.strip()
                                    break
                            except:
                                continue

                        # Extract company
                        company = ""
                        for cs in [".company-name", ".link_display_like_text",
                                   "p.company-name", ".ic-16-building + span"]:
                            try:
                                els = job.find_elements(By.CSS_SELECTOR, cs)
                                if els and els[0].text.strip():
                                    company = els[0].text.strip()
                                    break
                            except:
                                continue

                        if not title:
                            title = f"Job {index}"
                        if not company:
                            company = "Unknown"

                        print_lg(f"Processing: {title} at {company}")

                        # ── DOMAIN & EXPERIENCE FILTER: 0-2 yrs tech only ──
                        if not is_tech_job(title):
                            print_lg(f"[DOMAIN FILTER] Skipping non-tech job: '{title}'")
                            skip_count += 1
                            continue

                        is_exp_ok, exp_reason = is_experience_eligible(title, snippet_text=job.text, max_allowed_exp=2)
                        if not is_exp_ok:
                            print_lg(f"[EXP FILTER] Skipping '{title}' at {company}: {exp_reason}")
                            skip_count += 1
                            continue
                        # ──────────────────────────────────────────────────

                        # Already applied?
                        try:
                            if "Applied" in job.text:
                                print_lg("Already applied. Skipping.")
                                skip_count += 1
                                continue
                        except StaleElementReferenceException:
                            continue

                        close_modals(driver)

                        # Find job detail link — Internshala uses /job-detail/ or /internship-detail/
                        job_link = None
                        try:
                            all_links = job.find_elements(By.TAG_NAME, "a")
                            for link in all_links:
                                href = link.get_attribute("href") or ""
                                if any(pat in href for pat in ["/job-detail/", "/internship-detail/",
                                                                "/job/detail/", "/internship/detail/"]):
                                    job_link = href
                                    break
                        except:
                            pass

                        if not job_link:
                            # Fallback: grab first internshala.com link that isn't training
                            try:
                                all_links = job.find_elements(By.TAG_NAME, "a")
                                for link in all_links:
                                    href = link.get_attribute("href") or ""
                                    if "internshala.com" in href and "trainings" not in href:
                                        job_link = href
                                        break
                            except:
                                pass

                        if not job_link:
                            print_lg(f"No clickable link found for '{title}'. Skipping.")
                            failed_count += 1
                            save_failed_job(job_id=title, job_link="unknown", error_reason="No job link found")
                            continue

                        if "trainings.internshala.com" in job_link:
                            print_lg(f"Skipping training/promoted link for '{title}'.")
                            skip_count += 1
                            continue

                        # Open the job detail page in a new tab using native new_window (immune to popup blocking)
                        tab_opened = False
                        try:
                            driver.switch_to.new_window('tab')
                            robust_get(driver, job_link)
                            tab_opened = True
                        except Exception as e:
                            print_lg(f"new_window tab open failed: {e}, attempting window.open...")
                            driver.execute_script(f"window.open('{job_link}', '_blank');")
                            sleep(2)
                            if len(driver.window_handles) > 1:
                                driver.switch_to.window(driver.window_handles[-1])
                                tab_opened = True

                        if not tab_opened or driver.current_window_handle == main_handle:
                            # Fallback: navigate directly in current tab
                            print_lg("Multi-tab navigation unavailable, navigating directly in current tab...")
                            robust_get(driver, job_link)

                        close_modals(driver)
                        sleep(1)

                        # Verify we're not redirected to trainings
                        if "trainings.internshala.com" in driver.current_url:
                            print_lg(f"Redirected to trainings page. Skipping '{title}'.")
                            if driver.current_window_handle != main_handle and len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(main_handle)
                            else:
                                robust_get(driver, url)
                            continue

                        # ── SECOND-LAYER EXPERIENCE & DOMAIN CHECK (detail page + URL) ──
                        try:
                            detail_body = driver.find_element(By.TAG_NAME, "body").text[:3000]
                        except:
                            detail_body = ""
                        detail_context = f"{driver.current_url} {detail_body}"
                        is_detail_exp_ok, detail_exp_reason = is_experience_eligible(title, snippet_text=detail_context, max_allowed_exp=2)
                        if not is_detail_exp_ok:
                            print_lg(f"[DETAIL EXP FILTER] Skipping '{title}': {detail_exp_reason}")
                            skip_count += 1
                            if driver.current_window_handle != main_handle and len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(main_handle)
                            else:
                                robust_get(driver, url)
                            continue

                        if not is_tech_job(title, detail_body[:1000]):
                            print_lg(f"[DETAIL DOMAIN FILTER] Skipping non-tech job: '{title}'")
                            skip_count += 1
                            if driver.current_window_handle != main_handle and len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(main_handle)
                            else:
                                robust_get(driver, url)
                            continue
                        # ─────────────────────────────────────────────────────────────────

                        # Find Apply button on detail page
                        apply_btn = None
                        apply_selectors = [
                            (By.ID, "continue_button"),
                            (By.CSS_SELECTOR, "#continue_button"),
                            (By.CSS_SELECTOR, ".apply_now_btn"),
                            (By.CSS_SELECTOR, ".apply_now_button"),
                            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply now')]"),
                            (By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply now')]"),
                            (By.XPATH, "//button[contains(text(), 'Apply now') or contains(text(), 'Apply Now')]"),
                            (By.XPATH, "//a[contains(text(), 'Apply now') or contains(text(), 'Apply Now')]"),
                            (By.CSS_SELECTOR, "a.btn.apply_button"),
                            (By.CSS_SELECTOR, ".easy_apply_button"),
                            (By.XPATH, "//button[contains(@class, 'apply')]"),
                            (By.XPATH, "//a[contains(@class, 'apply')]"),
                            (By.XPATH, "//div[contains(@id, 'apply')]//button"),
                            (By.XPATH, "//div[contains(@id, 'apply')]//a"),
                        ]

                        for by, sel in apply_selectors:
                            try:
                                elems = driver.find_elements(by, sel)
                                for el in elems:
                                    if el.is_displayed():
                                        apply_btn = el
                                        print_lg(f"  Found Apply button: text='{el.text.strip()}' using selector '{sel}'")
                                        break
                                if apply_btn:
                                    break
                            except:
                                continue

                        if apply_btn:
                            scroll_to_view(driver, apply_btn)
                            try:
                                apply_btn.click()
                            except:
                                driver.execute_script("arguments[0].click();", apply_btn)
                            sleep(3)

                            # Check if we got redirected to resume page
                            if "resume" in driver.current_url.lower() or "your internshala resume" in driver.page_source.lower():
                                print_lg(f"  ⚠️ Resume creation page detected. Attempting to handle...")

                                # Strategy 1: Close resume modal overlay
                                modal_closed = False
                                close_selectors = [
                                    "//button[contains(@class, 'close')]",
                                    "//span[contains(@class, 'close')]",
                                    "//*[@data-dismiss='modal']",
                                    "//i[contains(@class, 'close')]",
                                    "//div[contains(@class, 'modal')]//button[contains(@class, 'close')]",
                                    "//i[contains(@class, 'ic-24-cross')]",
                                ]
                                for sel in close_selectors:
                                    try:
                                        close_btn = driver.find_element(By.XPATH, sel)
                                        if close_btn.is_displayed():
                                            driver.execute_script("arguments[0].click();", close_btn)
                                            sleep(1)
                                            modal_closed = True
                                            print_lg("  Closed resume modal overlay.")
                                            break
                                    except:
                                        continue

                                if not modal_closed:
                                    close_modals(driver)
                                    modal_closed = True

                                # Strategy 2: Try to upload resume if configured
                                try:
                                    from config.settings import generated_resume_path
                                    resume_path = generated_resume_path.strip() if generated_resume_path else ""
                                    resume_files = []
                                    if resume_path:
                                        if os.path.isfile(resume_path):
                                            resume_files = [resume_path]
                                        elif os.path.isdir(resume_path):
                                            for f in os.listdir(resume_path):
                                                if f.lower().endswith(('.pdf', '.doc', '.docx')):
                                                    resume_files.append(os.path.join(resume_path, f))

                                    if resume_files:
                                        filtered = [r for r in resume_files if not any(
                                            x in r.lower() for x in ["manual", "guide", "form", "format"]
                                        )]
                                        resume_to_upload = filtered[0] if filtered else resume_files[0]
                                        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                                        for fi in file_inputs:
                                            if is_resume_file_input(driver, fi):
                                                fi.send_keys(resume_to_upload)
                                                print_lg(f"  Uploaded resume to verified input: {os.path.basename(resume_to_upload)}")
                                                sleep(4)
                                                break
                                except Exception as e:
                                    print_lg(f"  Failed to auto-upload resume: {e}")

                                # Strategy 3: Proceed past resume/profile completion page
                                for _ in range(3):
                                    close_modals(driver)
                                    if "resume" not in driver.current_url.lower() and try_xp(driver, "//textarea[@id='cover_letter']"):
                                        break

                                    proceed_selectors = [
                                        "//button[contains(text(), 'Proceed to application')]",
                                        "//a[contains(text(), 'Proceed to application')]",
                                        "//button[contains(text(), 'Save and Next')]",
                                        "//button[contains(normalize-space(), 'Save & Next')]",
                                        "//input[@value='Save & Next']",
                                        "//button[@id='save_resume_btn']",
                                        "//button[contains(text(), 'Save')]",
                                        "//button[contains(text(), 'Next')]"
                                    ]
                                    clicked = False
                                    for sel in proceed_selectors:
                                        try:
                                            btn = driver.find_element(By.XPATH, sel)
                                            if btn.is_displayed():
                                                is_disabled = "disabled" in (btn.get_attribute("class") or "").lower() or btn.get_attribute("disabled")
                                                if is_disabled:
                                                    print_lg(f"  Wait: '{btn.text.strip()}' is disabled. Trying to clear overlays...")
                                                    close_modals(driver)
                                                    sleep(2)
                                                    try:
                                                        save_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Save')] | //div[contains(@class, 'modal')]//button[contains(text(), 'Save')]")
                                                        if save_btn.is_displayed():
                                                            driver.execute_script("arguments[0].click();", save_btn)
                                                            sleep(2)
                                                    except:
                                                        pass
                                                print_lg(f"  Clicking '{btn.text.strip() or 'Proceed'}' to move past resume page.")
                                                driver.execute_script("arguments[0].click();", btn)
                                                sleep(4)
                                                clicked = True
                                                break
                                        except:
                                            continue
                                    if not clicked:
                                        break

                                # Strategy 4: Check if application form is now visible
                                form_visible = False
                                try:
                                    cl = driver.find_element(By.ID, "cover_letter")
                                    if cl.is_displayed():
                                        form_visible = True
                                except:
                                    pass

                                if not form_visible:
                                    try:
                                        sub = driver.find_element(By.ID, "submit")
                                        if sub.is_displayed():
                                            form_visible = True
                                    except:
                                        pass

                                if form_visible:
                                    print_lg("  ✅ Application form is visible after processing resume requirements!")
                                    handle_application_form(title, company)
                                else:
                                    print_lg(f"  Profile/resume still requires confirmation for '{title}'.")
                                    # Prompt user to click Proceed in browser instead of failing/skipping the job!
                                    if prompt_user_if_stuck(driver, title, "Internshala is on resume page. Please click 'Proceed to application' in the browser window."):
                                        sleep(2)
                                        handle_application_form(title, company)
                                    else:
                                        print_lg(f"  Skipping '{title}' as resume could not be processed.")
                                        try:
                                            screenshot(driver, "Internshala", f"Incomplete_Profile_{title[:20]}")
                                        except:
                                            pass
                                        failed_count += 1
                                        save_failed_job(job_id=title, job_link=driver.current_url, error_reason="Internshala resume/profile incomplete")
                            else:
                                handle_application_form(title, company)
                        else:
                            print_lg(f"  Could not find Apply button for '{title}'.")
                            try:
                                screenshot(driver, title or "Unknown", "Apply_Not_Found")
                            except:
                                pass
                            failed_count += 1
                            save_failed_job(job_id=title, job_link=driver.current_url, error_reason="Apply button not found on Internshala detail page")

                        # Close the detail tab or return to search listings
                        if driver.current_window_handle != main_handle and len(driver.window_handles) > 1:
                            driver.close()
                            driver.switch_to.window(main_handle)
                            sleep(1)
                        else:
                            robust_get(driver, url)
                            sleep(2)

                    except Exception as e:
                        print_lg(f"Error processing listing {index}: {e}")
                        try:
                            if driver.current_window_handle != main_handle and len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(main_handle)
                            else:
                                robust_get(driver, url)
                                sleep(2)
                        except:
                            pass
                        continue

                # Next page logic
                try:
                    next_btn = driver.find_element(By.ID, "navigation-next")
                    if "disabled" in (next_btn.get_attribute("class") or ""):
                        print_lg("Reached last page of Internshala listings.")
                        break
                    next_btn.click()
                    sleep(3)
                    close_modals(driver)
                except:
                    try:
                        next_links = driver.find_elements(By.CSS_SELECTOR, "a[rel='next'], .pagination .next a")
                        if next_links:
                            next_links[0].click()
                            sleep(3)
                            close_modals(driver)
                        else:
                            print_lg("No more pages found.")
                            break
                    except:
                        print_lg("No more pages found.")
                        break

        except Exception as e:
            if "invalid session id" in str(e).lower():
                raise e
            print_lg(f"Critical error in Internshala loop for category '{category}':", e)

def handle_application_form(job_title, company_name):
    global applied_count, failed_count, skip_count, driver, actions, aiClient
    if not driver: return
    try:
        # Ensure aiClient is available
        if not aiClient and use_AI and ai_provider == "gemini":
            try:
                from modules.ai.geminiConnections import gemini_create_client
                aiClient = gemini_create_client()
            except Exception as e:
                print_lg(f"Could not initialize Gemini client: {e}")

        # Intelligently fill ALL form elements (Why hire you via Gemini, assessment questions via Gemini,
        # location, CTC, notice period, radio buttons, resume upload, etc.)
        print_lg(f"Filling application form for '{job_title}' using Gemini AI & Profile...")
        filled = auto_fill_form_elements(driver, job_title=job_title, company=company_name, ai_client=aiClient)
        print_lg(f"Filled {filled} form elements on Internshala.")

        # Find and click Submit button
        submit_btn = None
        submit_selectors = [
            (By.ID, "submit"),
            (By.XPATH, "//button[contains(normalize-space(), 'Submit')]"),
            (By.XPATH, "//button[contains(normalize-space(), 'Apply now')]"),
            (By.XPATH, "//input[@type='submit']"),
            (By.CSS_SELECTOR, ".submit-button"),
            (By.ID, "submit_application")
        ]
        
        for by, sel in submit_selectors:
            try:
                btn = driver.find_element(by, sel)
                if btn.is_displayed():
                    submit_btn = btn
                    break
            except: continue
            
        if not submit_btn:
            print_lg("Submit button not directly found. Checking for required fields blocking submit...")
            if not prompt_user_if_stuck(driver, job_title, "Submit button not found or an unanswered question requires your input in browser.", timeout_seconds=60):
                print_lg(f"Skipping '{job_title}' due to 1-minute timeout or user skip.")
                skip_count += 1
                return
            # Retry after user intervention
            for by, sel in submit_selectors:
                try:
                    btn = driver.find_element(by, sel)
                    if btn.is_displayed():
                        submit_btn = btn
                        break
                except: continue

        if submit_btn:
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            sleep(1)
            try:
                submit_btn.click()
            except:
                driver.execute_script("arguments[0].click();", submit_btn)
            print_lg(f"Clicked submit for {job_title}")
        else:
            try:
                screenshot(driver, "Internshala", f"Submit_Not_Found_{job_title[:20]}")
            except: pass
            raise Exception("Final submit button not found on Internshala application form")
        
        sleep(5)
        
        # Check if form is still asking for mandatory fields or error is displayed
        try:
            error_msgs = driver.find_elements(By.CSS_SELECTOR, ".error-message, .form-error, .alert-danger, .has-error")
            for em in error_msgs:
                if em.is_displayed() and em.text.strip():
                    print_lg(f"Form validation alert: {em.text.strip()}")
                    if not prompt_user_if_stuck(driver, job_title, f"Validation message on Internshala: '{em.text.strip()}'. Please resolve in browser.", timeout_seconds=60):
                        print_lg(f"Skipping '{job_title}' due to validation timeout or user skip.")
                        skip_count += 1
                        return
                    # Re-click submit
                    try:
                        submit_btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", submit_btn)
                    sleep(3)
                    break
        except:
            pass

        # Success verification
        success_indicators = ["successfully", "application sent", "applied", "congratulations", "already applied"]
        pg_src = driver.page_source.lower()
        if any(ind in pg_src for ind in success_indicators):
            print_lg(f"SUCCESS: Applied to {job_title}")
            screenshot(driver, "Internshala", f"Applied_Success_{job_title[:15]}")
            applied_count += 1
            save_submitted_job(job_id=job_title, title=job_title, company=company_name, job_link=driver.current_url, application_link="Internshala Applied")
        else:
            print_lg(f"WARNING: Application submission result unclear for {job_title}")
            applied_count += 1 
            save_submitted_job(job_id=job_title, title=job_title, company=company_name, job_link=driver.current_url, application_link="Internshala Applied (Unclear)")
            
        try:
            # Handle close modal if exists
            close_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'close')] | //div[contains(@class, 'close')]")
            close_btn.click()
        except: pass
        
    except Exception as e:
        print_lg(f"FAILED: Application for {job_title} failed: {e}")
        failed_count += 1
        save_failed_job(job_id=job_title, job_link=driver.current_url, error_reason="Internshala application failed", exception=e)
        if actions:
            try:
                actions.send_keys(Keys.ESCAPE).perform()
            except:
                pass

