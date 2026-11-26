'''
Author:     Himanshu Khurana
LinkedIn:   https://www.linkedin.com/in/himanshukhurana/

Copyright (C) 2024 Himanshu Khurana

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    24.12.29.12.30
'''


# Imports
import os
import csv
import re
import subprocess

from dotenv import load_dotenv
load_dotenv(override=True)

# Self-healing for X11 authorization (specifically for Linux environments with DisplayConnectionError)
def fix_x11_authorization():
    display = os.environ.get('DISPLAY', ':0')
    if os.name == 'posix' and display:
        try:
            # Check if we have an entry for the current display
            result = subprocess.run(['xauth', 'list', display], capture_output=True, text=True)
            # If the specific display (e.g., :0) is not in the list, or we just want to ensure it's there
            # We use a more aggressive approach: if pyautogui failed (which calls this), try to add cookies.
            cookies = subprocess.run(['xauth', 'list'], capture_output=True, text=True).stdout.splitlines()
            if cookies:
                # Get the last part (cookie) of the first available entry
                parts = cookies[0].split()
                if len(parts) >= 3:
                    protocol = parts[1]
                    cookie = parts[2]
                    # Add for both the display as-is and with /unix: prefix for robustness
                    subprocess.run(['xauth', 'add', display, protocol, cookie], capture_output=True)
                    if not display.startswith('/unix:'):
                        subprocess.run(['xauth', 'add', f'/unix{display}', protocol, cookie], capture_output=True)
        except Exception:
            pass

try:
    import pyautogui
except Exception:
    fix_x11_authorization()
    import pyautogui

# Set CSV field size limit to prevent field size errors
csv.field_size_limit(1000000)  # Set to 1MB instead of default 131KB

from random import choice, shuffle, randint
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, NoSuchWindowException, ElementNotInteractableException, WebDriverException

from config.personals import *
from config.questions import *
from config.search import *
from config.secrets import use_AI, username, password, ai_provider
from config.settings import *

from modules.open_chrome import *
from modules.helpers import *
from modules.clickers_and_finders import *
from modules.validator import validate_config
from modules.platforms import linkedin, internshala, naukri, indeed

if use_AI:
    from modules.ai.openaiConnections import ai_create_openai_client, ai_close_openai_client, ai_answer_question
    from modules.ai.deepseekConnections import deepseek_create_client
    from modules.ai.geminiConnections import gemini_create_client, gemini_answer_question

from typing import Literal

pyautogui.FAILSAFE = False
# if use_resume_generator:    from resume_generator import is_logged_in_GPT, login_GPT, open_resume_chat, create_custom_resume


#< Global Variables and logics

if run_in_background == True:
    pause_at_failed_question = False
    pause_before_submit = False
    run_non_stop = False

first_name = first_name.strip()
middle_name = middle_name.strip()
last_name = last_name.strip()
full_name = first_name + " " + middle_name + " " + last_name if middle_name else first_name + " " + last_name

useNewResume = True
randomly_answered_questions = set()

tabs_count = 1
easy_applied_count = 0
external_jobs_count = 0
failed_count = 0
skip_count = 0
dailyEasyApplyLimitReached = False

re_experience = re.compile(r'(?:\d+[-]\d+|\d+\+?)\s*year[s]?', re.IGNORECASE)

desired_salary_lakhs = str(round(desired_salary / 100000, 2))
desired_salary_monthly = str(round(desired_salary/12, 2))
desired_salary = str(desired_salary)

current_ctc_lakhs = str(round(current_ctc / 100000, 2))
current_ctc_monthly = str(round(current_ctc/12, 2))
current_ctc = str(current_ctc)

notice_period_months = str(notice_period//30)
notice_period_weeks = str(notice_period//7)
notice_period = str(notice_period)

aiClient = None
##> ------ Himanshu Khurana : dheeraj9811 Email:dheeraj20194@iiitd.ac.in/dheerajdeshwal9811@gmail.com - Feature ------
about_company_for_ai = None # TODO extract about company for AI
##<

#>



# LinkedIn specific functions were moved to modules/platforms/linkedin.py
# This script will now route to that module for LinkedIn-related automation.


        

# Define which platforms to run — controlled by PLATFORMS env var in .env

# Build list of all available (configured) platforms
_available_platforms = []
# Build list of all available (configured) platforms
_available_platforms = []
try:
    if 'search_terms' in globals() and search_terms: _available_platforms.append("linkedin")
except: pass
try:
    if 'internshala_categories' in globals() and internshala_categories: _available_platforms.append("internshala")
except: pass
try:
    if 'naukri_search_terms' in globals() and naukri_search_terms: _available_platforms.append("naukri")
except: pass
try:
    if 'indeed_search_terms' in globals() and indeed_search_terms: _available_platforms.append("indeed")
except: pass

print(f"Initially detected available platforms: {_available_platforms}")

# Read PLATFORMS from .env  (default: "all")
_env_platforms = os.environ.get("PLATFORMS", "all").strip().lower()
if _env_platforms == "all" or _env_platforms == "":
    platforms_to_run = _available_platforms
else:
    _requested = [p.strip() for p in _env_platforms.split(",") if p.strip()]
    _valid = {"linkedin", "internshala", "naukri", "indeed"}
    platforms_to_run = [p for p in _requested if p in _valid and p in _available_platforms]

print(f"PLATFORMS setting: '{_env_platforms}' -> Final platforms to run: {platforms_to_run}")


def run(total_runs: int) -> int:
    print_lg("\n########################################################################################################################\n")
    print_lg(f"Date and Time: {datetime.now()}")
    print_lg(f"Cycle number: {total_runs}")
    
    global driver, wait, actions
    
    # Route to selected platforms, each isolated so one failure won't kill others
    PLATFORM_ROTATION_TIME = 600 # 10 minutes in seconds
    for platform in platforms_to_run:
        try:
            end_time = time.time() + PLATFORM_ROTATION_TIME
            if platform == "linkedin":
                if not linkedin.dailyEasyApplyLimitReached:
                    print_lg(f"Running LinkedIn automation... (Cycle {total_runs})")
                    print_lg(f"Looking for jobs posted within '{date_posted}' and sorting by '{sort_by}'")
                    linkedin.apply_to_jobs(search_terms, end_time=end_time)
            elif platform == "internshala":
                if not internshala.dailyLimitReached:
                    print_lg(f"Running Internshala automation... (Cycle {total_runs})")
                    internshala.apply_to_jobs(end_time=end_time)
            elif platform == "naukri":
                if not naukri.dailyLimitReached:
                    print_lg(f"Running Naukri automation... (Cycle {total_runs})")
                    naukri.apply_to_jobs(end_time=end_time)
            elif platform == "indeed":
                if not indeed.dailyLimitReached:
                    print_lg(f"Running Indeed automation... (Cycle {total_runs})")
                    indeed.apply_to_jobs(end_time=end_time)

        except (NoSuchWindowException, WebDriverException) as e:
            print_lg(f"Browser crash while running {platform}: {str(e)[:120]}")
            print_lg(f"Attempting to reinitialize browser and continue with remaining platforms...")
            try:
                try: driver.quit()
                except Exception: pass
                driver, wait, actions = setup_bot()
                # Re-initialize all platform drivers
                if "linkedin" in platforms_to_run:
                    linkedin.init_linkedin(driver, wait, actions, aiClient)
                if "internshala" in platforms_to_run:
                    internshala.init_internshala(driver, wait, actions, aiClient)
                if "naukri" in platforms_to_run:
                    naukri.init_naukri(driver, wait, actions, aiClient)
                if "indeed" in platforms_to_run:
                    indeed.init_indeed(driver, wait, actions, aiClient)
                print_lg("Browser reinitialized. Continuing with next platform.")
            except Exception as reinit_e:
                print_lg(f"Failed to reinitialize browser: {reinit_e}. Skipping remaining platforms.")
                break
        except Exception as e:
            print_lg(f"Unexpected error on {platform}: {str(e)[:200]}")
            critical_error_log(f"Platform error: {platform}", e)
            # Continue to next platform
            continue
    
    # Sync stats back for final summary
    global easy_applied_count, external_jobs_count, failed_count, skip_count
    easy_applied_count = linkedin.easy_applied_count + internshala.applied_count + naukri.applied_count + indeed.applied_count
    failed_count = linkedin.failed_count + internshala.failed_count + naukri.failed_count + indeed.failed_count
    skip_count = linkedin.skip_count + internshala.skip_count + naukri.skip_count + indeed.skip_count
    
    print_lg("########################################################################################################################\n")
    
    # Check if all reached limit
    all_reached = True
    if "linkedin" in platforms_to_run and not linkedin.dailyEasyApplyLimitReached: all_reached = False
    if "internshala" in platforms_to_run and not internshala.dailyLimitReached: all_reached = False
    if "naukri" in platforms_to_run and not naukri.dailyLimitReached: all_reached = False
    if "indeed" in platforms_to_run and not indeed.dailyLimitReached: all_reached = False
    
    if not all_reached or run_non_stop:
        # If we reached limit but are in non-stop mode, or haven't reached limit, sleep and continue
        sleep_minutes = 2
        print_lg(f"Cycle {total_runs} complete. Sleeping for {sleep_minutes} minutes before next cycle...")
        # Simulate the 10-minute wait with updates
        for i in range(sleep_minutes, 0, -1):
            if i == 5:
                print_lg(f"Starting next cycle in 5 minutes...")
            sleep(60) 
    
    buffer(3)
    return total_runs + 1


def main() -> None:
    try:
        # Validate configuration
        validate_config()

        # Check and fix X11 authorization if needed
        fix_x11_authorization()
        
        # Initialize the bot
        global driver, wait, actions, aiClient, tabs_count, linkedIn_tab
        driver, wait, actions = setup_bot()
        linkedIn_tab = driver.current_window_handle  # default fallback
        first_tab = driver.current_window_handle      # first tab for any platform

        # Initialize AI Client early so platforms have access to it immediately
        if use_AI:
            try:
                if ai_provider == "openai":
                    aiClient = ai_create_openai_client()
                elif ai_provider == "deepseek":
                    aiClient = deepseek_create_client()
                elif ai_provider == "gemini":
                    aiClient = gemini_create_client()
            except Exception as e:
                print_lg(f"Failed to initialize AI client: {e}")

        # Initialize platforms
        if "linkedin" in platforms_to_run:
            linkedin.init_linkedin(driver, wait, actions, aiClient)
            # Login to LinkedIn
            robust_get(driver, "https://www.linkedin.com/login")
            if not linkedin.is_logged_in_LN(): linkedin.login_LN()
            linkedIn_tab = driver.current_window_handle
            
        if "internshala" in platforms_to_run:
            if "linkedin" not in platforms_to_run:
                # LinkedIn didn't open a tab; reuse the initial tab
                internshala.init_internshala(driver, wait, actions, aiClient)
            else:
                if driver.current_window_handle != linkedIn_tab:
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[-1])
                internshala.init_internshala(driver, wait, actions, aiClient)
            # Login to Internshala
            if not internshala.is_logged_in_IS(): internshala.login_IS()
            internshala.internshala_tab = driver.current_window_handle
            first_tab = first_tab if "linkedin" in platforms_to_run else internshala.internshala_tab
            
        if "naukri" in platforms_to_run:
            if len(driver.window_handles) == 1 and "linkedin" not in platforms_to_run and "internshala" not in platforms_to_run:
                # Only platform so far, reuse initial tab
                pass
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[-1])
            naukri.init_naukri(driver, wait, actions, aiClient)
            # Login to Naukri
            if not naukri.is_logged_in_NK(): naukri.login_NK()
            naukri.naukri_tab = driver.current_window_handle
            if "linkedin" not in platforms_to_run and "internshala" not in platforms_to_run:
                first_tab = naukri.naukri_tab

        if "indeed" in platforms_to_run:
            if len(driver.window_handles) == 1 and "linkedin" not in platforms_to_run and "internshala" not in platforms_to_run and "naukri" not in platforms_to_run:
                # Only platform, reuse initial tab
                pass
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[-1])
            indeed.init_indeed(driver, wait, actions, aiClient)
            # Login to Indeed
            if not indeed.is_logged_in_IN(): indeed.login_IN()
            indeed.indeed_tab = driver.current_window_handle
            if "linkedin" not in platforms_to_run and "internshala" not in platforms_to_run and "naukri" not in platforms_to_run:
                first_tab = indeed.indeed_tab

        # Update modules with aiClient
        if "linkedin" in platforms_to_run: linkedin.aiClient = aiClient
        if "internshala" in platforms_to_run: internshala.aiClient = aiClient
        if "naukri" in platforms_to_run: naukri.aiClient = aiClient
        if "indeed" in platforms_to_run: indeed.aiClient = aiClient

        # Start applying to jobs — switch to first active platform's tab
        driver.switch_to.window(first_tab)
        total_runs = 0
        total_runs = run(total_runs)
        while(run_non_stop):
            if cycle_date_posted:
                date_options = ["Any time", "Past month", "Past week", "Past 24 hours"]
                global date_posted
                date_posted = date_options[date_options.index(date_posted)+1 if date_options.index(date_posted)+1 > len(date_options) else -1] if stop_date_cycle_at_24hr else date_options[0 if date_options.index(date_posted)+1 >= len(date_options) else date_options.index(date_posted)+1]
            if alternate_sortby:
                global sort_by
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
                total_runs = run(total_runs)
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
            total_runs = run(total_runs)
            # Stop loop if ALL active platforms have reached their daily limit
            all_daily_limits_reached = True
            if "linkedin" in platforms_to_run and not linkedin.dailyEasyApplyLimitReached: all_daily_limits_reached = False
            if "internshala" in platforms_to_run and not internshala.dailyLimitReached: all_daily_limits_reached = False
            if "naukri" in platforms_to_run and not naukri.dailyLimitReached: all_daily_limits_reached = False
            if "indeed" in platforms_to_run and not indeed.dailyLimitReached: all_daily_limits_reached = False
            if all_daily_limits_reached:
                break
        
        print_lg("\n########################################################################################################################\n")
        print_lg(f"Final Summary of Applications for Today:")
        if "linkedin" in platforms_to_run:
            print_lg(f"LinkedIn - Applied: {linkedin.easy_applied_count}, Failed: {linkedin.failed_count}, Skipped: {linkedin.skip_count}")
        if "internshala" in platforms_to_run:
            print_lg(f"Internshala - Applied: {internshala.applied_count}, Failed: {internshala.failed_count}, Skipped: {internshala.skip_count}")
        if "naukri" in platforms_to_run:
            print_lg(f"Naukri - Applied: {naukri.applied_count}, Failed: {naukri.failed_count}, Skipped: {naukri.skip_count}")
        if "indeed" in platforms_to_run:
            print_lg(f"Indeed - Applied: {indeed.applied_count}, Failed: {indeed.failed_count}, Skipped: {indeed.skip_count}")
        
        print_lg(f"\nTotal Easy Applied Jobs: {easy_applied_count}")
        print_lg(f"Total Failed Jobs: {failed_count}")
        print_lg(f"Total Skipped Jobs: {skip_count}")
        print_lg("\n########################################################################################################################\n")
        print_lg("Execution completed. Closing the browser...")
        
    except (NoSuchWindowException, WebDriverException) as e:
        print_lg("Browser window closed or session is invalid. Ending application process.", e)
    except Exception as e:
        print_lg("An unexpected error occurred in main execution flow!")
        critical_error_log("In Main", e)
        # print_lg(e)
    finally:
        try:
            quote = choice([
                "Success is not final, failure is not fatal: It is the courage to continue that counts. - Winston Churchill",
                "Believe in yourself and all that you are. Know that there is something inside you that is greater than any obstacle. - Christian D. Larson",
                "Every job is a self-portrait of the person who does it. Autograph your work with excellence.",
                "The only way to do great work is to love what you do. If you haven't found it yet, keep looking. Don't settle. - Steve Jobs",
                "Opportunities don't happen, you create them. - Chris Grosser",
                "The road to success and the road to failure are almost exactly the same. The difference is perseverance.",
                "Obstacles are those frightful things you see when you take your eyes off your goal. - Henry Ford",
                "The only limit to our realization of tomorrow will be our doubts of today. - Franklin D. Roosevelt"
            ])
            msg = f"\n{quote}\n\nBest regards"
            print_lg(msg)
        except:
            pass

        if tabs_count >= 10:
            msg = "NOTE: IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM!\n\nOr it's highly likely that application will just open browser and not do anything next time!" 
            print_lg("\n"+msg)
            
        ##> ------ Yang Li : MARKYangL - Feature ------
        if use_AI and aiClient:
            try:
                if ai_provider.lower() == "openai":
                    ai_close_openai_client(aiClient)
                elif ai_provider.lower() == "deepseek":
                    ai_close_openai_client(aiClient)
                elif ai_provider.lower() == "gemini":
                    pass # Gemini client does not need to be closed
                print_lg(f"Closed {ai_provider} AI client.")
            except Exception as e:
                print_lg("Failed to close AI client:", e)
        ##<
        
        try:
            if driver:
                driver.quit()
                print_lg("\nBrowser closed.")
        except Exception as e:
            pass


if __name__ == "__main__":
    main()
