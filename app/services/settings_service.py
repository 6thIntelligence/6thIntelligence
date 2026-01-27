import json
import os
from typing import Dict, Any

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "openrouter_api_key": "",
    "model": "openai/gpt-3.5-turbo", 
    "temperature": 0.7,
    "system_persona": "Persona definition:\nName: Ramos from ExpertListing.\nRole: Human support team member.\nIdentity: Always human.\nNo AI references.\nNo automation talk.\n\nGuardrails:\nNever mention AI.\nNever state you are an AI.\nNever hallucinate facts.\nIf information is missing, do not guess.\nAdmit when you lack specific data.\n\nProfessionalism:\nMaintain a spartan, calm, human tone.\nUse active voice.\nAvoid markdown and asterisks.",
    "persona_type": "general",
    "model_name": "GPT-3.5 Turbo",
    "response_delay_min": 5.0,
    "response_delay_max": 10.0,
    "db_connection": "sqlite:///enterprise_bot.db",
    "crm_api_key": ""
}

def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        # Create file directly to avoid recursion via save_settings
        with open(SETTINGS_FILE, "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        return DEFAULT_SETTINGS
    
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_SETTINGS

def save_settings(settings: Dict[str, Any]):
    # Read directly to avoid recursion if we used load_settings() here while it was also trying to save
    current = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                current = json.load(f)
        except:
            current = DEFAULT_SETTINGS.copy()
    else:
        current = DEFAULT_SETTINGS.copy()
        
    current.update(settings)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(current, f, indent=4)

def get_setting(key: str, default=None):
    return load_settings().get(key, default)
