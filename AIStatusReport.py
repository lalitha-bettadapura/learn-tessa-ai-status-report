import streamlit as st
import pandas as pd
import os
import gspread
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests
import google.auth.transport.requests
from google.oauth2.service_account import Credentials
from urllib3.exceptions import InsecureRequestWarning

# Load local environment variables from .env if present
load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="QA Mentor - AI Assistant Suite",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Safe Configuration Loading (Checks .env first, then falls back safely to Streamlit secrets if deployed)
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_CHOICE = os.getenv("MODEL", "gemini-3.5-flash-lite")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Learning Tessa AI Status Log")
GCP_CREDS = None

try:
    if not API_KEY and "GOOGLE_API_KEY" in st.secrets:
        API_KEY = st.secrets["GOOGLE_API_KEY"]
    if MODEL_CHOICE == "gemini-3.5-flash-lite" and "MODEL" in st.secrets:
        MODEL_CHOICE = st.secrets["MODEL"]
    if SPREADSHEET_NAME == "Learning Tessa AI Status Log" and "SPREADSHEET_NAME" in st.secrets:
        SPREADSHEET_NAME = st.secrets["SPREADSHEET_NAME"]
    
    if "gcp_service_account" in st.secrets:
        GCP_CREDS = dict(st.secrets["gcp_service_account"])
except Exception:
    # Safely ignored locally when no secrets.toml file exists
    pass

# Initialize Gemini Client
try:
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY missing. Please set it in your local .env file or Streamlit secrets.")
    client = genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(client_args={"verify": False})
    )
except Exception as e:
    st.error(f"🚨 Gemini Initialization Error: {e}")
    st.stop()

# Suppress insecure request warnings for local development SSL bypass
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def get_google_sheet():
    """Authenticates with Google Sheets API and returns the target worksheet (with SSL verification bypassed)."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Load credentials from Streamlit secrets dictionary or local service_account.json file
        if GCP_CREDS:
            creds = Credentials.from_service_account_info(GCP_CREDS, scopes=scopes)
        elif os.path.exists("service_account.json"):
            creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)
        else:
            return None, "Google Service Account credentials not found. Please place 'service_account.json' in this folder."
            
        # Create a custom session with SSL verification disabled for corporate proxy/certificates
        custom_session = requests.Session()
        custom_session.verify = False
        
        # Pass the custom session into the token-refresh request handler
        auth_request = google.auth.transport.requests.Request(session=custom_session)
        creds.refresh(auth_request)
        
        # Initialize gspread client with our custom session
        auth_session = google.auth.transport.requests.AuthorizedSession(creds)
        auth_session.verify = False
        
        gc = gspread.Client(auth=creds, session=auth_session)
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        return worksheet, None
        
    except Exception as e:
        return None, str(e)

# Sidebar Navigation Menu
st.sidebar.title("📌 Navigation")
menu_option = st.sidebar.radio(
    "Select Feature:",
    [
        "1. Submit Status Report to AI",
        "2. General Chat with AI"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(f"**QA Mentor Testing Services**\nProject: *Learning Tessa AI*\nModel: `{MODEL_CHOICE}`")

# ---------------------------------------------------------
# OPTION 1: Submit Status Report to AI
# ---------------------------------------------------------
if menu_option == "1. Submit Status Report to AI":
    st.title("📊 Executive Status Report Assistant")
    st.markdown("**Company:** QA Mentor Testing Services | **Project:** Learning Tessa AI")
    st.markdown("Paste your raw notes or daily updates below. Gemini will transform them into a structured status report and append it to Google Sheets.")

    # Status Report Input Form
    with st.form("status_form"):
        col1, col2 = st.columns(2)
        with col1:
            tester_name = st.text_input("Tester Name *", placeholder="Enter your full name")
            company_name = st.text_input("Company Name", value="QA Mentor Testing Services")
        with col2:
            project_name = st.text_input("Project Name", value="Learning Tessa AI")
            report_date = st.date_input("Date *", value=datetime.today())
        
        col3, col4 = st.columns(2)
        with col3:
            test_cases_executed = st.text_input(
                "Test Cases Executed (Optional)", 
                placeholder="e.g., 45 or leave blank / 0"
            )
        with col4:
            defects_identified = st.text_input(
                "Defects Identified (Optional)", 
                placeholder="e.g., 2 or leave blank / 0"
            )
        
        raw_updates = st.text_area(
            "Activities Performed / Raw Updates *", 
            placeholder="Paste your raw notes, bullet points, or type if you are on leave/PTO...",
            height=150
        )
        
        submit_btn = st.form_submit_button("🚀 Submit Status Report")

    if submit_btn:
        if not tester_name.strip():
            st.warning("⚠️ Tester Name is mandatory.")
        elif not raw_updates.strip():
            st.warning("⚠️ Activities Performed / Raw Updates is mandatory.")
        else:
            with st.spinner("Processing update with Gemini..."):
                system_instruction = (
                    "You are a professional executive status report assistant. "
                    "First, analyze the user's input. If the user states they are on leave, PTO, vacation, out of office, or off for the day, "
                    "you must start your response with '[PTO]' followed by a polite, professional acknowledgment of their leave. "
                    "If it is a regular work update, transform the raw notes into a clean, structured executive markdown report with exactly these three sections:\n"
                    "1. Accomplishments / Completed Tasks\n"
                    "2. Work in Progress (WIP)\n"
                    "3. Blockers / Key Risks\n"
                )
                
                prompt = f"Raw Update Notes:\n{raw_updates}\n\nAnalyze this update."

                try:
                    response = client.models.generate_content(
                        model=MODEL_CHOICE,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3,
                        ),
                    )
                    output_text = response.text
                    
                    is_pto = "[PTO]" in output_text or any(kw in raw_updates.lower() for kw in ["pto", "leave", "vacation", "day off", "out of office", "ooo", "not working"])

                    if is_pto:
                        st.info(f"🌴 **Leave/PTO Acknowledged:** {output_text.replace('[PTO]', '').strip()}")
                        st.warning("🚫 Since you are on leave/PTO, the Google Sheet was **not** updated.")
                    else:
                        st.success("✅ Status report successfully generated!")
                        st.markdown("### 📋 Formatted Executive Status Report")
                        st.markdown(output_text)

                        tc_val = test_cases_executed.strip() if test_cases_executed.strip() else "0"
                        def_val = defects_identified.strip() if defects_identified.strip() else "0"

                        # Append row to Google Sheets
                        worksheet, err = get_google_sheet()
                        if err:
                            st.error(f"❌ Failed to connect to Google Sheets: {err}")
                        else:
                            row_data = [
                                company_name,
                                project_name,
                                tester_name.strip(),
                                str(report_date),
                                output_text,
                                tc_val,
                                def_val
                            ]
                            worksheet.append_row(row_data)
                            st.info("☁️ Record successfully saved directly to Google Sheets!")

                except Exception as e:
                    st.error(f"❌ Error communicating with Gemini API: {e}")

    # View Log directly from Google Sheets
    st.markdown("---")
    st.subheader("📁 Project Status Log (Live Google Sheet)")

    worksheet, err = get_google_sheet()
    if worksheet:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No records found in Google Sheet yet.")
    else:
        st.warning(f"Unable to load live log: {err}")

# ---------------------------------------------------------
# OPTION 2: General Chat with AI
# ---------------------------------------------------------
elif menu_option == "2. General Chat with AI":
    st.title("💬 General Chat with AI")
    st.markdown("Access your general AI assistant below or open it in a full standalone window.")
    
    chat_url = "https://aitesters1.streamlit.app/"
    
    st.markdown(f"🔗 [**Click here to open General Chat AI in a new tab**]({chat_url})")
    st.markdown("---")
    
    st.components.v1.iframe(chat_url, height=750, scrolling=True)