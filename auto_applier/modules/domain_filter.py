"""
Domain Filter Module — Strict Tech-Only & 0-2 Years Experience Job Validation
=============================================================================
Ensures the bot:
1. ONLY applies to tech/software/AI/data/Python jobs (blocks sales, HR, finance, food, etc.)
2. STRICTLY enforces 0-2 years experience requirement (blocks Lead, Principal, Director, VP, 3+ yrs roles)
"""

import re
from typing import Tuple

# ---------------------------------------------------------------------------
# TECH KEYWORDS — job must contain at least one of these to be considered
# ---------------------------------------------------------------------------
TECH_KEYWORDS = [
    # Roles
    "software", "developer", "engineer", "programmer", "coder",
    "devops", "devsecops", "sre", "site reliability",
    "data scientist", "data analyst", "data engineer", "analytics",
    "machine learning", "ml engineer", "ai engineer", "ai developer",
    "deep learning", "nlp", "computer vision", "research scientist",
    "backend", "back end", "front end", "frontend", "full stack", "fullstack",
    "mobile developer", "android developer", "ios developer",
    "cloud engineer", "platform engineer",
    "embedded", "firmware", "hardware engineer", "vlsi", "fpga",
    "network engineer", "network administrator", "cybersecurity",
    "security engineer", "penetration tester", "ethical hacker",
    "qa engineer", "quality assurance", "test engineer", "automation tester",
    "database administrator", "dba", "system administrator", "sysadmin",
    "it support", "it administrator", "it analyst",
    "big data", "hadoop", "spark", "kafka", "etl",
    "blockchain", "smart contract", "web3",
    "game developer", "unity developer", "unreal",
    # Languages / Frameworks / Technologies
    "python", "java", "javascript", "typescript", "golang", "go developer",
    "rust", "c++", "c#", ".net", "kotlin", "swift", "scala", "php developer",
    "ruby on rails", "react", "angular", "vue", "node.js", "nodejs",
    "django", "flask", "fastapi", "spring", "spring boot",
    "aws", "gcp", "google cloud", "azure", "kubernetes", "docker",
    "terraform", "ansible", "jenkins", "ci/cd", "git",
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "api", "rest", "graphql", "microservices", "serverless",
    "tableau", "power bi", "powerbi", "looker", "databricks",
    "opencv", "tensorflow", "pytorch", "keras", "scikit",
    "linux", "unix", "bash", "shell scripting",
    # Generic tech indicators
    "tech", "it ", "information technology", "software development",
    "web development", "app development", "product engineer",
    "technical", "technology", "automation",
]

# ---------------------------------------------------------------------------
# NON-TECH BLOCKLIST — if any of these appear in title/description → reject
# ---------------------------------------------------------------------------
NON_TECH_BLOCKLIST = [
    # Sales & Marketing
    "sales executive", "field sales", "sales manager", "sales officer",
    "business development executive", "bde", "bdm", "business development manager",
    "marketing executive", "marketing manager", "digital marketing",
    "social media manager", "social media executive", "content writer",
    "content creator", "copywriter", "seo executive", "sem executive",
    "brand manager", "growth hacker",
    # Finance & Accounts
    "accountant", "accounts executive", "accounts manager",
    "finance executive", "finance manager", "financial analyst",
    "ca ", "chartered accountant", "tax consultant", "auditor",
    "loan officer", "credit analyst", "insurance agent", "insurance advisor",
    "mutual fund", "stock broker", "equity analyst",
    # HR & Admin
    "hr ", "human resources", "hr executive", "hr manager",
    "recruiter", "talent acquisition", "payroll", "hr generalist",
    "admin executive", "administrative assistant", "office assistant",
    "receptionist", "front desk",
    # Operations & Logistics
    "operations executive", "operations manager",
    "supply chain", "logistics", "warehouse", "inventory",
    "procurement", "purchase executive", "store manager",
    "delivery executive", "delivery partner", "driver", "courier",
    # Hospitality & Service
    "chef", "cook", "baker", "bartender",
    "hotel", "hospitality", "housekeeping", "steward",
    "restaurant", "food and beverage",
    # Healthcare & Education (unless tech related)
    "nurse", "nursing", "doctor", "physician", "pharmacist",
    "teacher", "tutor", "faculty", "lecturer", "professor",
    "counsellor", "counselor",
    # Real Estate
    "real estate", "property consultant", "site engineer civil",
    "civil engineer", "structural engineer", "architect civil",
    # BPO / Call Centre
    "telecaller", "tele caller", "bpo", "call center", "call centre",
    "customer support executive", "customer service executive",
    "customer care", "voice process", "non-voice process",
    # Data Entry (not data engineering)
    "data entry", "data entry operator", "typist", "clerk",
    "back office executive", "cashier",
    # Other non-tech
    "field officer", "field executive", "collection executive",
    "relationship manager banking", "bank executive",
]

# ---------------------------------------------------------------------------
# SENIORITY BLOCKLIST — Roles requiring > 2 years experience (reject for 0-2 yrs)
# ---------------------------------------------------------------------------
SENIORITY_BLOCKLIST = [
    "senior", "sr.", "sr ", "lead", "principal", "director", "vice president", "vp ", "vp-", "head of",
    "chief", "architect", "senior manager", "general manager", "sr. manager",
    "staff", "staff engineer", "deputy vice president", "partner", "founder", "co-founder",
    "engineering manager", "technical manager", "delivery manager", "program manager",
    "project manager", "scrum master"
]


def is_tech_job(title: str, description: str = "") -> bool:
    """
    Returns True if the job is tech-related, False if it should be skipped.

    Checks:
    1. If the title/description contains ANY NON_TECH_BLOCKLIST phrase → reject
    2. If the title/description contains ANY TECH_KEYWORDS phrase → accept
    3. Otherwise → reject (safe default)
    """
    combined = (title + " " + description).lower()

    # Step 1: Hard reject if non-tech pattern found in title
    title_lower = title.lower()
    for blocked in NON_TECH_BLOCKLIST:
        if blocked in title_lower:
            return False

    # Step 2: Accept if any tech keyword is found
    for kw in TECH_KEYWORDS:
        if kw in combined:
            return True

    # Step 3: Default reject — no tech keyword found anywhere
    return False


def is_experience_eligible(title: str, snippet_text: str = "", max_allowed_exp: int = 2) -> Tuple[bool, str]:
    """
    Validates whether a job posting matches the candidate's 0-2 years experience level.
    Rejects:
    1. High seniority titles (Senior, Lead, Principal, Director, VP, Architect, etc.)
    2. Postings where minimum required experience > max_allowed_exp (e.g. 3-8 yrs, 8-12 yrs, 8-to-13-years)

    Returns:
        (True, "OK") if eligible
        (False, reason_str) if ineligible
    """
    title_norm = re.sub(r'[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]', '-', title.lower().strip())
    snippet_norm = re.sub(r'[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]', '-', snippet_text.lower().strip()) if snippet_text else ""
    combined = title_norm + " " + snippet_norm

    words = set(re.findall(r'\b[a-z]+\b', title_norm))

    # 1. Seniority Check in Title
    for s in SENIORITY_BLOCKLIST:
        s_clean = s.strip()
        if " " in s_clean or "." in s_clean:
            if s_clean in title_norm:
                return False, f"Title contains senior role indicator: '{s}'"
        else:
            if s_clean in words:
                return False, f"Title contains senior role indicator: '{s}'"

    # 2. Extract numeric experience ranges from combined text (title, card snippet, detail URL/page)
    # Match patterns like: "8 - 12 Yrs", "8 – 13 Yrs", "8 to 13 years", "8-to-13-years", "0-2 yrs"
    range_matches = re.findall(r'(\d+)[\s-]*(?:-to-|[-–—]|to)[\s-]*(\d+)[\s-]*(?:yrs|years|year|yr)', combined)
    for min_str, max_str in range_matches:
        min_val = int(min_str)
        max_val = int(max_str)
        if min_val <= 30 and min_val > max_allowed_exp:
            return False, f"Required experience range ({min_str}-{max_str} Yrs) exceeds {max_allowed_exp} years limit"

    # Match "exp: 5 - 10" or "experience: 3-5"
    exp_prefix_matches = re.findall(r'(?:exp(?:erience)?[:\s]*)(\d+)[\s-]*(?:-to-|[-–—]|to)[\s-]*(\d+)', combined)
    for min_str, max_str in exp_prefix_matches:
        min_val = int(min_str)
        if min_val <= 30 and min_val > max_allowed_exp:
            return False, f"Required experience range ({min_str}-{max_str} Yrs) exceeds {max_allowed_exp} years limit"

    # Match "8+ yrs", "5+ years"
    plus_matches = re.findall(r'(\d+)\+[\s-]*(?:yrs|years|year|yr)', combined)
    for val_str in plus_matches:
        val = int(val_str)
        if val <= 30 and val > max_allowed_exp:
            return False, f"Required experience ({val_str}+ Yrs) exceeds {max_allowed_exp} years limit"

    # Match "min 4 yrs", "minimum 3 years"
    min_keyword_matches = re.findall(r'min(?:imum)?[\s-]*(\d+)[\s-]*(?:yrs|years|year|yr)', combined)
    for val_str in min_keyword_matches:
        val = int(val_str)
        if val <= 30 and val > max_allowed_exp:
            return False, f"Minimum required experience ({val_str} Yrs) exceeds {max_allowed_exp} years limit"

    return True, "OK"
