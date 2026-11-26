import os
import csv
import re
from random import shuffle, randint
from datetime import datetime
from typing import Literal

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, NoSuchWindowException, WebDriverException

import config.secrets
from config.secrets import username, password, ai_provider
from config.search import *
from config.settings import *
from config.personals import *
from config.questions import *

from modules.helpers import buffer, print_lg, sleep, manual_login_retry, truncate_for_csv, calculate_date_posted, critical_error_log, robust_get, screenshot, is_timeout
from modules.clickers_and_finders import try_linkText, try_xp, text_input_by_ID, find_by_class, wait_span_click, multi_sel_noWait, boolean_button_click, try_find_by_classes, scroll_to_view
from modules.history import save_submitted_job, save_failed_job

try:
    import pyautogui
except:
    pass

# To be set by the main caller
driver: WebDriver = None
wait: WebDriverWait = None
actions = None
aiClient = None

# Global counters/flags for LinkedIn (synced with main or kept internal)
current_city = ""
failed_count = 0
skip_count = 0
easy_applied_count = 0
external_jobs_count = 0
tabs_count = 0
dailyEasyApplyLimitReached = False
useNewResume = True
linkedIn_tab = None

def init_linkedin(drv, wt, act, ai_clnt):
    global driver, wait, actions, aiClient, linkedIn_tab
    driver = drv
    wait = wt
    actions = act
    aiClient = ai_clnt
    linkedIn_tab = driver.current_window_handle

def is_logged_in_LN() -> bool:
    if driver.current_url == "https://www.linkedin.com/feed/": return True
    if try_linkText(driver, "Sign in"): return False
    if try_xp(driver, '//button[@type="submit" and contains(text(), "Sign in")]'):  return False
    if try_linkText(driver, "Join now"): return False
    print_lg("Didn't find Sign in link, so assuming user is logged in!")
    return True

def login_LN() -> None:
    robust_get(driver, "https://www.linkedin.com/login")
    
    # Use platform-specific credentials if available
    ln_username = getattr(config.secrets, 'linkedin_username', username)
    ln_password = getattr(config.secrets, 'linkedin_password', password)

    try:
        wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Forgot password?")))
        try:
            text_input_by_ID(driver, "username", ln_username, 1)
        except:
            print_lg("Couldn't find username field.")
        try:
            text_input_by_ID(driver, "password", ln_password, 1)
        except:
            print_lg("Couldn't find password field.")
        driver.find_element(By.XPATH, '//button[@type="submit" and contains(text(), "Sign in")]').click()
    except Exception as e1:
        try:
            profile_button = find_by_class(driver, "profile__details")
            profile_button.click()
        except:
            print_lg("Couldn't Login!", e1)

    try:
        wait.until(EC.url_to_be("https://www.linkedin.com/feed/"))
        return print_lg("Login successful!")
    except:
        print_lg("Seems like login attempt failed! Possibly due to wrong credentials or already logged in! Try logging in manually!")
        manual_login_retry(is_logged_in_LN, 2)

def get_applied_job_ids() -> set[str]:
    job_ids: set[str] = set()
    try:
        if not os.path.exists(file_name):
            # Ensure directory exists
            if os.path.dirname(file_name):
                os.makedirs(os.path.dirname(file_name), exist_ok=True)
            # Create the file with a header if it doesn't exist
            with open(file_name, 'w', encoding='utf-8', newline='') as file:
                writer = csv.writer(file)
                # Assuming standard header or no header
            print_lg(f"Created new CSV file: {file_name}")
            return job_ids

        with open(file_name, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row: job_ids.add(row[0])
    except FileNotFoundError:
        print_lg(f"The CSV file '{file_name}' does not exist.")
    return job_ids

def set_search_location() -> None:
    if search_location:
        print_lg(f'Setting search location as: "{search_location}"')
        try:
            search_location_ele = None
            selectors = [
                (By.XPATH, "//input[@aria-label='City, state, or zip code' and not(@disabled)]"),
                (By.XPATH, "//input[contains(@aria-label, 'location') and not(@disabled)]"),
                (By.XPATH, "//input[contains(@placeholder, 'location') and not(@disabled)]"),
                (By.XPATH, "//input[contains(@id, 'jobs-search-box-location')]"),
                (By.CSS_SELECTOR, "input[aria-label*='location']"),
                (By.NAME, "location"),
                (By.CLASS_NAME, "jobs-search-box__input--location"),
                (By.XPATH, "//div[contains(@class, 'location')]//input")
            ]
            for by, val in selectors:
                try:
                    search_location_ele = WebDriverWait(driver, 1).until(EC.presence_of_element_located((by, val)))
                    if search_location_ele: break
                except: continue
                
            if not search_location_ele:
                for class_name in ["jobs-search-box__input--location", "jobs-search-box__location-picker"]:
                    try:
                        driver.find_element(By.CLASS_NAME, class_name).click()
                        search_location_ele = driver.switch_to.active_element
                        if search_location_ele and search_location_ele.tag_name == "input": break
                    except: pass

            if search_location_ele:
                sleep(1)
                from modules.helpers import type_human_like
                type_human_like(search_location_ele, search_location.strip())
                sleep(2)
                search_location_ele.send_keys(Keys.ENTER)
                print_lg(f"Successfully set search location to: {search_location}")
                buffer(2)
            else:
                print_lg("Could not find search location input, skipping location setting...")
                
        except Exception as e:
            print_lg(f"Search location setting failed, continuing without location: {str(e)[:50]}")
            # Continue without location setting

def apply_filters() -> None:
    set_search_location()
    try:
        recommended_wait = 1 if click_gap < 1 else 0
        buffer(2)
        all_filters_btn = None
        for xpath in [
            '//button[contains(., "All filters")]',
            '//button[contains(@aria-label, "All filters")]',
            "//button[contains(@class, 'search-reusables__all-filters-button')]"
        ]:
            try:
                all_filters_btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                if all_filters_btn: break
            except: continue
            
        if all_filters_btn:
            # Try multiple approaches to handle overlapping elements
            try:
                # First try to dismiss any search suggestions
                WebDriverWait(driver, 3).until(EC.invisibility_of_element_located((By.CLASS_NAME, "jobs-search-box__search-starter")))
            except:
                # If suggestions persist, try clicking outside to dismiss them
                actions.send_keys(Keys.ESCAPE).perform()
                buffer(0.5)
                try:
                    WebDriverWait(driver, 2).until(EC.invisibility_of_element_located((By.CLASS_NAME, "jobs-search-box__search-starter")))
                except:
                    pass
            
            # Try JavaScript click as fallback
            try:
                driver.execute_script("arguments[0].click();", all_filters_btn)
                print_lg("Clicked 'All filters' button using JavaScript.")
            except:
                # Fallback to regular click with scroll
                actions.move_to_element(all_filters_btn).perform()
                buffer(0.5)
                all_filters_btn.click()
                print_lg("Clicked 'All filters' button.")
        else:
            print_lg("Failed to find 'All filters' button, skipping filters!")
            return

        modal_root = None
        try:
            modal_xpath = "//div[@role='dialog'] | //div[contains(@class, 'artdeco-modal')] | //div[contains(@class, 'all-filters')] | //aside[contains(@class, 'artdeco-sidebar')]"
            modal_root = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.XPATH, modal_xpath)))
            buffer(2)
            print_lg("Modal/Sidebar detected. Proceeding with filter selection.")
        except:
            print_lg("Warning: Modal/Sidebar content not found, searching globally.")

        def scraper_debug_log(filter_name):
            if modal_root:
                print_lg(f"DEBUG: Failed to find '{filter_name}'.")
                txt = modal_root.text.strip()
                if not txt or len(txt) < 10:
                    html = modal_root.get_attribute('innerHTML')
                    print_lg(f"Modal '.text' is effectively empty. Full innerHTML length: {len(html)}")
                    print_lg("--- MODAL HTML START ---")
                    print_lg(html[:5000])
                    print_lg("--- MODAL HTML END ---")
                else:
                    print_lg("--- MODAL TEXT START ---")
                    print_lg(txt)
                    print_lg("--- MODAL TEXT END ---")
            else:
                print_lg(f"DEBUG: Failed to find '{filter_name}' and no modal_root was identified.")

        try:
            if sort_by: 
                if not wait_span_click(driver, sort_by, 2, root=modal_root): scraper_debug_log(sort_by)
            if date_posted: 
                if not wait_span_click(driver, date_posted, 2, root=modal_root): scraper_debug_log(date_posted)
            buffer(recommended_wait)
        except Exception as e: print_lg(f"Error applying sort/date filters: {e}")

        try:
            if experience_level: 
                try: multi_sel_noWait(driver, experience_level, root=modal_root)
                except: scraper_debug_log(experience_level)
            if companies: 
                try: multi_sel_noWait(driver, companies, actions, root=modal_root)
                except: scraper_debug_log(companies)
            if experience_level or companies: buffer(recommended_wait)
        except Exception as e: print_lg(f"Error applying experience/company filters: {e}")

        try:
            if job_type: multi_sel_noWait(driver, job_type, root=modal_root)
            if on_site: multi_sel_noWait(driver, on_site, root=modal_root)
            if job_type or on_site: buffer(recommended_wait)
        except Exception as e: print_lg(f"Error applying type/site filters: {e}")

        try:
            if easy_apply_only: boolean_button_click(driver, actions, "Easy Apply")
        except: pass
        
        try:
            if location: multi_sel_noWait(driver, location, root=modal_root)
            if industry: multi_sel_noWait(driver, industry, root=modal_root)
            if location or industry: buffer(recommended_wait)
        except: pass

        try:
            if salary: 
                if not wait_span_click(driver, salary, 2, root=modal_root): scraper_debug_log(salary)
            buffer(recommended_wait)
        except: pass

        try:
            show_results_xpath = './/button[contains(., "results") or contains(., "Results") or contains(@aria-label, "results") or contains(., "Apply") or contains(., "Show")] | //button[contains(@class, "search-reusables__all-filters-button--primary")] | //button[contains(@aria-label, "Apply")]'
            search_base = modal_root if modal_root else driver
            # Try multiple approaches for overlapping elements
            try:
                WebDriverWait(driver, 2).until(EC.invisibility_of_element_located((By.CLASS_NAME, "jobs-search-box__search-starter")))
            except:
                actions.send_keys(Keys.ESCAPE).perform()
                buffer(0.5)
            
            show_results_button = WebDriverWait(search_base, 3).until(EC.element_to_be_clickable((By.XPATH, show_results_xpath)))
            
            # Try JavaScript click first
            try:
                driver.execute_script("arguments[0].click();", show_results_button)
                print_lg("Applied filters successfully using JavaScript.")
            except:
                # Fallback to regular click
                actions.move_to_element(show_results_button).perform()
                buffer(0.5)
                show_results_button.click()
                print_lg("Applied filters successfully.")
        except:
            print_lg("Failed to find 'Show results' button within modal, trying generic fallbacks...")
            if not try_xp(driver, "//button[contains(., 'Show results')]"):
                if not try_xp(driver, "//button[contains(., 'Apply')]"):
                    actions.send_keys(Keys.ENTER).perform()
                    print_lg("Sent ENTER key as fallback for Show results.")
    except Exception as e:
        print_lg("Setting the preferences failed!", e)

def get_page_info() -> tuple[WebElement | None, int | None]:
    try:
        pagination_element = try_find_by_classes(driver, ["jobs-search-pagination__pages", "artdeco-pagination", "artdeco-pagination__pages", "jobs-search-results-list__pagination"])
        if not pagination_element:
            pagination_element = driver.find_element(By.XPATH, "//div[contains(@class, 'pagination')] | //ul[contains(@class, 'pagination')]")
            
        scroll_to_view(driver, pagination_element)
        current_page_elem = pagination_element.find_element(By.XPATH, ".//li[contains(@class, 'active')] | .//button[contains(@aria-current, 'true')]")
        current_page = int(current_page_elem.text.strip())
        return pagination_element, current_page
    except Exception:
        return None, None

def get_job_main_details(job: WebElement, blacklisted_companies: set, rejected_jobs: set) -> tuple[str, str, str, str, str, bool]:
    skip = False
    job_details_button = None
    try:
        # Try multiple selectors for job details button/link
        job_details_selectors = [
            (By.CLASS_NAME, 'job-card-list__title'),
            (By.CLASS_NAME, 'job-card-container__link'),
            (By.CLASS_NAME, 'base-card__full-link'),
            (By.CSS_SELECTOR, 'a.job-card-list__title'),
            (By.CSS_SELECTOR, 'a.job-card-container__link'),
            (By.CSS_SELECTOR, 'a.base-card__full-link'),
            (By.CSS_SELECTOR, '.job-card-list__title--link'),
            (By.XPATH, './/a[contains(@href, "/jobs/view/")]'),
            (By.XPATH, './/a[contains(@class, "job-card")]'),
            (By.XPATH, './/a'),
        ]
        
        # Check if the 'job' element itself is a link
        try:
            if job.tag_name == 'a' and job.get_attribute('href'):
                job_details_button = job
        except:
            pass

        if not job_details_button:
            for by, selector in job_details_selectors:
                try:
                    job_details_button = job.find_element(by, selector)
                    if job_details_button and job_details_button.get_attribute('href'):
                        break
                    job_details_button = None
                except:
                    continue
        
        if not job_details_button:
            # Broad fallback: find first <a> with href containing /jobs/view/
            try:
                all_links = job.find_elements(By.TAG_NAME, 'a')
                for link in all_links:
                    href = link.get_attribute('href')
                    if href and '/jobs/view/' in href:
                        job_details_button = link
                        break
                if not job_details_button and all_links:
                    for link in all_links:
                        if link.text.strip():
                            job_details_button = link
                            break
            except:
                pass

        if not job_details_button:
            print_lg(f'Failed to find job details button for a job listing. Tried {len(job_details_selectors)} selectors.')
            return ("Unknown", "Unknown", "Unknown", "Unknown", "Unknown", True)
            
        scroll_to_view(driver, job_details_button, True)
    except Exception as e:
        print_lg(f'Error finding job details button: {str(e)[:100]}')
        return ("Unknown", "Unknown", "Unknown", "Unknown", "Unknown", True)
    
    # Robust Job ID extraction
    job_id = job.get_dom_attribute('data-occludable-job-id') or job.get_dom_attribute('data-job-id')
    if not job_id:
        try:
            href = job_details_button.get_attribute('href')
            if href and '/view/' in href:
                import re
                match = re.search(r'/view/(\d+)', href)
                if match:
                    job_id = match.group(1)
        except:
            pass
    if not job_id: job_id = "Unknown"

    # Title extraction
    title = job_details_button.text.strip().split('\n')[0]
    
    # Company and Location extraction
    company = "Unknown"
    work_location = "Unknown"
    work_style = "Unknown"
    
    try:
        subtitle_selectors = [
            (By.CLASS_NAME, 'job-card-container__company-name'),
            (By.CLASS_NAME, 'base-search-card__subtitle'),
            (By.CLASS_NAME, 'artdeco-entity-lockup__subtitle'),
            (By.CSS_SELECTOR, '.job-card-container__primary-description'),
            (By.CLASS_NAME, 'job-card-v2__company-name'),
        ]
        
        other_details = "Unknown"
        for by, sel in subtitle_selectors:
            try:
                other_details = job.find_element(by, sel).text.strip()
                if other_details: break
            except: continue

        if ' · ' in other_details:
            parts = other_details.split(' · ')
            company = parts[0].strip()
            work_location = parts[1].strip() if len(parts) > 1 else "Unknown"
        else:
            company = other_details
            # Fallback for location
            try:
                work_location = job.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text.strip()
            except:
                try:
                    work_location = job.find_element(By.CLASS_NAME, 'job-search-card__location').text.strip()
                except:
                    pass
    except:
        pass

    if '(' in work_location and ')' in work_location:
        work_style = work_location[work_location.rfind('(')+1:work_location.rfind(')')]
        work_location = work_location[:work_location.rfind('(')].strip()
    
    if company in blacklisted_companies:
        print_lg(f'Skipping "{title} | {company}" job (Blacklisted Company). Job ID: {job_id}!')
        skip = True
    elif job_id in rejected_jobs: 
        print_lg(f'Skipping previously rejected "{title} | {company}" job. Job ID: {job_id}!')
        skip = True
    
    try:
        if not skip:
            # Check if already applied via footer
            try:
                footer = job.find_element(By.CLASS_NAME, "job-card-container__footer-job-state")
                if "Applied" in footer.text:
                    skip = True
                    print_lg(f'Already applied to "{title} | {company}" job. Job ID: {job_id}!')
            except: pass

        if not skip:
            # Clear overlapping search starter if present
            try:
                WebDriverWait(driver, 1).until(EC.invisibility_of_element_located((By.CLASS_NAME, "jobs-search-box__search-starter")))
            except:
                actions.send_keys(Keys.ESCAPE).perform()
                buffer(0.5)

            # Try to click the job to show details
            try:
                # Try JavaScript click first (most reliable for LinkedIn's complex UI)
                driver.execute_script("arguments[0].click();", job_details_button)
            except:
                try:
                    # Fallback to physical click
                    scroll_to_view(driver, job_details_button)
                    actions.move_to_element(job_details_button).click().perform()
                except:
                    # Final fallback
                    job_details_button.click()
            
            buffer(click_gap)
    except Exception as e:
        print_lg(f'Warning: Error while interacting with job "{title}": {str(e)[:100]}')
        # We don't necessarily skip here if the click might have worked anyway
        
    return (job_id, title, company, work_location, work_style, skip)

def check_blacklist(rejected_jobs: set, job_id: str, company: str, blacklisted_companies: set) -> tuple[set, set, WebElement] | ValueError:
    try:
        jobs_top_card = try_find_by_classes(driver, ["job-details-jobs-unified-top-card__primary-description-container","job-details-jobs-unified-top-card__primary-description","jobs-unified-top-card__primary-description","jobs-details__main-content", "job-details-module", "job-details-about-the-job-module__description"])
    except:
        print_lg("Warning: Could not find main job details pane, but continuing...")
        jobs_top_card = driver.find_element(By.TAG_NAME, "body")

    try:
        about_company_org = find_by_class(driver, "jobs-company__box")
        scroll_to_view(driver, about_company_org)
        about_company_org = about_company_org.text
    except:
        about_company_org = "Unknown"
    about_company = about_company_org.lower()
    skip_checking = False
    for word in about_company_good_words:
        if word.lower() in about_company:
            print_lg(f'Found the word "{word}". So, skipped checking for blacklist words.')
            skip_checking = True
            break
    if not skip_checking:
        for word in about_company_bad_words: 
            if word.lower() in about_company: 
                rejected_jobs.add(job_id)
                blacklisted_companies.add(company)
                raise ValueError(f'\n"{about_company_org}"\n\nContains "{word}".')
    buffer(click_gap)
    try: scroll_to_view(driver, jobs_top_card)
    except: pass
    return rejected_jobs, blacklisted_companies, jobs_top_card

def extract_years_of_experience(text: str) -> int:
    matches = re.findall(re_experience, text)
    if len(matches) == 0: 
        print_lg(f'\n{text}\n\nCouldn\'t find experience requirement in About the Job!')
        return 0
    return max([int(match) for match in matches if int(match) <= 12])

def get_job_description() -> tuple[str | Literal['Unknown'], int | Literal['Unknown'], bool, str | None, str | None]:
    jobDescription = "Unknown"
    experience_required = "Unknown"
    skip = False
    skipReason = None
    skipMessage = None
    try:
        found_masters = 0
        # Wait for job details page to load after clicking
        buffer(3)
        
        # Try multiple selectors for job description
        description_elements = [
            (By.CLASS_NAME, "jobs-description-content__text"),
            (By.ID, "job-details"),
            (By.CLASS_NAME, "jobs-box__html-content"),
            (By.CLASS_NAME, "show-more-less-html__markup"),
            (By.CLASS_NAME, "jobs-description__text"),
            (By.CLASS_NAME, "jobs-search-results__job-description"),
            (By.ID, "main"),
            (By.XPATH, "//div[contains(@class, 'job-description')]//div[contains(@class, 'html')]"),
            (By.XPATH, "//article[contains(@class, 'jobs-description__container')]"),
            (By.XPATH, "//div[contains(@class, 'jobs-description')]//div[contains(@class, 'jobs-description__content')]"),
            (By.XPATH, "//section[contains(@class, 'description')]//div[contains(@class, 'show-more-less')]"),
            (By.CSS_SELECTOR, ".jobs-description__content .jobs-description__text"),
            (By.CSS_SELECTOR, ".jobs-box__html-content"),
            (By.CSS_SELECTOR, "#job-details"),
            (By.XPATH, "//div[@data-test-id='job-details']//span[contains(@class, 'visually-hidden')]/.."),
            (By.XPATH, "//div[contains(@class, 'jobs-description-content')]")
        ]
        
        jobDescription = "Unknown"
        print_lg("Attempting to extract job description...")
        
        for by, sel in description_elements:
            try:
                # Wait for element to be present
                element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, sel)))
                jobDescription = element.text
                if jobDescription and len(jobDescription.strip()) > 50: 
                    print_lg(f"✅ Successfully extracted job description using selector: {sel}")
                    break
            except Exception as e:
                continue
            
        if not jobDescription or jobDescription == "Unknown" or len(jobDescription.strip()) < 50:
            print_lg("❌ Unable to extract job description! Using minimal description for application.")
            # Debug: Show what elements we can find
            try:
                all_divs = driver.find_elements(By.TAG_NAME, "div")
                print_lg(f"Found {len(all_divs)} div elements on page")
                relevant_divs = [div for div in all_divs if any(keyword in div.get_attribute('class', '').lower() for keyword in ['description', 'detail', 'content'])]
                print_lg(f"Found {len(relevant_divs)} potentially relevant divs")
                for i, div in enumerate(relevant_divs[:3]):
                    class_name = div.get_attribute('class', '')
                    text_preview = div.text.strip()[:50] if div.text else 'No text'
                    print_lg(f"  Div {i+1}: class={class_name[:50]} text={text_preview}")
            except:
                pass
            jobDescription = "Job position available - applying for relevant role"

        jobDescriptionLow = jobDescription.lower()
        for word in bad_words:
            if word.lower() in jobDescriptionLow:
                skipMessage = f'\n{jobDescription}\n\nContains bad word "{word}". Skipping this job!\n'
                skipReason = "Found a Bad Word in About Job"
                skip = True
                break
        if not skip and security_clearance == False and ('polygraph' in jobDescriptionLow or 'clearance' in jobDescriptionLow or 'secret' in jobDescriptionLow):
            skipMessage = f'\n{jobDescription}\n\nFound "Clearance" or "Polygraph". Skipping this job!\n'
            skipReason = "Asking for Security clearance"
            skip = True
        if not skip:
            if did_masters and 'master' in jobDescriptionLow:
                print_lg(f'Found the word "master" in \n{jobDescription}')
                found_masters = 2
            experience_required = extract_years_of_experience(jobDescription)
            if current_experience > -1 and experience_required > current_experience + found_masters:
                skipMessage = f'\n{jobDescription}\n\nExperience required {experience_required} > Current Experience {current_experience + found_masters}. Skipping this job!\n'
                skipReason = "Required experience is high"
                skip = True
    except Exception as e:
        if jobDescription == "Unknown":    print_lg("Unable to extract job description!")
        else:
            experience_required = "Error in extraction"
            print_lg(f"Unable to extract years of experience required! (Error: {str(e)[:100]})")
            if jobDescription:
                print_lg(f"Debug: Job description snippet for parsing: {jobDescription[:200]}...")
    finally:
        return jobDescription, experience_required, skip, skipReason, skipMessage

def upload_resume(modal: WebElement, resume: str) -> tuple[bool, str]:
    try:
        if not resume:
            return False, "Previous resume"
        resume_abs = os.path.abspath(resume)
        if not os.path.isfile(resume_abs):
            return False, "Previous resume"
        modal.find_element(By.NAME, "file").send_keys(resume_abs)
        return True, os.path.basename(resume_abs)
    except: return False, "Previous resume"

def answer_common_questions(label: str, answer: str) -> str:
    if 'sponsorship' in label or 'visa' in label: answer = require_visa
    return answer

def answer_questions(modal: WebElement, questions_list: set, work_location: str, job_description: str | None = None ) -> set:
    all_questions = modal.find_elements(By.XPATH, ".//div[@data-test-form-element]")
    for Question in all_questions:
        select = try_xp(Question, ".//select", False)
        if select:
            label_org = "Unknown"
            try:
                label = Question.find_element(By.TAG_NAME, "label")
                label_org = label.find_element(By.TAG_NAME, "span").text
            except: pass
            answer = 'Yes'
            label = label_org.lower()
            select = Select(select)
            selected_option = select.first_selected_option.text
            optionsText = []
            options = '"List of phone country codes"'
            if label != "phone country code":
                optionsText = [option.text for option in select.options]
                options = "".join([f' "{option}",' for option in optionsText])
            prev_answer = selected_option
            if overwrite_previous_answers or selected_option == "Select an option":
                if 'email' in label or 'phone' in label: 
                    answer = prev_answer
                elif 'gender' in label or 'sex' in label: 
                    answer = gender
                elif 'disability' in label: 
                    answer = disability_status
                elif 'proficiency' in label: 
                    answer = 'Professional'
                elif any(loc_word in label for loc_word in ['location', 'city', 'state', 'country']):
                    if 'country' in label:
                        answer = country 
                    elif 'state' in label:
                        answer = state
                    elif 'city' in label:
                        answer = current_city if current_city else work_location
                    else:
                        answer = work_location
                else: 
                    answer = answer_common_questions(label,answer)
                try: 
                    select.select_by_visible_text(answer)
                except NoSuchElementException:
                    possible_answer_phrases = []
                    if answer == 'Decline':
                        possible_answer_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"]
                    elif 'yes' in answer.lower():
                        possible_answer_phrases = ["Yes", "Agree", "I do", "I have"]
                    elif 'no' in answer.lower():
                        possible_answer_phrases = ["No", "Disagree", "I don't", "I do not"]
                    else:
                        possible_answer_phrases = [answer, answer.lower(), answer.upper(), ''.join(c for c in answer if c.isalnum())]
                    foundOption = False
                    for phrase in possible_answer_phrases:
                        for option in optionsText:
                            if phrase.lower() in option.lower() or option.lower() in phrase.lower():
                                select.select_by_visible_text(option)
                                answer = option
                                foundOption = True
                                break
                    if not foundOption:
                        print_lg(f'Failed to find an option with text "{answer}" for question labelled "{label_org}", answering randomly!')
                        select.select_by_index(randint(1, len(select.options)-1))
                        answer = select.first_selected_option.text
                        randomly_answered_questions.add((f'{label_org} [ {options} ]',"select"))
            questions_list.add((f'{label_org} [ {options} ]', answer, "select", prev_answer))
            continue
        
        radio = try_xp(Question, './/fieldset[@data-test-form-builder-radio-button-form-component="true"]', False)
        if radio:
            prev_answer = None
            label = try_xp(radio, './/span[@data-test-form-builder-radio-button-form-component__title]', False)
            try: label = find_by_class(label, "visually-hidden", 2.0)
            except: pass
            label_org = label.text if label else "Unknown"
            answer = 'Yes'
            label = label_org.lower()
            label_org += ' [ '
            options = radio.find_elements(By.TAG_NAME, 'input')
            options_labels = []
            for option in options:
                id = option.get_attribute("id")
                option_label = try_xp(radio, f'.//label[@for="{id}"]', False)
                options_labels.append( f'"{option_label.text if option_label else "Unknown"}"<{option.get_attribute("value")}>' )
                if option.is_selected(): prev_answer = options_labels[-1]
                label_org += f' {options_labels[-1]},'
            if overwrite_previous_answers or prev_answer is None:
                if 'citizenship' in label or 'employment eligibility' in label: answer = us_citizenship
                elif 'veteran' in label or 'protected' in label: answer = veteran_status
                elif 'disability' in label or 'handicapped' in label: 
                    answer = disability_status
                else: answer = answer_common_questions(label,answer)
                foundOption = try_xp(radio, f".//label[normalize-space()='{answer}']", False)
                if foundOption: 
                    actions.move_to_element(foundOption).click().perform()
                else:    
                    possible_answer_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"] if answer == 'Decline' else [answer]
                    ele = options[0]
                    answer = options_labels[0]
                    for phrase in possible_answer_phrases:
                        for i, option_label in enumerate(options_labels):
                            if phrase in option_label:
                                foundOption = options[i]
                                ele = foundOption
                                answer = f'Decline ({option_label})' if len(possible_answer_phrases) > 1 else option_label
                                break
                        if foundOption: break
                    actions.move_to_element(ele).click().perform()
                    if not foundOption: randomly_answered_questions.add((f'{label_org} ]',"radio"))
            else: answer = prev_answer
            questions_list.add((label_org+" ]", answer, "radio", prev_answer))
            continue
        
        text = try_xp(Question, ".//input[@type='text']", False)
        if text: 
            do_actions = False
            label = try_xp(Question, ".//label[@for]", False)
            try: label = label.find_element(By.CLASS_NAME,'visually-hidden')
            except: pass
            label_org = label.text if label else "Unknown"
            answer = ""
            label = label_org.lower()
            prev_answer = text.get_attribute("value")
            if not prev_answer or overwrite_previous_answers:
                if 'experience' in label or 'years' in label: answer = years_of_experience
                elif 'phone' in label or 'mobile' in label: answer = phone_number
                elif 'street' in label: answer = street
                elif 'city' in label or 'location' in label or 'address' in label:
                    answer = current_city if current_city else work_location
                    do_actions = True
                elif 'signature' in label: answer = full_name
                elif 'name' in label:
                    if 'full' in label: answer = full_name
                    elif 'first' in label and 'last' not in label: answer = first_name
                    elif 'middle' in label and 'last' not in label: answer = middle_name
                    elif 'last' in label and 'first' not in label: answer = last_name
                    elif 'employer' in label: answer = recent_employer
                    else: answer = full_name
                elif 'notice' in label:
                    if 'month' in label:
                        answer = notice_period_months
                    elif 'week' in label:
                        answer = notice_period_weeks
                    else: answer = notice_period
                elif 'salary' in label or 'compensation' in label or 'ctc' in label or 'pay' in label: 
                    if 'current' in label or 'present' in label:
                        if 'month' in label:
                            answer = current_ctc_monthly
                        elif 'lakh' in label:
                            answer = current_ctc_lakhs
                        else:
                            answer = current_ctc
                    else:
                        if 'month' in label:
                            answer = desired_salary_monthly
                        elif 'lakh' in label:
                            answer = desired_salary_lakhs
                        else:
                            answer = desired_salary
                elif 'linkedin' in label: answer = linkedIn
                elif 'website' in label or 'blog' in label or 'portfolio' in label or 'link' in label: answer = website
                elif 'scale of 1-10' in label: answer = confidence_level
                elif 'headline' in label: answer = linkedin_headline
                elif ('hear' in label or 'come across' in label) and 'this' in label and ('job' in label or 'position' in label): answer = "https://github.com/GodsScion/Auto_job_applier_linkedIn"
                elif 'state' in label or 'province' in label: answer = state
                elif 'zip' in label or 'postal' in label or 'code' in label: answer = zipcode
                elif 'country' in label: answer = country
                else: answer = answer_common_questions(label,answer)
                if answer == "":
                    if aiClient:
                        try:
                            if ai_provider.lower() == "openai":
                                from modules.ai.openaiConnections import ai_answer_question
                                answer = ai_answer_question(aiClient, label_org, question_type="text", job_description=job_description, user_information_all=user_information_all)
                            elif ai_provider.lower() == "deepseek":
                                from modules.ai.deepseekConnections import deepseek_answer_question
                                answer = deepseek_answer_question(aiClient, label_org, options=None, question_type="text", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            elif ai_provider.lower() == "gemini":
                                from modules.ai.geminiConnections import gemini_answer_question
                                answer = gemini_answer_question(aiClient, label_org, options=None, question_type="text", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            else:
                                randomly_answered_questions.add((label_org, "text"))
                                answer = years_of_experience
                            if not answer or not isinstance(answer, str) or len(answer) == 0:
                                randomly_answered_questions.add((label_org, "text"))
                                answer = years_of_experience
                        except:
                            randomly_answered_questions.add((label_org, "text"))
                            answer = years_of_experience
                    else:
                        randomly_answered_questions.add((label_org, "text"))
                        answer = years_of_experience
                text.clear()
                text.send_keys(answer)
                if do_actions:
                    sleep(2)
                    actions.send_keys(Keys.ARROW_DOWN)
                    actions.send_keys(Keys.ENTER).perform()
            questions_list.add((label, text.get_attribute("value"), "text", prev_answer))
            continue
        
        text_area = try_xp(Question, ".//textarea", False)
        if text_area:
            label = try_xp(Question, ".//label[@for]", False)
            label_org = label.text if label else "Unknown"
            label = label_org.lower()
            answer = ""
            prev_answer = text_area.get_attribute("value")
            if not prev_answer or overwrite_previous_answers:
                if 'summary' in label: answer = linkedin_summary
                elif 'cover' in label: answer = cover_letter
                if answer == "":
                    if aiClient:
                        try:
                            if ai_provider.lower() == "openai":
                                from modules.ai.openaiConnections import ai_answer_question
                                answer = ai_answer_question(aiClient, label_org, question_type="textarea", job_description=job_description, user_information_all=user_information_all)
                            elif ai_provider.lower() == "deepseek":
                                from modules.ai.deepseekConnections import deepseek_answer_question
                                answer = deepseek_answer_question(aiClient, label_org, options=None, question_type="textarea", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            elif ai_provider.lower() == "gemini":
                                from modules.ai.geminiConnections import gemini_answer_question
                                answer = gemini_answer_question(aiClient, label_org, options=None, question_type="textarea", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            else:
                                randomly_answered_questions.add((label_org, "textarea"))
                                answer = ""
                            if not answer or not isinstance(answer, str) or len(answer) == 0:
                                randomly_answered_questions.add((label_org, "textarea"))
                                answer = ""
                        except:
                            randomly_answered_questions.add((label_org, "textarea"))
                            answer = ""
                    else:
                        randomly_answered_questions.add((label_org, "textarea"))
            text_area.clear()
            text_area.send_keys(answer)
            if do_actions:
                    sleep(2)
                    actions.send_keys(Keys.ARROW_DOWN)
                    actions.send_keys(Keys.ENTER).perform()
            questions_list.add((label, text_area.get_attribute("value"), "textarea", prev_answer))
            continue

        checkbox = try_xp(Question, ".//input[@type='checkbox']", False)
        if checkbox:
            label = try_xp(Question, ".//span[@class='visually-hidden']", False)
            label_org = label.text if label else "Unknown"
            label = label_org.lower()
            answer = try_xp(Question, ".//label[@for]", False)
            answer = answer.text if answer else "Unknown"
            prev_answer = checkbox.is_selected()
            checked = prev_answer
            if not prev_answer:
                try:
                    actions.move_to_element(checkbox).click().perform()
                    checked = True
                except: pass
            questions_list.add((f'{label} ([X] {answer})', checked, "checkbox", prev_answer))
            continue
    try_xp(driver, "//button[contains(@aria-label, 'This is today')]")
    return questions_list

def external_apply(pagination_element: WebElement, job_id: str, job_link: str, resume: str, date_listed, application_link: str, screenshot_name: str) -> tuple[bool, str, int]:
    global tabs_count, dailyEasyApplyLimitReached
    if easy_apply_only:
        try:
            if "exceeded the daily application limit" in driver.find_element(By.CLASS_NAME, "artdeco-inline-feedback__message").text: dailyEasyApplyLimitReached = True
        except: pass
        print_lg("Easy apply failed I guess!")
        if pagination_element != None: return True, application_link, tabs_count
    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3')]"))).click()
        wait_span_click(driver, "Continue", 1, True, False)
        windows = driver.window_handles
        tabs_count = len(windows)
        driver.switch_to.window(windows[-1])
        application_link = driver.current_url
        print_lg('Got the external application link "{}"'.format(application_link))
        if close_tabs and driver.current_window_handle != linkedIn_tab: driver.close()
        driver.switch_to.window(linkedIn_tab)
        return False, application_link, tabs_count
    except Exception as e:
        print_lg("Failed to apply!")
        save_failed_job(job_id, job_link, resume, date_listed, "Probably didn't find Apply button or unable to switch tabs.", e, application_link, screenshot_name)
        return True, application_link, tabs_count

def follow_company(modal: WebDriver = driver) -> None:
    try:
        follow_checkbox_input = try_xp(modal, ".//input[@id='follow-company-checkbox' and @type='checkbox']", False)
        if follow_checkbox_input and follow_checkbox_input.is_selected() != follow_companies:
            try_xp(modal, ".//label[@for='follow-company-checkbox']")
    except Exception as e:
        print_lg("Failed to update follow companies checkbox!", e)


def discard_job() -> None:
    try:
        actions.send_keys(Keys.ESCAPE).perform()
        buffer(0.5)
        # Try multiple ways to find the discard button
        discard_selectors = [
            "//button[contains(@aria-label, 'Discard')]",
            "//button[contains(text(), 'Discard')]",
            "//span[contains(text(), 'Discard')]/ancestor::button",
            "//button[contains(@class, 'discard')]",
            "//button[contains(@class, 'skip')]"
        ]
        
        for selector in discard_selectors:
            try:
                discard_btn = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, selector)))
                discard_btn.click()
                buffer(click_gap)
                return
            except:
                continue
                
        # If no discard button found, try clicking outside
        actions.send_keys(Keys.ESCAPE).perform()
    except Exception as e:
        print_lg("Could not find discard button, continuing...")
        pass

def build_search_url(keyword: str) -> str:
    """Build LinkedIn job search URL with all filters encoded as query parameters.
    
    This approach prevents LinkedIn from overriding the search keyword when 
    filters are applied via the UI modal (which was causing 'React Developer' searches).
    
    LinkedIn URL parameters:
    - keywords: search term
    - location: geographic filter
    - f_E: experience level (1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive)
    - f_JT: job type (F=Full-time, P=Part-time, C=Contract, T=Temporary, V=Volunteer, I=Internship, O=Other)
    - f_WT: work type (1=On-site, 2=Remote, 3=Hybrid)
    - f_TPR: time posted (r86400=24h, r604800=week, r2592000=month)
    - f_AL: easy apply (true)
    - sortBy: DD=Most recent, R=Most relevant
    - geoId: LinkedIn geo ID (102713980=India)
    """
    from urllib.parse import quote_plus
    
    url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(keyword)}"
    
    # Location
    if search_location:
        url += f"&location={quote_plus(search_location)}"
        # Common geoIds: India=102713980, US=103644278, UK=101165590
        geo_map = {
            "india": "102713980", "united states": "103644278", "united kingdom": "101165590",
            "canada": "101174742", "australia": "101452733", "germany": "101282230",
        }
        geo_id = geo_map.get(search_location.strip().lower(), "")
        if geo_id:
            url += f"&geoId={geo_id}"
    
    # Experience level mapping
    exp_map = {
        "Internship": "1", "Entry level": "2", "Associate": "3",
        "Mid-Senior level": "4", "Director": "5", "Executive": "6"
    }
    if experience_level:
        exp_codes = [exp_map[e] for e in experience_level if e in exp_map]
        if exp_codes:
            url += f"&f_E={'%2C'.join(exp_codes)}"
    
    # Job type mapping
    jt_map = {
        "Full-time": "F", "Part-time": "P", "Contract": "C",
        "Temporary": "T", "Volunteer": "V", "Internship": "I", "Other": "O"
    }
    if job_type:
        jt_codes = [jt_map[j] for j in job_type if j in jt_map]
        if jt_codes:
            url += f"&f_JT={'%2C'.join(jt_codes)}"
    
    # Work type (on-site/remote/hybrid)
    wt_map = {"On-site": "1", "Remote": "2", "Hybrid": "3"}
    if on_site:
        wt_codes = [wt_map[w] for w in on_site if w in wt_map]
        if wt_codes:
            url += f"&f_WT={'%2C'.join(wt_codes)}"
    
    # Date posted
    tpr_map = {
        "Past 24 hours": "r86400", "Past week": "r604800", "Past month": "r2592000"
    }
    if date_posted and date_posted in tpr_map:
        url += f"&f_TPR={tpr_map[date_posted]}"
    
    # Easy apply filter
    if easy_apply_only:
        url += "&f_AL=true"
    
    # Sort order
    if sort_by == "Most recent":
        url += "&sortBy=DD"
    elif sort_by == "Most relevant":
        url += "&sortBy=R"
    
    # Force spell correction enabled for better results
    url += "&spellCorrectionEnabled=true"
    
    return url


def apply_to_jobs(search_terms: list[str], end_time: float = None) -> None:
    global current_city, failed_count, skip_count, easy_applied_count, external_jobs_count, tabs_count, dailyEasyApplyLimitReached, useNewResume, linkedIn_tab
    linkedIn_tab = driver.current_window_handle
    applied_jobs = get_applied_job_ids()
    rejected_jobs = set()
    blacklisted_companies = set()
    current_city = current_city.strip()

    if randomize_search_order:  shuffle(search_terms)
    # 1. Iterate through search terms
    for searchTerm in search_terms:
        if is_timeout(end_time):
            print_lg("Time limit reached for LinkedIn cycle. Rotating to next platform.")
            break

        # Build LinkedIn search URL with ALL filters encoded as query parameters.
        # This prevents LinkedIn from replacing the keyword with its own recommendations.
        search_url = build_search_url(searchTerm)
        robust_get(driver, search_url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'jobs-search-box__input')] | //li[@data-occludable-job-id]")))
        except:
            print_lg("Timed out waiting for search page to load, but continuing...")
        
        print_lg("\n" + "_"*120 + "\n")
        print_lg(f'\n>>>> Now searching for "{searchTerm}" <<<<\n\n')
        print_lg(f"Search URL: {search_url}")

        # No need to call apply_filters() — all filters are in the URL

        current_count = 0
        try:
            while current_count < switch_number:
                # Try multiple selectors for job listings
                job_listing_selectors = [
                    "//li[@data-occludable-job-id]",
                    "//div[contains(@class, 'job-search-card')]",
                    "//div[contains(@class, 'base-card')]",
                    "//div[contains(@class, 'job-card-container')]",
                    "//div[contains(@class, 'jobs-search-results__list-item')]",
                    "//ul[contains(@class, 'jobs-search-results__list')]/li",
                    "//div[@data-job-id]"
                ]
                
                job_listings = []
                for selector in job_listing_selectors:
                    try:
                        job_listings = driver.find_elements(By.XPATH, selector)
                        if job_listings:
                            break
                    except:
                        continue
                
                if not job_listings:
                    print_lg("No job listings found with any selector")
                    break
                    
                # Wait for at least one job listing to be fully loaded
                try:
                    WebDriverWait(driver, 5).until(lambda d: len(job_listings) > 0)
                except:
                    pass
                pagination_element, current_page = get_page_info()
                buffer(3)  

                for job in job_listings:
                    if keep_screen_awake: pyautogui.press('shiftright')
                    if current_count >= switch_number: break
                    print_lg("\n-@-\n")

                    job_id,title,company,work_location,work_style,skip = get_job_main_details(job, blacklisted_companies, rejected_jobs)
                    if skip: continue
                    try:
                        if job_id in applied_jobs or find_by_class(driver, "jobs-s-apply__application-link", 2):
                            print_lg(f'Already applied to "{title} | {company}" job. Job ID: {job_id}!')
                            continue
                    except:
                        print_lg(f'Trying to Apply to "{title} | {company}" job. Job ID: {job_id}')

                    job_link = "https://www.linkedin.com/jobs/view/"+job_id
                    application_link = "Easy Applied"
                    date_applied = "Pending"
                    hr_link = "Unknown"
                    hr_name = "Unknown"
                    connect_request = "In Development"
                    date_listed = "Unknown"
                    skills = "Needs an AI"
                    resume = "Pending"
                    reposted = False
                    questions_list = None
                    screenshot_name = "Not Available"

                    try:
                        rejected_jobs, blacklisted_companies, jobs_top_card = check_blacklist(rejected_jobs,job_id,company,blacklisted_companies)
                    except ValueError as e:
                        print_lg(e, 'Skipping this job!\n')
                        save_failed_job(job_id, job_link, resume, date_listed, "Found Blacklisted words in About Company", e, "Skipped", screenshot_name)
                        skip_count += 1
                        continue
                    except:
                        print_lg("Failed to scroll to About Company!")

                    try:
                        hr_info_card = WebDriverWait(driver,2).until(EC.presence_of_element_located((By.CLASS_NAME, "hirer-card__hirer-information")))
                        hr_link = hr_info_card.find_element(By.TAG_NAME, "a").get_attribute("href")
                        hr_name = hr_info_card.find_element(By.TAG_NAME, "span").text
                    except:
                        print_lg(f'HR info was not given for "{title}" with Job ID: {job_id}!')

                    try:
                        time_posted_ele = jobs_top_card.find_element(By.XPATH, './/*[contains(normalize-space(), " ago")]')
                        time_posted_text = time_posted_ele.text
                        if "Reposted" in time_posted_text:
                            reposted = True
                            time_posted_text = time_posted_text.replace("Reposted", "")
                        date_listed = calculate_date_posted(time_posted_text.strip())
                    except Exception as e:
                        print_lg("Failed to calculate the date posted! Using current time as fallback.",e)
                        date_listed = datetime.now()

                    description, experience_required, skip, reason, message = get_job_description()
                    if skip:
                        print_lg(message)
                        save_failed_job(job_id, job_link, resume, date_listed, reason, message, "Skipped", screenshot_name)
                        rejected_jobs.add(job_id)
                        skip_count += 1
                        continue

                    if aiClient and description != "Unknown":
                        try:
                            if ai_provider.lower() == "openai":
                                from modules.ai.openaiConnections import ai_extract_skills
                                skills = ai_extract_skills(aiClient, description)
                            elif ai_provider.lower() == "deepseek":
                                from modules.ai.deepseekConnections import deepseek_extract_skills
                                skills = deepseek_extract_skills(aiClient, description)
                            elif ai_provider.lower() == "gemini":
                                from modules.ai.geminiConnections import gemini_extract_skills
                                skills = gemini_extract_skills(aiClient, description)
                            else:
                                skills = "In Development"
                            print_lg(f"Extracted skills using {ai_provider} AI")
                        except Exception as e:
                            print_lg("Failed to extract skills:", e)
                            skills = "Error extracting skills"

                    uploaded = False
                    easy_apply_btn = None
                    easy_apply_selectors = [
                        (By.XPATH, ".//button[contains(@class,'jobs-apply-button') and contains(., 'Easy')]"),
                        (By.XPATH, "//button[contains(@aria-label, 'Easy Apply')]"),
                        (By.XPATH, "//span[contains(text(), 'Easy Apply')]/ancestor::button"),
                        (By.CSS_SELECTOR, "button.jobs-apply-button")
                    ]
                    
                    for by, sel in easy_apply_selectors:
                        try:
                            easy_apply_btn = driver.find_element(by, sel)
                            if easy_apply_btn: break
                        except: continue

                    if easy_apply_btn:
                        try:
                            # Scroll and try to click
                            scroll_to_view(driver, easy_apply_btn)
                            try:
                                easy_apply_btn.click()
                            except:
                                driver.execute_script("arguments[0].click();", easy_apply_btn)
                            buffer(click_gap)
                            
                            errored = ""
                            modal = find_by_class(driver, "jobs-easy-apply-modal")
                            if not modal:
                                print_lg("Could not find 'jobs-easy-apply-modal', trying 'artdeco-modal'")
                                modal = find_by_class(driver, "artdeco-modal")
                            
                            if not modal:
                                raise Exception("Could not find Easy Apply modal after clicking Apply")
                            
                            print_lg("Easy Apply modal detected, proceeding...")
                            # Try multiple approaches to find Next button
                            next_selectors = [
                                ".//button[contains(span, 'Next')]",
                                ".//button[contains(@aria-label, 'Next')]",
                                ".//button[contains(., 'Next')]",
                                ".//span[contains(text(), 'Next')]/ancestor::button",
                                ".//button[contains(@class, 'next')]",
                                ".//button[contains(@id, 'next-button')]",
                                ".//button[contains(., 'Review')]",
                                ".//button[contains(@aria-label, 'Review')]"
                            ]
                            
                            next_found = False
                            for selector in next_selectors:
                                try:
                                    next_btn = WebDriverWait(modal, 2).until(EC.element_to_be_clickable((By.XPATH, selector)))
                                    if next_btn:
                                        next_found = True
                                        print_lg(f"Found initial Next/Review button with selector: {selector}")
                                        break
                                except:
                                    continue
                            
                            if not next_found:
                                print_lg("No Next button found, proceeding with questions")
                            
                            resume = "Previous resume"
                            next_button = True
                            questions_list = set()
                            next_counter = 0
                            while next_button:
                                next_counter += 1
                                if next_counter >= 15: 
                                    if pause_at_failed_question:
                                        screenshot(driver, job_id, "Needed manual intervention for failed question")
                                        print_lg("Couldn't answer one or more questions. Skipping as automation is preferred.")
                                        break
                                    if questions_list: print_lg("Stuck for one or some of the following questions...", questions_list)
                                    screenshot_name = screenshot(driver, job_id, "Failed at questions")
                                    errored = "stuck"
                                    print_lg(f"Loop detected at Step {next_counter}. Possible causes: Required question not answered or 'Next' button not advancing.")
                                    raise Exception(f"Seems like stuck in a continuous loop of next ({next_counter} attempts).")
                                
                                print_lg(f"Easy Apply Step {next_counter}: Answering questions...")
                                questions_list = answer_questions(modal, questions_list, work_location, job_description=description)
                                if useNewResume and not uploaded: uploaded, resume = upload_resume(modal, default_resume_path)
                                
                                # Try to find Next or Review button with multiple selectors
                                next_button = None
                                next_selectors = [
                                    './/span[normalize-space(.)="Review"]',
                                    './/span[normalize-space(.)="Review your application"]',
                                    './/button[contains(span, "Next")]',
                                    './/button[contains(span, "Review")]',
                                    './/button[contains(@aria-label, "Next")]',
                                    './/button[contains(@aria-label, "Review")]',
                                    './/button[contains(., "Next")]',
                                    './/button[contains(., "Review")]',
                                    './/span[contains(text(), "Next")]/ancestor::button',
                                    './/span[contains(text(), "Review")]/ancestor::button',
                                    './/button[contains(@class, "next")]',
                                    './/button[contains(@class, "review")]',
                                    './/button[contains(@id, "next-button")]'
                                ]
                                
                                for selector in next_selectors:
                                    try:
                                        next_button = modal.find_element(By.XPATH, selector)
                                        break
                                    except NoSuchElementException:
                                        continue
                                
                                if next_button:
                                    try: 
                                        next_button.click()
                                    except ElementClickInterceptedException: 
                                        break
                                else:
                                    # No more Next buttons found, exit the loop
                                    next_button = False
                                    break
                                buffer(click_gap)
                            
                            if questions_list and errored != "stuck": 
                                print_lg("Answered the following questions...", questions_list)
                            wait_span_click(driver, "Review", 1, scrollTop=True, root=modal)
                            
                            follow_company(modal)
                            submitted = False
                            for btn_text in ["Submit application", "Submit Application", "Submit", "Review your application", "Review"]:
                                if wait_span_click(driver, btn_text, 1, scrollTop=True, root=modal):
                                    submitted = True
                                    print_lg(f"Clicked '{btn_text}' button.")
                                    break
                            
                            if not submitted:
                                submit_selectors = [
                                    ".//button[contains(@class, 'artdeco-button--primary') and contains(., 'Submit')]",
                                    ".//button[contains(., 'Submit application')]",
                                    ".//button[contains(., 'Submit Application')]",
                                    ".//button[contains(., 'Submit')]",
                                    ".//span[normalize-space()='Submit application']/ancestor::button",
                                    "//button[contains(@aria-label, 'Submit application')]",
                                    "//button[contains(@aria-label, 'Submit')]",
                                    "//button[contains(span, 'Submit')]"
                                ]
                                for selector in submit_selectors:
                                    try:
                                        submit_btn = modal.find_element(By.XPATH, selector)
                                        if submit_btn:
                                            try:
                                                submit_btn.click()
                                            except:
                                                driver.execute_script("arguments[0].click();", submit_btn)
                                            submitted = True
                                            break
                                    except: continue

                            if submitted:
                                date_applied = datetime.now()
                                if not wait_span_click(driver, "Done", 2): 
                                    if not wait_span_click(driver, "Close", 2):
                                        actions.send_keys(Keys.ESCAPE).perform()
                            elif errored != "stuck":
                                print_lg("Submit Application button not found, but continuing as automation is preferred.")
                            else:
                                print_lg("Since, Submit Application failed or bot was stuck, discarding the job application...")
                                if errored == "nose": raise Exception("Failed to find Submit Application button")
                        except Exception as e:
                            print_lg(f"Failed to Easy apply! Error in Step {next_counter if 'next_counter' in locals() else 'initial'}")
                            critical_error_log("Somewhere in Easy Apply process",e)
                            save_failed_job(job_id, job_link, resume, date_listed, "Problem in Easy Applying", e, application_link, screenshot_name)
                            failed_count += 1
                            discard_job()
                            continue
                    else:
                        skip, application_link, tabs_count = external_apply(pagination_element, job_id, job_link, resume, date_listed, application_link, screenshot_name)
                        if dailyEasyApplyLimitReached:
                            print_lg("\n###############  Daily application limit for Easy Apply is reached!  ###############\n")
                            return
                        if skip: continue

                    if date_applied == "Pending": date_applied = datetime.now()
                    if submitted:
                        save_submitted_job(job_id, title, company, work_location, work_style, description, experience_required, skills, hr_name, hr_link, resume, reposted, date_listed, date_applied, job_link, application_link, questions_list, connect_request)
                        if uploaded:   useNewResume = False
                        print_lg(f'Successfully saved "{title} | {company}" job. Job ID: {job_id} info')
                        current_count += 1
                        if application_link == "Easy Applied": easy_applied_count += 1
                        else:   external_jobs_count += 1
                        applied_jobs.add(job_id)
                    else:
                        print_lg(f'Discarded "{title} | {company}" job instance. Job ID: {job_id} (Not Applied - Submission failed)')
                else:
                    print_lg(f'Discarded "{title} | {company}" job instance. Job ID: {job_id} (Not Applied)')

                if pagination_element is None:
                    print_lg("Couldn't find pagination element, probably at the end page of results!")
                    break
                    
                try:
                    # Attempt to find the next page button using multiple robust selectors
                    next_page = current_page + 1
                    next_page_selectors = [
                        f".//button[@aria-label='Page {next_page}']",
                        f".//a[@aria-label='Page {next_page}']",
                        f".//button[text()='{next_page}']",
                        f".//li[contains(@class, 'active')]/following-sibling::li//button",
                        f".//li[contains(@class, 'active')]/following-sibling::li//a"
                    ]
                    
                    next_button = None
                    for selector in next_page_selectors:
                        try:
                            next_button = pagination_element.find_element(By.XPATH, selector)
                            if next_button: break
                        except: continue
                    
                    if next_button:
                        scroll_to_view(driver, next_button)
                        try:
                            next_button.click()
                        except:
                            driver.execute_script("arguments[0].click();", next_button)
                        print_lg(f"\n>-> Successfully moved to Page {next_page} \n")
                        buffer(3)
                    else:
                        print_lg(f"\n>-> Didn't find Page {next_page} button. Probably at the end page of results!\n")
                        break
                except Exception as e:
                    print_lg(f"\n>-> Error navigating to Page {current_page + 1}: {str(e)[:100]}\n")
                    break
        except (NoSuchWindowException, WebDriverException) as e:
            print_lg(f"Browser error for search term '{searchTerm}': {str(e)[:120]}")
            print_lg("Attempting to recover browser session...")
            try:
                # Try to navigate to a safe page to reset the browser state
                driver.get("about:blank")
                sleep(2)
                print_lg("Browser recovered. Moving to next search term...")
            except Exception:
                print_lg("Browser session unrecoverable for this search term. Skipping to next.")
            break  # Break inner while, continue to next searchTerm
        except Exception as e:
            print_lg(f"Failed to find Job listings for term '{searchTerm}'!")
            critical_error_log("In Applier loop", e)
            # Try to recover by refreshing or going back to home
            try:
                driver.get("https://www.linkedin.com/jobs/")
                sleep(2)
            except: pass
