"""
Universal Question Solver & Form Filler Module
===============================================
Automates question answering and form completion across Internshala, Indeed, Naukri, and LinkedIn.
Uses Google Gemini AI (with fallback to candidate profile rules) to answer:
  - Expected CTC / Salary / Compensation (Numbers, LPA, Monthly, Text)
  - Current CTC / Salary
  - Notice Period / Joining Availability
  - Location, relocation, experience, GitHub, portfolio links
  - "Why should we hire you?" / Fit questions (via Gemini)
  - Technical / custom assessment questions (via Gemini)
  - Safe file uploads (ONLY uploads resume to verified resume/CV inputs — NEVER to CTC, payslip, photo, or assignment inputs)
  - Interactive 1-minute timeout prompt with auto-skip
"""

import os
import re
import sys
import time
import select
import threading
from typing import Optional, List, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

import config.secrets as secrets
from config.secrets import use_AI, ai_provider
from config.personals import *
from config.questions import *
from config.search import *
from modules.helpers import print_lg, sleep, screenshot

# Ensure valid resume path
RESUME_PATH = os.path.abspath(default_resume_path) if default_resume_path else ""

# Fallback AI answer for Why Hire You if AI client is unreachable
DEFAULT_WHY_HIRE = (
    cover_letter.strip()
    or linkedin_summary.strip()
    or (
        "I have strong hands-on experience in software engineering and problem solving, "
        "and I am eager to contribute effectively to your team."
    )
)


def get_ai_answer(prompt_question: str, job_title: str = "", company: str = "", ai_client: Any = None) -> str:
    """
    Calls the configured AI provider to answer a question intelligently
    using the candidate's configured profile and resume context.
    """
    if not (use_AI and ai_client):
        return ""

    try:
        from modules.ai.geminiConnections import gemini_answer_question
        from modules.ai.openaiConnections import ai_answer_question

        context = f"Job Title: {job_title}\nCompany: {company}\nPlatform Application Question."
        
        if ai_provider == "gemini":
            ans = gemini_answer_question(
                ai_client,
                question=prompt_question,
                job_description=context,
                user_information_all=user_information_all
            )
        elif ai_provider in ["openai", "deepseek"]:
            ans = ai_answer_question(
                ai_client,
                prompt_question,
                job_description=context,
                user_information_all=user_information_all
            )
        else:
            ans = ""

        if isinstance(ans, str) and ans.strip() and not ans.startswith("Error") and "error" not in ans.lower()[:15]:
            return ans.strip().strip('"').strip("'")
    except Exception as e:
        print_lg(f"[QuestionSolver] AI generation failed for '{prompt_question[:40]}': {e}")

    return ""


def extract_field_label(driver: WebDriver, element: WebElement) -> str:
    """
    Thoroughly extracts the actual question / label text associated with a form element.
    Inspects aria-label, placeholder, associated <label>, enclosing tags, preceding siblings,
    and ancestor question containers (e.g. Internshala, Indeed, Naukri HTML).
    """
    label_candidates: List[str] = []

    try:
        # 1. Direct attributes on the input/textarea
        aria = (element.get_attribute("aria-label") or "").strip()
        if aria:
            label_candidates.append(aria)

        placeholder = (element.get_attribute("placeholder") or "").strip()
        if placeholder:
            label_candidates.append(placeholder)

        elem_title = (element.get_attribute("title") or "").strip()
        if elem_title:
            label_candidates.append(elem_title)

        # 2. Associated label via id
        elem_id = element.get_attribute("id") or ""
        if elem_id:
            try:
                lbl = driver.find_elements(By.XPATH, f"//label[@for='{elem_id}']")
                if lbl and lbl[0].text.strip():
                    label_candidates.append(lbl[0].text.strip())
            except:
                pass

        # 3. Enclosing label element
        try:
            parent_lbl = element.find_elements(By.XPATH, "./ancestor::label")
            if parent_lbl and parent_lbl[0].text.strip():
                label_candidates.append(parent_lbl[0].text.strip())
        except:
            pass

        # 4. Immediate preceding sibling element (heading, label, span, div)
        try:
            sibs = element.find_elements(By.XPATH, "./preceding-sibling::*[self::label or self::div or self::span or self::p or self::h4 or self::h5 or self::h6 or self::legend]")
            for s in reversed(sibs):
                txt = s.text.strip()
                if txt and len(txt) > 2:
                    label_candidates.append(txt)
                    break
        except:
            pass

        # 5. Ancestor container search (form-group, assessment_question, field, row)
        try:
            containers = element.find_elements(By.XPATH, "./ancestor::div[contains(@class, 'form-group') or contains(@class, 'assessment') or contains(@class, 'question') or contains(@class, 'field') or contains(@class, 'form-item') or contains(@class, 'input-group')]")
            for c in containers:
                # Look for headings or labels inside container
                headings = c.find_elements(By.XPATH, ".//*[contains(@class, 'heading') or contains(@class, 'label') or contains(@class, 'title') or contains(@class, 'question') or self::label or self::h4 or self::h5 or self::h6 or self::legend or self::p]")
                for h in headings:
                    htxt = h.text.strip()
                    if htxt and len(htxt) > 3 and not any(w in htxt.lower() for w in ["optional", "characters left", "max "]):
                        label_candidates.append(htxt)
                        break
                if label_candidates:
                    break
        except:
            pass

        # 6. Fallback to name or id attribute
        elem_name = element.get_attribute("name") or ""
        if elem_name:
            label_candidates.append(elem_name.replace("_", " ").replace("-", " "))
        if elem_id:
            label_candidates.append(elem_id.replace("_", " ").replace("-", " "))

    except Exception:
        pass

    # Pick the best descriptive candidate (preferring one that actually has meaningful words)
    for c in label_candidates:
        c_clean = c.strip().rstrip("*:? \n\t")
        if len(c_clean) >= 3 and not c_clean.isdigit():
            return c_clean

    return ""


def resolve_answer(
    question_text: str,
    job_title: str = "",
    company: str = "",
    ai_client: Any = None,
    field_type: str = "text",
    input_element: Any = None
) -> str:
    """
    Determines the exact, correct answer for a given question string.
    STRICTLY maps CTC / Salary / Notice / Location / Experience to deterministic values,
    and calls Gemini AI for open-ended technical questions.

    NEVER returns a resume/CV for Expected CTC, salary, or general fields!
    """
    q = question_text.lower().strip()

    # Get placeholder/type hints from element if provided
    placeholder = ""
    min_val = ""
    max_val = ""
    if input_element:
        try:
            placeholder = (input_element.get_attribute("placeholder") or "").lower()
            min_val = (input_element.get_attribute("min") or "").lower()
            max_val = (input_element.get_attribute("max") or "").lower()
        except:
            pass

    combined_hint = f"{q} {placeholder}".strip()

    # -------------------------------------------------------------------------
    # 1. EXPECTED CTC / SALARY / COMPENSATION / STIPEND
    # -------------------------------------------------------------------------
    # Matches: "what is your expected ctc", "expected salary", "desired ctc", "ctc expectation",
    # "expected compensation", "annual ctc", "ctc", "expected stipend", etc.
    is_expected_ctc = (
        any(k in q for k in [
            "expected ctc", "expected salary", "salary expectation", "ctc expectation",
            "desired ctc", "desired salary", "expected compensation", "expected remuneration",
            "what you expected ctc", "what is your expected ctc", "what are your ctc expectations",
            "what is your salary expectation", "expected package", "expected in-hand",
            "expected fixed", "expected annual", "ctc expected", "salary expected",
            "remuneration expected", "expected stipend", "stipend expected", "minimum ctc",
            "annual ctc", "fixed ctc", "gross ctc", "desired compensation"
        ])
        or ("expected" in q and any(w in q for w in ["ctc", "salary", "remuneration", "compensation", "stipend", "package", "pay", "inr", "lpa"]))
        or ("ctc" in q and "current" not in q and "present" not in q and "existing" not in q)
        or ("salary" in q and "current" not in q and "present" not in q and any(w in q for w in ["expect", "desire", "want", "look", "demand"]))
    )

    if is_expected_ctc:
        print_lg(f"[QuestionSolver] Recognized Expected CTC question: '{question_text[:50]}'")
        salary_val = desired_salary or 0
        lpa_str = str(round(salary_val / 100000, 2)).rstrip('0').rstrip('.') if salary_val else "0"
        # A) In Lakhs / LPA
        if any(w in combined_hint for w in ["lakh", "lpa", "lac", "in lakhs", "in lacs", "(lpa)"]):
            return lpa_str
        # B) Monthly
        if any(w in combined_hint for w in ["month", "monthly", "per month", "/month", "/pm"]):
            monthly_sal = round(salary_val / 12)
            return str(monthly_sal)
        # C) Pure Number input
        if field_type == "number":
            # If max or placeholder suggests LPA (e.g., max 50 or placeholder "e.g. 5")
            if (max_val and float(max_val) <= 50) or (min_val and float(min_val) <= 10 and max_val and float(max_val) <= 100):
                return lpa_str
            if any(w in placeholder for w in ["lakh", "lpa", "5", "6", "7", "8", "9", "10"]) and not any(w in placeholder for w in ["000", "0000"]):
                return lpa_str
            return str(salary_val)
        # D) Textarea
        if field_type == "textarea":
            return f"My expected CTC is {lpa_str} LPA (negotiable based on the role and responsibilities)."
        # E) Standard text
        if "lpa" in q:
            return f"{lpa_str} LPA"
        return str(salary_val)

    # -------------------------------------------------------------------------
    # 2. CURRENT CTC / SALARY / COMPENSATION
    # -------------------------------------------------------------------------
    is_current_ctc = (
        any(k in q for k in [
            "current ctc", "current salary", "present ctc", "present salary",
            "existing ctc", "existing salary", "current compensation", "current package",
            "current in-hand", "current fixed", "current remuneration", "last drawn salary",
            "last drawn ctc", "what is your current ctc", "what is your present ctc"
        ])
        or (("current" in q or "present" in q or "existing" in q or "last drawn" in q) and any(w in q for w in ["ctc", "salary", "compensation", "package", "remuneration"]))
    )

    if is_current_ctc:
        print_lg(f"[QuestionSolver] Recognized Current CTC question: '{question_text[:50]}'")
        ctc_val = current_ctc or 0
        ctc_lpa_str = str(round(ctc_val / 100000, 2)).rstrip('0').rstrip('.') if ctc_val else "0"
        if any(w in combined_hint for w in ["lakh", "lpa", "lac", "in lakhs", "in lacs"]):
            return ctc_lpa_str
        if any(w in combined_hint for w in ["month", "monthly", "per month"]):
            return str(round(ctc_val / 12))
        if field_type == "number":
            return str(ctc_val)
        if field_type == "textarea":
            return f"My current CTC is {ctc_lpa_str} LPA."
        return f"{ctc_lpa_str} LPA"

    # -------------------------------------------------------------------------
    # 3. NOTICE PERIOD / JOINING TIME / AVAILABILITY
    # -------------------------------------------------------------------------
    if any(k in q for k in [
        "notice period", "how soon can you join", "joining time", "when can you start",
        "earliest joining date", "days required to join", "availability to join", "serving notice"
    ]) or ("notice" in q and any(w in q for w in ["day", "period", "month", "time", "join", "start"])):
        print_lg(f"[QuestionSolver] Recognized Notice Period question: '{question_text[:50]}'")
        np_days = notice_period if notice_period is not None else 0
        if "month" in q:
            return str(np_days // 30)
        if "day" in q or field_type == "number":
            return str(np_days)
        if field_type == "textarea":
            return f"Available in {np_days} days." if np_days > 0 else "Available immediately."
        return f"{np_days} days" if np_days > 0 else "Immediate"

    # -------------------------------------------------------------------------
    # 4. EXPERIENCE QUESTIONS (Years of Experience)
    # -------------------------------------------------------------------------
    if any(k in q for k in [
        "years of experience", "how many years", "total experience", "relevant experience",
        "work experience", "experience in python", "experience with python",
        "experience in ai", "experience with ai", "experience with machine learning",
        "experience with llm", "overall experience"
    ]):
        print_lg(f"[QuestionSolver] Recognized Experience question: '{question_text[:50]}'")
        exp_str = years_of_experience or "0"
        if field_type == "number" or "number" in q:
            return exp_str
        if field_type == "textarea":
            return f"I have {exp_str} year(s) of relevant hands-on experience."
        return f"{exp_str} years"

    # -------------------------------------------------------------------------
    # 5. LOCATION / CURRENT CITY / RESIDENCE
    # -------------------------------------------------------------------------
    if any(k in q for k in [
        "current location", "current city", "where do you live", "where are you located",
        "current residence", "residing in", "which city", "your city", "base location"
    ]):
        print_lg(f"[QuestionSolver] Recognized Location question: '{question_text[:50]}'")
        return current_city or ""

    # -------------------------------------------------------------------------
    # 6. RELOCATION / WORK FROM OFFICE / ONSITE
    # -------------------------------------------------------------------------
    if any(k in q for k in [
        "relocate", "willing to move", "comfortable traveling", "work from office",
        "open to relocate", "hybrid", "on-site", "relocation"
    ]):
        print_lg(f"[QuestionSolver] Recognized Relocation question: '{question_text[:50]}'")
        return "Yes, I am completely open to relocating or working on-site."

    # -------------------------------------------------------------------------
    # 7. GITHUB / REPOSITORY / PORTFOLIO / WEBSITE
    # -------------------------------------------------------------------------
    if any(k in q for k in ["github", "repo", "portfolio", "project link", "website", "sample work", "code link"]):
        return website or ""

    # -------------------------------------------------------------------------
    # 8. LINKEDIN PROFILE
    # -------------------------------------------------------------------------
    if "linkedin" in q:
        return linkedIn or ""

    # -------------------------------------------------------------------------
    # 9. PHONE / MOBILE
    # -------------------------------------------------------------------------
    if any(k in q for k in ["phone", "mobile", "contact number", "cell"]):
        return phone_number or ""

    # -------------------------------------------------------------------------
    # 10. EMAIL
    # -------------------------------------------------------------------------
    if "email" in q:
        return getattr(secrets, 'username', '') or ""

    # -------------------------------------------------------------------------
    # 11. FULL NAME / FIRST NAME / LAST NAME
    # -------------------------------------------------------------------------
    if "full name" in q:
        return f"{first_name} {last_name}".strip()
    if "first name" in q:
        return first_name
    if "last name" in q:
        return last_name

    # -------------------------------------------------------------------------
    # 12. WHY SHOULD WE HIRE YOU / COVER LETTER / FIT QUESTIONS
    # -------------------------------------------------------------------------
    # ONLY triggers when explicitly asking why hire, cover letter, or pitch
    if any(k in q for k in [
        "why should we hire you", "why should you be hired", "why are you a good fit",
        "why do you want to join", "cover letter", "pitch yourself", "about yourself",
        "suitability for this role", "why hire", "describe yourself", "brief introduction"
    ]):
        print_lg(f"[QuestionSolver] Generating tailored Why Hire response for '{job_title}' via AI...")
        ai_resp = get_ai_answer(
            f"Explain concisely in 2-3 engaging paragraphs why the candidate should be hired for the role of '{job_title}' at '{company}', highlighting relevant experience and skills from the candidate profile.",
            job_title=job_title,
            company=company,
            ai_client=ai_client
        )
        if ai_resp:
            return ai_resp
        return DEFAULT_WHY_HIRE

    # -------------------------------------------------------------------------
    # 13. OPEN-ENDED TECHNICAL / ASSESSMENT QUESTIONS -> GEMINI AI
    # -------------------------------------------------------------------------
    if len(q) > 8:
        print_lg(f"[QuestionSolver] Using Gemini AI to answer: '{question_text[:60]}'")
        ai_resp = get_ai_answer(question_text, job_title=job_title, company=company, ai_client=ai_client)
        if ai_resp:
            return ai_resp

    # Safe default: short affirmative sentence (NEVER the CV / resume text!)
    return "Yes, I have practical experience and skills relevant to this requirement."


def is_resume_file_input(driver: WebDriver, file_element: WebElement) -> bool:
    """
    Validates whether a file input (<input type='file'>) is ACTUALLY meant for a resume/CV.
    STRICTLY REJECTS file inputs for payslips, CTC proof, photos, assignments, etc.
    """
    try:
        # Check element attributes
        elem_name = (file_element.get_attribute("name") or "").lower()
        elem_id = (file_element.get_attribute("id") or "").lower()
        elem_accept = (file_element.get_attribute("accept") or "").lower()
        elem_title = (file_element.get_attribute("title") or "").lower()
        elem_aria = (file_element.get_attribute("aria-label") or "").lower()

        # Check surrounding text / label
        surrounding_text = extract_field_label(driver, file_element).lower()

        combined = f"{elem_name} {elem_id} {elem_accept} {elem_title} {elem_aria} {surrounding_text}"

        # 1. HARD BLOCK: If any non-resume indicator is present
        blocked_keywords = [
            "photo", "picture", "image", "avatar", "profile_pic", "photograph",
            "ctc", "salary", "payslip", "pay_slip", "slip", "proof",
            "assignment", "sample", "project", "code", "zip", "tar", "video", "audio",
            "aadhaar", "pan", "passport", "id_card", "identity", "signature"
        ]
        for b in blocked_keywords:
            if b in combined:
                print_lg(f"[QuestionSolver] Skipping non-resume file input (detected '{b}'): name='{elem_name}', id='{elem_id}'")
                return False

        # 2. POSITIVE MATCH: Resume/CV indicators
        resume_keywords = ["resume", "cv", "curriculum", "biodata", "profile_doc", "document"]
        for r in resume_keywords:
            if r in combined:
                return True

        # 3. Accept attribute specifies PDF/DOC and page context mentions resume
        if any(ext in elem_accept for ext in [".pdf", ".doc", ".docx", "application/pdf"]):
            page_text = driver.page_source[:5000].lower()
            if any(r in page_text for r in ["resume", "cv", "curriculum vitae", "attach your resume"]):
                return True

    except Exception:
        pass

    return False


def auto_fill_form_elements(
    driver: WebDriver,
    job_title: str = "",
    company: str = "",
    ai_client: Any = None
) -> int:
    """
    Finds and fills ALL uncompleted form elements on the current page or modal:
    - Textareas (Why hire you, assessment questions)
    - Input text / number / url (CTC, location, experience, salary, links)
    - File upload inputs (ONLY verified resume inputs — NEVER CTC/payslip/photo inputs)
    - Radio buttons (Yes/No, availability, relocation)
    - Dropdowns (Select)
    - Checkboxes (confirmations)
    Returns count of elements filled.
    """
    filled_count = 0

    # 1. Upload Resume ONLY if verified resume file input is present
    try:
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        for fi in file_inputs:
            try:
                if is_resume_file_input(driver, fi):
                    if RESUME_PATH and os.path.isfile(RESUME_PATH):
                        fi.send_keys(RESUME_PATH)
                        print_lg(f"[QuestionSolver] ✅ Successfully uploaded resume to verified file input: {os.path.basename(RESUME_PATH)}")
                        filled_count += 1
                        sleep(2)
                else:
                    print_lg("[QuestionSolver] File input is not a resume field. Skipping file upload.")
            except Exception as e:
                print_lg(f"[QuestionSolver] File upload notice: {e}")
    except Exception:
        pass

    # 2. Textareas (Why hire you, cover letters, assessment answers)
    try:
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        for ta in textareas:
            try:
                if not ta.is_displayed():
                    continue
                current_val = ta.get_attribute("value") or ""
                if not current_val.strip() or current_val.strip().lower() in ["cover letter", "cover letter\n"]:
                    label_text = extract_field_label(driver, ta)
                    if not label_text:
                        # Check id or name for why hire keywords
                        ta_id = (ta.get_attribute("id") or "").lower()
                        if "cover" in ta_id or "hire" in ta_id:
                            label_text = "Why should you be hired for this role?"
                        else:
                            label_text = "Assessment Question"

                    print_lg(f"[QuestionSolver] Answering textarea: '{label_text[:60]}'")
                    ans = resolve_answer(label_text, job_title=job_title, company=company, ai_client=ai_client, field_type="textarea", input_element=ta)
                    ta.clear()
                    ta.send_keys(ans)
                    filled_count += 1
                    sleep(1)
            except Exception as e:
                print_lg(f"[QuestionSolver] Textarea fill error: {e}")
    except Exception:
        pass

    # 3. Text & Number Inputs (CTC, notice period, location, salary, experience, links)
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='url'], input:not([type])")
        for inp in inputs:
            try:
                if not inp.is_displayed() or not inp.is_enabled():
                    continue
                val = inp.get_attribute("value") or ""
                if not val.strip():
                    inp_type = inp.get_attribute("type") or "text"
                    label_text = extract_field_label(driver, inp)
                    if not label_text:
                        continue

                    print_lg(f"[QuestionSolver] Answering input ({inp_type}): '{label_text[:50]}'")
                    ans = resolve_answer(label_text, job_title=job_title, company=company, ai_client=ai_client, field_type=inp_type, input_element=inp)
                    if ans:
                        inp.clear()
                        inp.send_keys(ans)
                        filled_count += 1
                        sleep(0.5)
            except Exception:
                pass
    except Exception:
        pass

    # 4. Radio Buttons
    try:
        radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        radio_groups: Dict[str, List[WebElement]] = {}
        for r in radios:
            try:
                if not r.is_displayed():
                    parent = r.find_element(By.XPATH, "./..")
                    if not parent.is_displayed():
                        continue
                name = r.get_attribute("name") or "default_group"
                radio_groups.setdefault(name, []).append(r)
            except:
                pass

        for name, group in radio_groups.items():
            if any(r.is_selected() for r in group):
                continue

            chosen = None
            for r in group:
                try:
                    r_id = r.get_attribute("id") or ""
                    r_val = (r.get_attribute("value") or "").lower()
                    label = ""
                    if r_id:
                        try:
                            lbl = driver.find_element(By.XPATH, f"//label[@for='{r_id}']")
                            label = lbl.text.lower()
                        except:
                            pass
                    if not label:
                        label = r_val

                    # Prefer Yes / Available / Immediate / Relocate
                    if any(pos in label for pos in ["yes", "1", "true", "immediate", "full-time", "relocate", "confirm"]):
                        chosen = r
                        break
                except:
                    pass

            if not chosen and group:
                chosen = group[0]

            if chosen:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", chosen)
                    filled_count += 1
                    sleep(0.5)
                except:
                    pass
    except Exception:
        pass

    # 5. Dropdowns (Select Elements)
    try:
        selects = driver.find_elements(By.TAG_NAME, "select")
        for s_el in selects:
            try:
                if s_el.is_displayed() and s_el.is_enabled():
                    sel = Select(s_el)
                    first_opt = sel.first_selected_option
                    val = first_opt.get_attribute("value") if first_opt else ""
                    if not val or val == "0" or "select" in (first_opt.text or "").lower():
                        opts = sel.options
                        chosen_opt = None
                        for o in opts:
                            t = o.text.lower()
                            if any(k in t for k in ["yes", "immediate", "0-15", "1-2", "delhi", "full-time", "7"]):
                                chosen_opt = o
                                break
                        if not chosen_opt and len(opts) > 1:
                            chosen_opt = opts[1]
                        if chosen_opt:
                            sel.select_by_visible_text(chosen_opt.text)
                            filled_count += 1
            except:
                pass
    except Exception:
        pass

    # 6. Checkboxes (Terms, Declarations)
    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        for cb in checkboxes:
            try:
                if cb.is_displayed() and not cb.is_selected():
                    cb_id = cb.get_attribute("id") or ""
                    label_text = ""
                    if cb_id:
                        try:
                            lbl = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                            label_text = lbl.text.lower()
                        except:
                            pass
                    if any(w in label_text for w in ["agree", "confirm", "certify", "accept", "terms", "condition", "relocate", "available"]):
                        driver.execute_script("arguments[0].click();", cb)
                        filled_count += 1
            except:
                pass
    except Exception:
        pass

    return filled_count


def prompt_user_if_stuck(
    driver: WebDriver,
    job_title: str,
    reason: str = "Unfilled required field or verification needed",
    timeout_seconds: int = 60
) -> bool:
    """
    When an unexpected question or platform prompt blocks submission,
    asks the user in console to inspect the browser and confirm rather than skipping.
    Waits for at most timeout_seconds (default 60 seconds / 1 minute).
    If no input is received within 1 minute or user types 'skip', returns False to skip the job.
    Returns True if user chose to proceed.
    """
    if not pause_at_failed_question:
        return False

    print_lg("\n" + "=" * 65)
    print_lg(f"🔔 [ACTION REQUIRED] Job: '{job_title}'")
    print_lg(f"Reason: {reason}")
    print_lg("Please check the browser window, fill/adjust any missing field.")
    print_lg(f"⏳ Waiting for 1 minute ({timeout_seconds}s) for your response.")
    print_lg("👉 Press Enter in terminal to proceed, or type 'skip' to move to next job...")
    print_lg("=" * 65 + "\n")

    try:
        screenshot(driver, "QuestionSolver", f"Manual_Action_Needed_{job_title[:15]}")
    except:
        pass

    try:
        sys.stdout.write(f"👉 Press Enter to continue (or type 'skip') [{timeout_seconds}s timeout]: ")
        sys.stdout.flush()

        user_input = None
        try:
            rlist, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
            if rlist:
                user_input = sys.stdin.readline().strip().lower()
        except Exception:
            raw_input = [None]
            def _reader():
                try:
                    raw_input[0] = sys.stdin.readline()
                except:
                    pass
            th = threading.Thread(target=_reader, daemon=True)
            th.start()
            th.join(timeout=timeout_seconds)
            if raw_input[0] is not None:
                user_input = raw_input[0].strip().lower()

        if user_input is not None:
            if user_input in ["skip", "s", "no", "n"]:
                print_lg(f"\nUser explicitly skipped '{job_title}'. Moving to next job.")
                return False
            print_lg("\nUser confirmed. Continuing application...")
            return True
        else:
            print_lg(f"\n⏱️ 1-minute timeout reached with no reply. Skipping '{job_title}' and moving to next job...")
            return False

    except Exception as e:
        print_lg(f"Notice during timed prompt: {e}")
        return False
