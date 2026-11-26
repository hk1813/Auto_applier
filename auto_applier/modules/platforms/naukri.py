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
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, NoSuchWindowException, WebDriverException

import config.secrets
from config.secrets import use_AI, username, password, ai_provider
from config.search import naukri_search_terms, naukri_location, naukri_salary, naukri_experience, naukri_work_mode, bad_words
from config.settings import keep_screen_awake, run_in_background, safe_mode, smooth_scroll, stealth_mode
from config.personals import *
from config.questions import *

from modules.helpers import buffer, print_lg, sleep, manual_login_retry, truncate_for_csv, calculate_date_posted, critical_error_log, robust_get, screenshot, is_timeout
from modules.domain_filter import is_tech_job, is_experience_eligible
from modules.question_solver import auto_fill_form_elements, prompt_user_if_stuck
from modules.clickers_and_finders import try_linkText, try_xp, text_input_by_ID, find_by_class, wait_span_click, multi_sel_noWait, boolean_button_click, try_find_by_classes, scroll_to_view
from modules.history import save_submitted_job, save_failed_job

if use_AI:
    from modules.ai.openaiConnections import ai_answer_question
    from modules.ai.geminiConnections import gemini_answer_question

try:
    import pyautogui
except:
    pass

# To be set by the main caller
driver: WebDriver = None
wait: WebDriverWait = None
actions = None
aiClient = None

# Global counters/flags for Naukri
applied_count = 0
failed_count = 0
skip_count = 0
dailyLimitReached = False
naukri_tab = None

def init_naukri(drv, wt, act, ai_clnt):
    global driver, wait, actions, aiClient, naukri_tab
    driver = drv
    wait = wt
    actions = act
    aiClient = ai_clnt
    naukri_tab = driver.current_window_handle

def is_logged_in_NK() -> bool:
    '''
    Function to check if user is logged-in in Naukri
    '''
    try:
        # Check for profile icon or logout button
        if try_linkText(driver, "Logout"): return True
        if try_xp(driver, "//div[contains(@class, 'nI-g-profile-icon')]"): return True
        if try_xp(driver, "//a[contains(@href, 'naukri.com/mnjuser/profile')]"): return True
        if try_xp(driver, "//div[contains(@class, 'nI-g-profile-img')]"): return True
        # Naukri Campus elements
        if "naukricampus.com" in driver.current_url and try_xp(driver, "//div[contains(@class, 'profile')]"): return True
        if first_name and try_xp(driver, f"//*[contains(text(), '{first_name}')]"): return True
        if try_xp(driver, "//a[contains(@href, 'Logout')]"): return True
        return False
    except:
        return False

def close_modals():
    '''
    Try to close any overlaying modals on Naukri
    '''
    try:
        close_selectors = [
            "//span[contains(@class, 'gnb-icn-close')]",
            "//div[contains(@class, 'crossIcon')]",
            "//button[contains(@class, 'close')]",
            "//span[contains(text(), 'Skip')]",
            "//div[contains(@class, 'modal-close')]"
        ]
        for sel in close_selectors:
            try:
                btns = driver.find_elements(By.XPATH, sel)
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        sleep(1)
            except: continue
    except: pass

def login_NK() -> None:
    '''
    Function to login for Naukri
    '''
    # Navigate directly to login page to avoid homepage popups
    robust_get(driver, "https://www.naukri.com/nlogin/login")
    sleep(2)
    
    if is_logged_in_NK():
        print_lg("Already logged in to Naukri.")
        return

    # Use platform-specific credentials if available
    nk_username = getattr(config.secrets, 'naukri_username', username)
    nk_password = getattr(config.secrets, 'naukri_password', password)

    try:
        # Check if already on login page or navigate
        if "nlogin/login" not in driver.current_url:
            robust_get(driver, "https://www.naukri.com/nlogin/login")
            sleep(2)

        # Wait for the login modal fields using stable selectors
        user_field = None
        for sel in ["usernameField", "emailId"]:
            try:
                user_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, sel)))
                if user_field: break
            except: continue
            
        if not user_field:
            try:
                user_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='Email ID'], input[placeholder*='Username']")
            except: pass

        pass_field = None
        for sel in ["passwordField", "password"]:
            try:
                pass_field = driver.find_element(By.ID, sel)
                if pass_field: break
            except: continue
        
        if not pass_field:
            try:
                pass_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            except: pass

        if user_field and pass_field:
            # Fill credentials
            from modules.helpers import type_human_like
            type_human_like(user_field, nk_username)
            type_human_like(pass_field, nk_password)
            
            submit_btn = None
            submit_selectors = [
                "//button[contains(@class, 'loginButton')]",
                "//button[contains(text(), 'Login') and @type='submit']",
                "//button[normalize-space()='Login']",
                ".loginButton"
            ]
            for sel in submit_selectors:
                try:
                    if sel.startswith('.') or sel.startswith('#'):
                        submit_btn = driver.find_element(By.CSS_SELECTOR, sel)
                    else:
                        submit_btn = driver.find_element(By.XPATH, sel)
                    if submit_btn and submit_btn.is_displayed(): break
                except: continue

            if submit_btn:
                try:
                    driver.execute_script("arguments[0].click();", submit_btn)
                except:
                    submit_btn.click()
            else:
                actions.send_keys(Keys.ENTER).perform()
            
            print_lg("Clicked Naukri login button. Waiting for redirect...")
            sleep(7) # Wait for redirect/login processing
        
        if is_logged_in_NK():
            print_lg("Login successful to Naukri!")
            return
        
        # Check for error messages
        try:
            error_msg = driver.find_element(By.CLASS_NAME, "err-container").text
            print_lg(f"Naukri Login Error Displayed: {error_msg}")
        except: pass

        print_lg("Naukri auto-login failed. Attempting manual login fallback.")
        # Capture failure state
        screenshot(driver, "Naukri", "Login_Failed")
        manual_login_retry(is_logged_in_NK, 1)
    except Exception as e:
        print_lg("Error during Naukri login flow:", e)
        manual_login_retry(is_logged_in_NK, 1)

def set_filters():
    '''
    Apply search filters on Naukri
    '''
    try:
        print_lg("Applying filters on Naukri...")
        
        # Work mode (Remote)
        if 'naukri_work_mode' in globals() and naukri_work_mode and "Remote" in naukri_work_mode:
            try:
                # Find Remote filter checkbox label
                remote_xpath = "//span[contains(@title, 'Remote')]/preceding-sibling::i | //label[contains(., 'Remote')]"
                remote_filter = driver.find_element(By.XPATH, remote_xpath)
                # Check if already selected (classes or state might vary, often has 'selected' or checkbox checked)
                remote_filter.click()
                sleep(2)
            except: pass
            
        # Salary
        if 'naukri_salary' in globals() and naukri_salary:
            for s_range in naukri_salary:
                try:
                    salary_xpath = f"//span[contains(@title, '{s_range}')]/preceding-sibling::i"
                    driver.find_element(By.XPATH, salary_xpath).click()
                    sleep(1)
                except: pass
        
        # Experience
        # Experience can be tricky on Naukri (slider or list). Usually the search bar has it.
        
        buffer(2)
    except Exception as e:
        print_lg("Failed to apply some filters on Naukri:", e)

def apply_to_jobs(end_time: float = None) -> None:
    global applied_count, failed_count, skip_count, dailyLimitReached, naukri_tab
    
    # 0. Switch to Naukri tab
    global naukri_tab
    try:
        if naukri_tab and naukri_tab in driver.window_handles:
            driver.switch_to.window(naukri_tab)
        elif driver.window_handles:
            naukri_tab = driver.window_handles[0]
            driver.switch_to.window(naukri_tab)
    except:
        pass

    # 1. Iterate through search terms
    for term in naukri_search_terms:
        if is_timeout(end_time):
            print_lg("Time limit reached for Naukri cycle. Rotating to next platform.")
            break
        try:
            print_lg(f"\n--- Searching for '{term}' on Naukri ---")
            # Navigate directly to search results
            search_url = f"https://www.naukri.com/{term.lower().replace(' ', '-')}-jobs"
            if naukri_location:
                search_url += f"-in-{naukri_location.lower().replace(' ', '-')}"

            # Append experience filter as query param (e.g. ?experience=0 for 0-2 yrs / freshers)
            if naukri_experience:
                if isinstance(naukri_experience, list):
                    # Naukri backend expects a single integer, where 0 filters for freshers / 0-2 yrs
                    exp_val = "0" if "0" in [str(x) for x in naukri_experience] else str(naukri_experience[0])
                else:
                    exp_val = str(naukri_experience)
                search_url += f"?experience={exp_val}"

            print_lg(f"Navigating to: {search_url}")
            robust_get(driver, search_url)
            
            # Wait for job listings or specific page content
            try:
                # Based on browser inspection, listings use srp-jobtuple-wrapper or cust-job-tuple
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "srp-jobtuple-wrapper")))
                print_lg("Found Naukri job listings.")
            except:
                print_lg("Timed out waiting for Naukri listings. Checking for alternative selectors or empty results.")
                if "No jobs found" in driver.page_source:
                    print_lg(f"No jobs found for '{term}' on Naukri.")
                    continue
            
            set_filters()
            
            # Application loop
            application_loop(term, end_time=end_time)
            
        except Exception as e:
            if "invalid session id" in str(e).lower():
                raise e
            print_lg(f"Error searching for '{term}' on Naukri: {e}")
            continue

def application_loop(term: str, end_time: float = None):
    global applied_count, failed_count, skip_count
    try:
        while True:
            if is_timeout(end_time):
                print_lg("Time limit reached for Naukri application loop.")
                break
            # Job tuples are individual job listings
            job_tuples = driver.find_elements(By.CLASS_NAME, "srp-jobtuple-wrapper")
            if not job_tuples:
                # Try fallback
                job_tuples = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
            
            print_lg(f"Found {len(job_tuples)} jobs on Naukri results page.")
            if not job_tuples:
                print_lg("No Naukri job tuples found on this page. Page content might be different or no results.")
            
            for index, job in enumerate(job_tuples):
                if is_timeout(end_time):
                    print_lg("Time limit reached for Naukri application loop.")
                    return
                try:
                    # Keep screen awake
                    if keep_screen_awake: pyautogui.press('shiftright')
                    
                    # Get title and company
                    title = job.find_element(By.CLASS_NAME, "title").text
                    company = job.find_element(By.CLASS_NAME, "comp-name").text
                    print_lg(f"Processing: {title} at {company}")
                    
                    # Already applied?
                    # Naukri sometimes shows 'Applied' text
                    if "Applied" in job.text:
                        print_lg("Already applied. Skipping.")
                        continue
                    
                    # ── DOMAIN FILTER: strict tech-only gate ──────────────
                    if not is_tech_job(title):
                        print_lg(f"[DOMAIN FILTER] Skipping non-tech job: '{title}'")
                        skip_count += 1
                        continue
                    # ──────────────────────────────────────────────────────

                    # ── EXPERIENCE FILTER: strict 0-2 years gate ──────────
                    card_text = job.text
                    is_exp_ok, exp_reason = is_experience_eligible(title, snippet_text=card_text, max_allowed_exp=2)
                    if not is_exp_ok:
                        print_lg(f"[EXP FILTER] Skipping '{title}' at {company}: {exp_reason}")
                        skip_count += 1
                        continue
                    # ──────────────────────────────────────────────────────

                    # Also check against global bad_words
                    title_lower = title.lower()
                    bad_word_hit = False
                    for bad in bad_words:
                        if bad.lower() in title_lower:
                            print_lg(f"Title '{title}' contains bad word '{bad}'. Skipping.")
                            bad_word_hit = True
                            break
                    if bad_word_hit:
                        skip_count += 1
                        continue
                    
                    # Click job to open details
                    scroll_to_view(driver, job.find_element(By.CLASS_NAME, "title"))
                    close_modals()
                    initial_handles = driver.window_handles
                    try:
                        job.find_element(By.CLASS_NAME, "title").click()
                    except:
                        driver.execute_script("arguments[0].click();", job.find_element(By.CLASS_NAME, "title"))
                    sleep(2)
                    
                    # Handle details page in new tab
                    handle_job_detail(title, company, initial_handles)
                    
                except Exception as e:
                    print_lg(f"Error processing Naukri listing {index}: {e}")
                    continue
            
            # Pagination
            try:
                next_btn = driver.find_element(By.XPATH, "//a[contains(@class, 'styles_btn-secondary') and contains(., 'Next')]")
                if "disabled" in next_btn.get_attribute("class"):
                    print_lg("Reached last page of Naukri results.")
                    break
                next_btn.click()
                sleep(3)
            except:
                print_lg("No more Naukri pages found.")
                break
                
    except Exception as e:
        print_lg("Naukri application loop error:", e)

def handle_job_detail(job_title, company_name, initial_handles):
    global applied_count, failed_count, skip_count
    main_handle = driver.current_window_handle
    switched_to_new_tab = False
    try:
        # Wait for new tab
        wait.until(lambda d: len(d.window_handles) > len(initial_handles))
        # Switch to new tab
        new_handles = set(driver.window_handles) - set(initial_handles)
        if new_handles:
            driver.switch_to.window(new_handles.pop())
            switched_to_new_tab = True

        
        sleep(3)
        print_lg(f"Opened detail page for '{job_title}': {driver.current_url}")
        
        # ── SECOND-LAYER EXPERIENCE & DOMAIN CHECK (detail page + URL) ──
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
        # ─────────────────────────────────────────────────────────────────
        
        def find_apply_button():
            """Try many selectors to find the Apply button in the current context."""
            apply_selectors = [
                (By.ID, "apply-button"),
                (By.CSS_SELECTOR, "[class*='apply-button']"),
                (By.CSS_SELECTOR, "[class*='applyButton']"),
                (By.CSS_SELECTOR, "[class*='Apply']"),
                (By.XPATH, "//button[normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))='apply']"),
                (By.XPATH, "//button[normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))='apply now']"),
                (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"),
                (By.XPATH, "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]"),
                (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply now')]"),
                (By.XPATH, "//a[contains(@class, 'apply')]"),
                (By.XPATH, "//button[contains(., 'Apply')]"),
                (By.XPATH, "//span[contains(., 'Apply')]/parent::button"),
                (By.XPATH, "//div[contains(@class, 'apply')]//button")
            ]
            for by, sel in apply_selectors:
                try:
                    btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
                    if btn:
                        print_lg(f"Found Apply button via: {sel}")
                        return btn
                except: continue
            return None
        
        # 1. Try main page
        apply_btn = find_apply_button()
        
        # 2. Try iframes if not found
        if not apply_btn:
            print_lg("Apply button not found in main page. Scanning iframes...")
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            print_lg(f"  -> {len(iframes)} iframes found.")
            for i, frame in enumerate(iframes):
                try:
                    driver.switch_to.frame(frame)
                    apply_btn = find_apply_button()
                    if apply_btn:
                        print_lg(f"  -> Found Apply button inside iframe #{i}.")
                        break
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()
                    continue
        
        # 3. Debug info if still not found
        if not apply_btn:
            try:
                driver.switch_to.default_content()
                buttons = driver.find_elements(By.TAG_NAME, "button")
                btn_texts = [b.text.strip() for b in buttons if b.text.strip()][:15]
                links = driver.find_elements(By.TAG_NAME, "a")
                apply_links = [l.text.strip() for l in links if 'apply' in l.text.lower()][:5]
                print_lg(f"DEBUG - All visible buttons: {btn_texts}")
                print_lg(f"DEBUG - Apply-related links: {apply_links}")
                print_lg(f"DEBUG - Current URL: {driver.current_url}")
            except: pass
            raise Exception("Apply button not found with any selector (including iframes)")
        
        # Check if button is for external company site
        btn_text = (apply_btn.text or "").strip().lower()
        if any(ext_w in btn_text for ext_w in ["company site", "external", "apply on site"]):
            print_lg(f"External portal detected for '{job_title}' ('{apply_btn.text}'). Skipping external application.")
            skip_count += 1
            return

        # Click the button (with JS fallback)
        try:
            driver.switch_to.default_content()
        except: pass
        try:
            apply_btn.click()
        except:
            driver.execute_script("arguments[0].click();", apply_btn)
        sleep(3)
            
        # Determine success
        pg_src = driver.page_source.lower()
        if "successfully" in pg_src or "application sent" in pg_src:
            print_lg(f"SUCCESS: Applied to '{job_title}' at {company_name} on Naukri.")
            applied_count += 1
            save_submitted_job(job_id=job_title, title=job_title, company=company_name, job_link=driver.current_url, application_link="Naukri Applied")
        elif "already applied" in pg_src or "you have applied" in pg_src:
            print_lg(f"Already applied to '{job_title}'. Skipping.")
            skip_count += 1
        else:
            # Check for questionnaire / chatbot questions
            print_lg(f"Checking for Naukri questionnaire/assessment for '{job_title}'...")
            filled = auto_fill_form_elements(driver, job_title=job_title, company=company_name, ai_client=aiClient)
            if filled > 0:
                print_lg(f"Filled {filled} questionnaire fields on Naukri. Attempting submit...")
                for sub_sel in ["//button[contains(normalize-space(), 'Submit')]", "//button[contains(normalize-space(), 'Save')]", "//button[contains(normalize-space(), 'Continue')]"]:
                    try:
                        sbtn = driver.find_element(By.XPATH, sub_sel)
                        if sbtn.is_displayed():
                            driver.execute_script("arguments[0].click();", sbtn)
                            sleep(3)
                            break
                    except:
                        pass

            pg_src_after = driver.page_source.lower()
            if "successfully" in pg_src_after or "application sent" in pg_src_after:
                print_lg(f"SUCCESS: Applied to '{job_title}' at {company_name} on Naukri after questionnaire.")
                applied_count += 1
                save_submitted_job(job_id=job_title, title=job_title, company=company_name, job_link=driver.current_url, application_link="Naukri Applied")
            else:
                if prompt_user_if_stuck(driver, job_title, "Naukri questionnaire needs your review or completion in browser", timeout_seconds=60):
                    print_lg(f"Marking '{job_title}' as applied on Naukri after manual completion.")
                    applied_count += 1
                    save_submitted_job(job_id=job_title, title=job_title, company=company_name, job_link=driver.current_url, application_link="Naukri Applied (Questionnaire)")
                else:
                    print_lg(f"Skipping '{job_title}' on Naukri due to 1-minute timeout or user skip.")
                    skip_count += 1
                    return
    except Exception as e:
        print_lg(f"Failed to apply on Naukri for '{job_title}': {e}")
        failed_count += 1
        try:
            save_failed_job(job_id=job_title, job_link=driver.current_url, error_reason="Naukri apply button failure", exception=e)
        except: pass
    finally:
        try:
            driver.switch_to.default_content()
        except:
            pass
        try:
            # Safely close any newly opened detail tab/popup without touching main_handle
            current_handles = list(driver.window_handles)
            for h in current_handles:
                if h not in initial_handles and h != main_handle and len(driver.window_handles) > 1:
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

