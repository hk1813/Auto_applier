import os
import csv
from datetime import datetime
from typing import Literal
from modules.helpers import print_lg, truncate_for_csv
from config.settings import file_name, failed_file_name, logs_folder_path

def save_submitted_job(job_id: str, title: str, company: str, work_location: str = "Unknown", 
                       work_style: str = "Unknown", description: str = "Unknown", 
                       experience_required: str | int = "Unknown", 
                       skills: str | list = "Unknown", hr_name: str = "Unknown", 
                       hr_link: str = "Unknown", resume: str = "Unknown", 
                       reposted: bool = False, date_listed: str | datetime = "Unknown", 
                       date_applied: datetime = None, job_link: str = "Unknown", 
                       application_link: str = "Unknown", questions_list: set | list = None, 
                       connect_request: str = "Unknown") -> None:
    '''
    Save successfully applied job to CSV and Excel history files.
    '''
    if date_applied is None:
        date_applied = datetime.now()
        
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_name), exist_ok=True)

        # Save to CSV
        with open(file_name, mode='a', newline='', encoding='utf-8') as csv_file:
            fieldnames = ['Job ID', 'Title', 'Company', 'Work Location', 'Work Style', 'About Job', 'Experience required', 'Skills required', 'HR Name', 'HR Link', 'Resume', 'Re-posted', 'Date Posted', 'Date Applied', 'Job Link', 'External Job link', 'Questions Found', 'Connect Request']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            if csv_file.tell() == 0: writer.writeheader()
            writer.writerow({
                'Job ID': truncate_for_csv(job_id), 
                'Title': truncate_for_csv(title), 
                'Company': truncate_for_csv(company), 
                'Work Location': truncate_for_csv(work_location), 
                'Work Style': truncate_for_csv(work_style), 
                'About Job': truncate_for_csv(description), 
                'Experience required': truncate_for_csv(experience_required), 
                'Skills required': truncate_for_csv(skills), 
                'HR Name': truncate_for_csv(hr_name), 
                'HR Link': truncate_for_csv(hr_link), 
                'Resume': truncate_for_csv(resume), 
                'Re-posted': truncate_for_csv(reposted), 
                'Date Posted': truncate_for_csv(date_listed), 
                'Date Applied': truncate_for_csv(date_applied), 
                'Job Link': truncate_for_csv(job_link), 
                'External Job link': truncate_for_csv(application_link), 
                'Questions Found': truncate_for_csv(questions_list), 
                'Connect Request': truncate_for_csv(connect_request)
            })
        
        # Save to Excel
        try:
            from openpyxl import Workbook, load_workbook
            excel_file = file_name.replace(".csv", ".xlsx")
            row_data = [
                truncate_for_csv(job_id), truncate_for_csv(title), truncate_for_csv(company), 
                truncate_for_csv(work_location), truncate_for_csv(work_style), 
                truncate_for_csv(description), truncate_for_csv(experience_required), truncate_for_csv(skills), 
                truncate_for_csv(hr_name), truncate_for_csv(hr_link), truncate_for_csv(resume), 
                truncate_for_csv(reposted), truncate_for_csv(date_listed), truncate_for_csv(date_applied), 
                truncate_for_csv(job_link), truncate_for_csv(application_link), 
                # Convert set to list for Excel serialization if needed
                str(questions_list) if isinstance(questions_list, (set, list)) else truncate_for_csv(questions_list), 
                truncate_for_csv(connect_request)
            ]
            if not os.path.exists(excel_file):
                wb = Workbook()
                ws = wb.active
                ws.append(['Job ID', 'Title', 'Company', 'Work Location', 'Work Style', 'About Job', 'Experience required', 'Skills required', 'HR Name', 'HR Link', 'Resume', 'Re-posted', 'Date Posted', 'Date Applied', 'Job Link', 'External Job link', 'Questions Found', 'Connect Request'])
            else:
                wb = load_workbook(excel_file)
                ws = wb.active
            ws.append(row_data)
            wb.save(excel_file)
        except Exception as excel_e:
            print_lg("Failed to update applied jobs Excel history!", excel_e)
    except Exception as e:
        print_lg("Failed to update submitted jobs list!", e)

def save_failed_job(job_id: str, job_link: str, resume: str = "Unknown", 
                    date_listed: str | datetime = "Unknown", 
                    error_reason: str = "Unknown", exception: Exception = None, 
                    application_link: str = "Unknown", screenshot_name: str = "Not Available") -> None:
    '''
    Save failed job application to CSV and Excel history files.
    '''
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(failed_file_name), exist_ok=True)
        
        with open(failed_file_name, 'a', newline='', encoding='utf-8') as file:
            fieldnames = ['Job ID', 'Job Link', 'Resume Tried', 'Date listed', 'Date Tried', 'Assumed Reason', 'Stack Trace', 'External Job link', 'Screenshot Name']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if file.tell() == 0: writer.writeheader()
            writer.writerow({
                'Job ID': truncate_for_csv(job_id), 
                'Job Link': truncate_for_csv(job_link), 
                'Resume Tried': truncate_for_csv(resume), 
                'Date listed': truncate_for_csv(date_listed), 
                'Date Tried': datetime.now(), 
                'Assumed Reason': truncate_for_csv(error_reason), 
                'Stack Trace': truncate_for_csv(str(exception) if exception else ""), 
                'External Job link': truncate_for_csv(application_link), 
                'Screenshot Name': truncate_for_csv(screenshot_name)
            })
        
        # Save to Excel
        try:
            from openpyxl import Workbook, load_workbook
            excel_file = failed_file_name.replace(".csv", ".xlsx")
            row_data = [
                truncate_for_csv(job_id), truncate_for_csv(job_link), truncate_for_csv(resume), 
                truncate_for_csv(date_listed), datetime.now(), truncate_for_csv(error_reason), 
                truncate_for_csv(str(exception) if exception else ""), truncate_for_csv(application_link), 
                truncate_for_csv(screenshot_name)
            ]
            if not os.path.exists(excel_file):
                wb = Workbook()
                ws = wb.active
                ws.append(['Job ID', 'Job Link', 'Resume Tried', 'Date listed', 'Date Tried', 'Assumed Reason', 'Stack Trace', 'External Job link', 'Screenshot Name'])
            else:
                wb = load_workbook(excel_file)
                ws = wb.active
            ws.append(row_data)
            wb.save(excel_file)
        except Exception as excel_e:
            print_lg("Failed to update failed jobs Excel history!", excel_e)
    except Exception as e:
        print_lg("Failed to update failed jobs list!", e)
