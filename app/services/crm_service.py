"""
CRM Service for Enterprise Bot
Provides OAuth2 authentication and CRM operations
Supports multiple CRM providers: HubSpot, Salesforce, Zoho (extensible)
"""
import httpx
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

# CRM Provider configurations
CRM_PROVIDERS = {
    "hubspot": {
        "auth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "api_base": "https://api.hubapi.com",
        "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"]
    },
    "salesforce": {
        "auth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "api_base": "",  # Dynamic per instance
        "scopes": ["api", "refresh_token"]
    },
    "zoho": {
        "auth_url": "https://accounts.zoho.com/oauth/v2/auth",
        "token_url": "https://accounts.zoho.com/oauth/v2/token",
        "api_base": "https://www.zohoapis.com/crm/v2",
        "scopes": ["ZohoCRM.modules.contacts.READ", "ZohoCRM.modules.contacts.WRITE"]
    }
}

class CRMService:
    def __init__(self):
        self.provider = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self._load_credentials()
    
    def _load_credentials(self):
        """Load CRM credentials from storage"""
        try:
            with open("data/crm_credentials.json", "r") as f:
                creds = json.load(f)
                self.provider = creds.get("provider")
                self.access_token = creds.get("access_token")
                self.refresh_token = creds.get("refresh_token")
                if creds.get("expires_at"):
                    self.expires_at = datetime.fromisoformat(creds["expires_at"])
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    def _save_credentials(self):
        """Save CRM credentials to storage"""
        import os
        os.makedirs("data", exist_ok=True)
        
        creds = {
            "provider": self.provider,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
        with open("data/crm_credentials.json", "w") as f:
            json.dump(creds, f)
    
    def get_auth_url(self, provider: str = "hubspot") -> str:
        """Generate OAuth2 authorization URL"""
        from app.services.settings_service import load_settings
        settings = load_settings()
        
        crm_config = settings.get("crm", {})
        client_id = crm_config.get("client_id", "")
        redirect_uri = crm_config.get("redirect_uri", "http://localhost:8000/api/crm/callback")
        
        if not client_id:
            raise ValueError("CRM client_id not configured in settings")
        
        if provider not in CRM_PROVIDERS:
            raise ValueError(f"Unsupported CRM provider: {provider}")
        
        config = CRM_PROVIDERS[provider]
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(config["scopes"]),
            "response_type": "code"
        }
        
        # Provider-specific params
        if provider == "hubspot":
            params["optional_scope"] = ""
        elif provider == "salesforce":
            params["prompt"] = "consent"
        elif provider == "zoho":
            params["access_type"] = "offline"
        
        self.provider = provider
        return f"{config['auth_url']}?{urlencode(params)}"
    
    async def exchange_code(self, code: str, provider: str = None) -> dict:
        """Exchange authorization code for access tokens"""
        from app.services.settings_service import load_settings
        settings = load_settings()
        
        crm_config = settings.get("crm", {})
        client_id = crm_config.get("client_id", "")
        client_secret = crm_config.get("client_secret", "")
        redirect_uri = crm_config.get("redirect_uri", "http://localhost:8000/api/crm/callback")
        
        provider = provider or self.provider or "hubspot"
        config = CRM_PROVIDERS[provider]
        
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Token exchange failed: {response.text}")
            
            tokens = response.json()
            
            self.access_token = tokens.get("access_token")
            self.refresh_token = tokens.get("refresh_token")
            
            expires_in = tokens.get("expires_in", 3600)
            self.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            self.provider = provider
            
            self._save_credentials()
            
            return {
                "success": True,
                "provider": provider,
                "expires_at": self.expires_at.isoformat()
            }
    
    async def refresh_access_token(self) -> bool:
        """Refresh expired access token"""
        if not self.refresh_token or not self.provider:
            return False
        
        from app.services.settings_service import load_settings
        settings = load_settings()
        
        crm_config = settings.get("crm", {})
        client_id = crm_config.get("client_id", "")
        client_secret = crm_config.get("client_secret", "")
        
        config = CRM_PROVIDERS[self.provider]
        
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": self.refresh_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(config["token_url"], data=data)
            
            if response.status_code != 200:
                return False
            
            tokens = response.json()
            self.access_token = tokens.get("access_token")
            
            if tokens.get("refresh_token"):
                self.refresh_token = tokens["refresh_token"]
            
            expires_in = tokens.get("expires_in", 3600)
            self.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            self._save_credentials()
            return True
    
    async def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        if not self.access_token:
            raise Exception("CRM not connected. Please authenticate first.")
        
        if self.expires_at and datetime.utcnow() >= self.expires_at:
            if not await self.refresh_access_token():
                raise Exception("CRM token expired and refresh failed. Please re-authenticate.")
    
    async def _make_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make authenticated request to CRM API"""
        await self._ensure_valid_token()
        
        config = CRM_PROVIDERS[self.provider]
        url = f"{config['api_base']}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code >= 400:
                raise Exception(f"CRM API error: {response.text}")
            
            return response.json() if response.text else {}
    
    async def lookup_contact(self, email: str = None, phone: str = None) -> Optional[dict]:
        """Search for a contact by email or phone"""
        if self.provider == "hubspot":
            if email:
                try:
                    result = await self._make_request(
                        "GET", 
                        f"/crm/v3/objects/contacts/{email}?idProperty=email"
                    )
                    return result
                except:
                    return None
        
        return None
    
    async def create_contact(self, data: dict) -> dict:
        """Create a new contact in CRM"""
        if self.provider == "hubspot":
            payload = {
                "properties": {
                    "email": data.get("email"),
                    "firstname": data.get("first_name", ""),
                    "lastname": data.get("last_name", ""),
                    "phone": data.get("phone", "")
                }
            }
            return await self._make_request("POST", "/crm/v3/objects/contacts", payload)
        
        raise NotImplementedError(f"create_contact not implemented for {self.provider}")
    
    async def update_contact(self, contact_id: str, data: dict) -> dict:
        """Update an existing contact"""
        if self.provider == "hubspot":
            payload = {"properties": data}
            return await self._make_request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", payload)
        
        raise NotImplementedError(f"update_contact not implemented for {self.provider}")
    
    async def log_conversation(self, contact_id: str, session_id: str, summary: str):
        """Log a conversation/engagement to the contact"""
        if self.provider == "hubspot":
            # Create a note
            payload = {
                "properties": {
                    "hs_note_body": f"Chatbot Conversation (Session: {session_id[:8]}...)\n\n{summary}",
                    "hs_timestamp": datetime.utcnow().isoformat() + "Z"
                },
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 10}]
                    }
                ]
            }
            return await self._make_request("POST", "/crm/v3/objects/notes", payload)
        
        raise NotImplementedError(f"log_conversation not implemented for {self.provider}")
    
    def is_connected(self) -> bool:
        """Check if CRM is connected"""
        return bool(self.access_token and self.provider)
    
    def get_connection_status(self) -> dict:
        """Get current CRM connection status"""
        return {
            "connected": self.is_connected(),
            "provider": self.provider,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expired": self.expires_at and datetime.utcnow() >= self.expires_at if self.expires_at else False
        }
    
    def disconnect(self):
        """Disconnect from CRM"""
        self.provider = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        
        import os
        try:
            os.remove("data/crm_credentials.json")
        except FileNotFoundError:
            pass

# Singleton instance
crm_service = CRMService()

def get_crm_service() -> CRMService:
    """Get the CRM service instance"""
    return crm_service
