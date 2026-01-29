import json
import os
from typing import Dict, Any

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "openrouter_api_key": "",
    "model": "google/gemma-3n-e2b-it:free", 
    "temperature": 0.1,
    "system_persona": "You are a research-focused AI for 6thIntelligence. Your goal is to provide data-driven insights into Causal-Fractal RAG architectures. Maintain academic rigor and professional tone.",
    "persona_type": "research",
    "model_name": "Gemma 3n 2B (free)",
    "response_delay_min": 0.0,
    "response_delay_max": 0.0,
    "db_connection": "sqlite:///6th_intelligence.db",
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
