'''
Author:     Himanshu Khurana
LinkedIn:   https://www.linkedin.com/in/himanshukhurana/

Copyright (C) 2024 Himanshu Khurana

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    2024.11.28.16.00
'''


###################################################### CONFIGURE YOUR TOOLS HERE ######################################################


# >>>>>>>>>>> Easy Apply Questions & Inputs <<<<<<<<<<<

# Your legal name
first_name = ""                 # Your first name in quotes Eg: "First"
middle_name = ""                # Your middle name in quotes Eg: "Middle", ""
last_name = ""                  # Your last name in quotes Eg: "Last"

# Phone number (required), make sure it's valid.
phone_number = ""               # Enter your 10 digit number in quotes Eg: "9876543210"

# What is your current city?
current_city = ""               # Los Angeles, San Francisco, Bengaluru, etc.
'''
Note: If left empty as "", the bot will fill in location of jobs location.
'''

# Address, not so common question but some job applications make it required!
street = ""
state = ""
zipcode = ""
country = ""

## US Equal Opportunity questions
# What is your ethnicity or race? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
ethnicity = ""              # "Decline", "Hispanic/Latino", "American Indian or Alaska Native", "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander", "White", "Other"

# How do you identify yourself? If left empty as "", tool will not answer the question. However, note that some companies make compulsory to be answered
gender = ""                 # "Male", "Female", "Other", "Decline" or ""

# Are you physically disabled or have a history/record of having a disability? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
disability_status = "No"      # "Yes", "No", "Decline"

veteran_status = "No"         # "Yes", "No", "Decline"
##


'''
For string variables followed by comments with options, only use the answers from given options.
Some valid examples are:
* variable1 = "option1"         # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#
* variable2 = ""                # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#

Other variables are free text. No restrictions other than compulsory use of quotes.
Some valid examples are:
* variable3 = "Random Answer 5"         # Enter your answer. Eg: "Answer1", "Answer2"

Invalid inputs will result in an error!
'''




############################################################################################################
'''
License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
'''
############################################################################################################