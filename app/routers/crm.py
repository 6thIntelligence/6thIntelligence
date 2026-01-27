"""
CRM Router for Enterprise Bot
Handles OAuth2 authentication and CRM operations
"""
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from app.services.crm_service import get_crm_service
from app.routers.admin import get_current_user

router = APIRouter(prefix="/api/crm", tags=["CRM"])

class ContactCreate(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

class ConversationLog(BaseModel):
    contact_id: str
    session_id: str
    summary: str

@router.get("/auth")
async def initiate_oauth(
    provider: str = Query(default="hubspot", description="CRM provider: hubspot, salesforce, zoho"),
    user: str = Depends(get_current_user)
):
    """
    Initiate OAuth2 authentication with CRM provider.
    Returns the authorization URL to redirect the user.
    """
    try:
        crm = get_crm_service()
        auth_url = crm.get_auth_url(provider)
        return {"auth_url": auth_url, "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from CRM"),
    state: str = Query(default=None)
):
    """
    Handle OAuth2 callback from CRM provider.
    Exchanges authorization code for access tokens.
    """
    try:
        crm = get_crm_service()
        result = await crm.exchange_code(code)
        
        # Redirect back to admin with success message
        return RedirectResponse(url="/admin?crm_connected=true")
    except Exception as e:
        return RedirectResponse(url=f"/admin?crm_error={str(e)}")

@router.get("/status")
async def get_connection_status(user: str = Depends(get_current_user)):
    """Get current CRM connection status"""
    crm = get_crm_service()
    return crm.get_connection_status()

@router.post("/disconnect")
async def disconnect_crm(user: str = Depends(get_current_user)):
    """Disconnect from CRM"""
    crm = get_crm_service()
    crm.disconnect()
    return {"status": "disconnected"}

@router.get("/contacts/search")
async def search_contacts(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    user: str = Depends(get_current_user)
):
    """Search for contacts in CRM"""
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Provide email or phone to search")
    
    try:
        crm = get_crm_service()
        contact = await crm.lookup_contact(email=email, phone=phone)
        
        if contact:
            return {"found": True, "contact": contact}
        return {"found": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/contacts")
async def create_contact(
    contact: ContactCreate,
    user: str = Depends(get_current_user)
):
    """Create a new contact in CRM"""
    try:
        crm = get_crm_service()
        result = await crm.create_contact(contact.dict())
        return {"status": "created", "contact": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conversations/log")
async def log_conversation(
    log: ConversationLog,
    user: str = Depends(get_current_user)
):
    """Log a conversation to a contact in CRM"""
    try:
        crm = get_crm_service()
        result = await crm.log_conversation(
            contact_id=log.contact_id,
            session_id=log.session_id,
            summary=log.summary
        )
        return {"status": "logged", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/test")
async def test_crm_connection(user: str = Depends(get_current_user)):
    """Test CRM connection by making a simple API call"""
    crm = get_crm_service()
    
    if not crm.is_connected():
        return {"status": "not_connected", "message": "CRM not connected. Please authenticate first."}
    
    try:
        # Try to refresh token to verify connection
        await crm.refresh_access_token()
        return {"status": "connected", "provider": crm.provider}
    except Exception as e:
        return {"status": "error", "message": str(e)}
