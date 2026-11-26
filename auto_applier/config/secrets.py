'''
Author:     Himanshu Khurana
LinkedIn:   https://www.linkedin.com/in/himanshukhurana/

Copyright (C) 2024 Himanshu Khurana

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    24.12.3.10.30
'''


###################################################### CONFIGURE YOUR TOOLS HERE ######################################################

import os
# Login Credentials (use MY_USERNAME/MY_PASSWORD in .env to avoid OS environment conflicts)
username = os.getenv("MY_USERNAME", "")
password = os.getenv("MY_PASSWORD", "")


# Platform-specific Credentials (Optional - falls back to global username/password if empty)
linkedin_username = os.getenv("LINKEDIN_USERNAME") or username
linkedin_password = os.getenv("LINKEDIN_PASSWORD") or password
indeed_username = os.getenv("INDEED_USERNAME") or username
indeed_password = os.getenv("INDEED_PASSWORD") or password
naukri_username = os.getenv("NAUKRI_USERNAME") or username
naukri_password = os.getenv("NAUKRI_PASSWORD") or password
internshala_username = os.getenv("INTERNSHALA_USERNAME") or username
internshala_password = os.getenv("INTERNSHALA_PASSWORD") or password


## Artificial Intelligence (Beta Not-Recommended)
# Use AI
use_AI = True                         # True or False, Note: True or False are case-sensitive
'''
Note: Set it as True only if you want to use AI, and If you either have a
1. Local LLM model running on your local machine, with it's APIs exposed. Example softwares to achieve it are:
    a. Ollama - https://ollama.com/
    b. llama.cpp - https://github.com/ggerganov/llama.cpp
    c. LM Studio - https://lmstudio.ai/ (Recommended)
    d. Jan - https://jan.ai/
2. OR you have a valid OpenAI API Key, and money to spare, and you don't mind spending it.
CHECK THE OPENAI API PIRCES AT THEIR WEBSITE (https://openai.com/api/pricing/). 
'''

##> ------ Yang Li : MARKYangL - Feature ------
##> ------ Tim L : tulxoro - Refactor ------
# Select AI Provider
ai_provider = "gemini"               # "openai", "deepseek", "gemini"
'''
Note: Select your AI provider.
* "openai" - OpenAI API (GPT models) OR OpenAi-compatible APIs (like Ollama)
* "deepseek" - DeepSeek API (DeepSeek models)
* "gemini" - Google Gemini API (Gemini models)
* For any other models, keep it as "openai" if it is compatible with OpenAI's api.
'''



# Your LLM url or other AI api url and port
llm_api_url = ""       # Examples: "https://api.openai.com/v1/", "http://127.0.0.1:1234/v1/", "http://localhost:1234/v1/", "https://api.deepseek.com", "https://api.deepseek.com/v1"
'''
Note: Don't forget to add / at the end of your url. You may not need this if you are using Gemini.
'''

# Your LLM API key or other AI API key 
llm_api_key = os.getenv("API_KEY", "")            # Enter your API key in the quotes, make sure it's valid, if not will result in error.
'''
Note: Leave it empty as "" or "not-needed" if not needed. Else will result in error!
If you are using ollama, you MUST put "not-needed".
'''

# Your LLM model name or other AI model name
llm_model = "gemini-2.5-flash"          # Examples: "gpt-3.5-turbo", "gpt-4o", "llama-3.2-3b-instruct", "qwen3:latest", "gemini-pro", "gemini-1.5-flash", "gemini-2.5-flash", "deepseek-llm:latest"

llm_spec = "openai"                # Examples: "openai", "openai-like", "openai-like-github", "openai-like-mistral"
'''
Note: Currently "openai", "deepseek", "gemini" and "openai-like" api endpoints are supported.
Most LLMs are compatible with openai, so keeping it as "openai-like" will work.
'''

# # Yor local embedding model name or other AI Embedding model name
# llm_embedding_model = "nomic-embed-text-v1.5"

# Do you want to stream AI output?
stream_output = False                    # Examples: True or False. (False is recommended for performance, True is recommended for user experience!)
'''
Set `stream_output = True` if you want to stream AI output or `stream_output = False` if not.
'''
##




############################################################################################################
'''
License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
'''
############################################################################################################