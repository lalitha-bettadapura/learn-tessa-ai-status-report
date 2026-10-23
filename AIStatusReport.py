import streamlit as st
import pandas as pd
import os
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from local .env file if present
load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="QA Mentor - AI Assistant Suite",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load configuration from environment variables (with fallback to Streamlit secrets for Cloud deployment)
API_KEY = os.getenv("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if "GOOGLE_API_KEY" in st.secrets else None)
MODEL_CHOICE = os.getenv("MODEL", "gemini-3.5-flash-lite")

# Initialize Gemini Client with custom HttpOptions and environment API key
try:
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY is missing from environment variables (.env) and Streamlit Secrets.")
    
    client = genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(client_args={"verify": False})
    )
except Exception as e:
    st.error(f"🚨 Initialization Error: {e}. Please check your .env file or Streamlit Secrets configuration.")
    st.stop()

EXCEL_FILE = "status_reports.xlsx"

def load_or_create_excel():
    """Loads the existing Excel log or creates a new one with required headers."""
    if os.path.exists(EXCEL_FILE):
        return pd.read_excel(EXCEL_FILE)
    else:
        df = pd.DataFrame(columns=[
            "Company Name",
            "Project Name",
            "Tester Name",
            "Date",
            "Activities Performed",
            "Test Cases Executed",
            "Defects Identified"
        ])
        df.to_excel(EXCEL_FILE, index=False)
        return df

# ---------------------------------------------------------
# Sidebar Navigation Menu
# ---------------------------------------------------------
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
    st.title("📊 AI Status Report Assistant")
    st.markdown("**Company:** QA Mentor Testing Services | **Project:** Learning Tessa AI")
    st.markdown("Paste your raw notes or daily updates below. AI will transform them into a structured executive status report and log them automatically.")

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
        # Validate mandatory fields
        if not tester_name.strip():
            st.warning("⚠️ Tester Name is mandatory.")
        elif not raw_updates.strip():
            st.warning("⚠️ Activities Performed / Raw Updates is mandatory.")
        else:
            with st.spinner("Processing update ..."):
                # System Instructions with PTO & Status Formatting Rules
                system_instruction = (
                    "You are a professional status report assistant. "
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
                    
                    # Check if PTO / Leave was detected by Gemini or text keywords
                    is_pto = "[PTO]" in output_text or any(kw in raw_updates.lower() for kw in ["pto", "leave", "vacation", "day off", "out of office", "ooo", "not working"])

                    if is_pto:
                        st.info(f"🌴 **Leave/PTO Acknowledged:** {output_text.replace('[PTO]', '').strip()}")
                        st.warning("🚫 Since you are on leave/PTO, the Excel status file was **not** updated, and no further status report is required.")
                    else:
                        st.success("✅ Status report successfully generated!")
                        st.markdown("### 📋 Status Report")
                        st.markdown(output_text)

                        # Handle optional metrics (default to "0" if left blank)
                        tc_val = test_cases_executed.strip() if test_cases_executed.strip() else "0"
                        def_val = defects_identified.strip() if defects_identified.strip() else "0"

                        # Save record to Excel sheet
                        df = load_or_create_excel()
                        new_row = {
                            "Company Name": company_name,
                            "Project Name": project_name,
                            "Tester Name": tester_name.strip(),
                            "Date": str(report_date),
                            "Activities Performed": output_text,
                            "Test Cases Executed": tc_val,
                            "Defects Identified": def_val
                        }
                        
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        df.to_excel(EXCEL_FILE, index=False)
                        st.info("💾 Record successfully logged to the project.  Thank You")

                except Exception as e:
                    st.error(f"❌ Error communicating with API: {e}")

    # Section to view and download all logged status reports
    st.markdown("---")
    st.subheader("📁 Project Status Log (All Testers)")

    if os.path.exists(EXCEL_FILE):
        df_existing = pd.read_excel(EXCEL_FILE)
        if not df_existing.empty:
            st.dataframe(df_existing, use_container_width=True)
            
            with open(EXCEL_FILE, "rb") as f:
                st.download_button(
                    label="📥 Download Full Status Report Excel",
                    data=f,
                    file_name="status_reports.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("No status reports logged yet.")
    else:
        st.info("No status reports logged yet.")

# ---------------------------------------------------------
# OPTION 2: General Chat with AI
# ---------------------------------------------------------
elif menu_option == "2. General Chat with AI":
    st.title("💬 General Chat with AI")
    st.markdown("Access your general AI assistant below or open it in a full standalone window.")
    
    chat_url = "https://aitesters1.streamlit.app/"
    
    st.markdown(f"🔗 [**Click here to open General Chat AI in a new tab**]({chat_url})")
    st.markdown("---")
    
    # Embed existing Streamlit app inside an iframe
    st.components.v1.iframe(chat_url, height=750, scrolling=True)