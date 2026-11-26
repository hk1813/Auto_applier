'''
Author:     Himanshu Khurana
LinkedIn:   https://www.linkedin.com/in/himanshukhurana/

Copyright (C) 2024 Himanshu Khurana

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    24.12.29.12.30
'''

from config.settings import click_gap, smooth_scroll
from modules.helpers import buffer, print_lg, sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains

# Click Functions
def wait_span_click(driver: WebDriver, text: str, time: float=5.0, click: bool=True, scroll: bool=True, scrollTop: bool=False, root: WebElement = None) -> WebElement | bool:
    '''
    Finds the span element with the given `text` within `root` (or driver if root is None).
    - Returns `WebElement` if found, else `False` if not found.
    - Clicks on it if `click = True`.
    - Will spend a max of `time` seconds in searching for each element.
    - Will scroll to the element if `scroll = True`.
    - Will scroll to the top if `scrollTop = True`.
    '''
    if text:
        try:
            # Try span first, then any tag that contains the text (case-insensitive where possible)
            # Using contains(normalize-space(.), 'text') is more robust than exact match
            xpath_span = f'.//span[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{text.lower()}")]'
            xpath_any = f'.//*[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{text.lower()}")]'
            
            search_base = root if root else driver
            try:
                if root:
                    # If root is a WebElement, we can't use standard WebDriverWait easily with EC
                    # So we use a simple try/except or a custom wait loop
                    button = search_base.find_element(By.XPATH, xpath_span)
                else:
                    button = WebDriverWait(driver, time).until(EC.presence_of_element_located((By.XPATH, xpath_span)))
            except:
                if root:
                    button = search_base.find_element(By.XPATH, xpath_any)
                else:
                    button = WebDriverWait(driver, time).until(EC.presence_of_element_located((By.XPATH, xpath_any)))
            
            if scroll:  scroll_to_view(driver, button, scrollTop)
            if click:
                button.click()
                buffer(click_gap)
            return button
        except Exception as e:
            print_lg("Click Failed! Didn't find '"+text+"'")
            # print_lg(e)
            return False

def multi_sel(driver: WebDriver, texts: list, time: float=5.0, root: WebElement = None) -> None:
    for text in texts:
        wait_span_click(driver, text, time, root=root)

def multi_sel_noWait(driver: WebDriver, texts: list, actions: ActionChains = None, root: WebElement = None) -> None:
    for text in texts:
        try:
            xpath = f'.//span[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{text.lower()}")]'
            search_base = root if root else driver
            button = search_base.find_element(By.XPATH, xpath)
            scroll_to_view(driver, button)
            button.click()
            buffer(click_gap)
        except Exception as e:
            if actions: company_search_click(driver, actions, text)
            else: print_lg("Click Failed! Didn't find '"+text+"'")

def boolean_button_click(driver: WebDriver, actions: ActionChains, text: str) -> None:
    '''
    Tries to click on the boolean button with the given `text` text.
    '''
    try:
        # Try finding using h3 or any tag that might contain the text
        try:
            list_container = driver.find_element(By.XPATH, './/h3[normalize-space()="'+text+'"]/ancestor::fieldset')
        except:
            list_container = driver.find_element(By.XPATH, './/*[normalize-space()="'+text+'"]/ancestor::fieldset | .//*[normalize-space()="'+text+'"]/ancestor::div[contains(@class, "filter")]')

        button = list_container.find_element(By.XPATH, './/input[@role="switch"] | .//button[@role="switch"] | .//input[@type="checkbox"]')
        scroll_to_view(driver, button)
        actions.move_to_element(button).click().perform()
        buffer(click_gap)
    except Exception as e:
        print_lg("Click Failed! Didn't find '"+text+"'")
        # print_lg(e)

# Find functions
def find_by_class(driver: WebDriver, class_name: str, time: float=5.0) -> WebElement | Exception:
    '''
    Waits for a max of `time` seconds for element to be found, and returns `WebElement` if found, else `Exception` if not found.
    '''
    return WebDriverWait(driver, time).until(EC.presence_of_element_located((By.CLASS_NAME, class_name)))

# Scroll functions
def scroll_to_view(driver: WebDriver, element: WebElement, top: bool = False, smooth_scroll: bool = smooth_scroll) -> None:
    '''
    Scrolls the `element` to view.
    - `smooth_scroll` will scroll with smooth behavior.
    - `top` will scroll to the `element` to top of the view.
    '''
    if top:
        return driver.execute_script('arguments[0].scrollIntoView();', element)
    behavior = "smooth" if smooth_scroll else "instant"
    return driver.execute_script('arguments[0].scrollIntoView({block: "center", behavior: "'+behavior+'" });', element)

# Enter input text functions
def text_input_by_ID(driver: WebDriver, id: str, value: str, time: float=5.0) -> None | Exception:
    '''
    Enters `value` into the input field with the given `id` if found, else throws NotFoundException.
    - `time` is the max time to wait for the element to be found.
    '''
    from modules.helpers import type_human_like
    username_field = WebDriverWait(driver, time).until(EC.presence_of_element_located((By.ID, id)))
    type_human_like(username_field, value)

def try_xp(driver: WebDriver, xpath: str, click: bool=True) -> WebElement | bool:
    try:
        if click:
            driver.find_element(By.XPATH, xpath).click()
            return True
        else:
            return driver.find_element(By.XPATH, xpath)
    except: return False

def try_linkText(driver: WebDriver, linkText: str) -> WebElement | bool:
    try:    return driver.find_element(By.LINK_TEXT, linkText)
    except:  return False

def try_find_by_classes(driver: WebDriver, classes: list[str]) -> WebElement | ValueError:
    for cla in classes:
        try:    return driver.find_element(By.CLASS_NAME, cla)
        except: pass
    raise ValueError("Failed to find an element with given classes")

def company_search_click(driver: WebDriver, actions: ActionChains, companyName: str) -> None:
    '''
    Tries to search and Add the company to company filters list.
    '''
    wait_span_click(driver,"Add a company",1)
    search = driver.find_element(By.XPATH,"(.//input[@placeholder='Add a company'])[1]")
    from modules.helpers import type_human_like
    type_human_like(search, companyName)
    buffer(3)
    actions.send_keys(Keys.DOWN).perform()
    actions.send_keys(Keys.ENTER).perform()
    print_lg(f'Tried searching and adding "{companyName}"')

def text_input(actions: ActionChains, textInputEle: WebElement | bool, value: str, textFieldName: str = "Text") -> None | Exception:
    if textInputEle:
        sleep(1)
        # actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        textInputEle.clear()
        textInputEle.send_keys(value.strip())
        sleep(2)
        actions.send_keys(Keys.ENTER).perform()
    else:
        print_lg(f'{textFieldName} input was not given!')