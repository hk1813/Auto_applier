'''
Author:     Himanshu Khurana
LinkedIn:   https://www.linkedin.com/in/himanshukhurana/

Copyright (C) 2024 Himanshu Khurana

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    24.12.29.12.30
'''

import os
from modules.helpers import make_directories
from config.settings import run_in_background, stealth_mode, disable_extensions, safe_mode, file_name, failed_file_name, logs_folder_path, generated_resume_path
from config.questions import default_resume_path
if stealth_mode:
    import undetected_chromedriver as uc
else: 
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from modules.helpers import find_default_profile_directory, critical_error_log, print_lg

def setup_bot():
    """
    Sets up the WebDriver and other necessary components.
    Returns: driver, wait, actions
    """
    global driver, wait, actions
    try:
        dirs_to_make = [file_name, failed_file_name, logs_folder_path + "/screenshots", default_resume_path]
        if generated_resume_path and os.path.isdir(generated_resume_path):
            dirs_to_make.append(generated_resume_path + "/temp")
        make_directories(dirs_to_make)

        # Set up WebDriver with Chrome Profile
        options = uc.ChromeOptions() if stealth_mode else Options()
        if run_in_background:   options.add_argument("--headless")
        if disable_extensions:  options.add_argument("--disable-extensions")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process") # Helps with some connection issues

        print_lg("IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM! Or it's highly likely that application will just open browser and not do anything!")
        if safe_mode: 
            print_lg("SAFE MODE: Will login with a guest profile, browsing history will not be saved in the browser!")
        else:
            profile_dir = os.path.abspath("chrome_bot_profile")
            print_lg(f"Using dedicated persistent bot profile at: {profile_dir}")
            print_lg("NOTE: Since this is a separate profile, you will need to log in manually the FIRST time. Afterwards, it will remember you and won't conflict with your main Chrome!")
            options.add_argument(f"--user-data-dir={profile_dir}")
        if stealth_mode:
            # try: 
            #     driver = uc.Chrome(driver_executable_path="C:\\Program Files\\Google\\Chrome\\chromedriver-win64\\chromedriver.exe", options=options)
            # except (FileNotFoundError, PermissionError) as e: 
            #     print_lg("(Undetected Mode) Got '{}' when using pre-installed ChromeDriver.".format(type(e).__name__)) 
                print_lg("Downloading Chrome Driver... This may take some time. Undetected mode requires download every run!")
                from webdriver_manager.chrome import ChromeDriverManager
                driver = uc.Chrome(options=options, driver_executable_path=ChromeDriverManager().install())
        else: driver = webdriver.Chrome(options=options, service=Service(ChromeDriverManager().install()))
        driver.maximize_window()
        wait = WebDriverWait(driver, 5)
        actions = ActionChains(driver)
        return driver, wait, actions
    except Exception as e:
        msg = 'Seems like either... \n\n1. Chrome is already running. \nA. Close all Chrome windows and try again. \n\n2. Google Chrome or Chromedriver is out dated. \nA. Update browser and Chromedriver (You can run "windows-setup.bat" in /setup folder for Windows PC to update Chromedriver)! \n\n3. If error occurred when using "stealth_mode", try reinstalling undetected-chromedriver. \nA. Open a terminal and use commands "pip uninstall undetected-chromedriver" and "pip install undetected-chromedriver". \n\n\nIf issue persists, try Safe Mode. Set, safe_mode = True in config.py \n\nPlease check GitHub discussions/support for solutions https://github.com/GodsScion/Auto_job_applier_linkedIn \n                                   OR \nReach out in discord ( https://discord.gg/fFp7uUzWCY )'
        if isinstance(e,TimeoutError): msg = "Couldn't download Chrome-driver. Set stealth_mode = False in config!"
        print_lg(msg)
        critical_error_log("In Opening Chrome", e)
        from pyautogui import alert
        alert(msg, "Error in opening chrome")
        try: driver.quit()
        except NameError: exit()
        return None, None, None
    
