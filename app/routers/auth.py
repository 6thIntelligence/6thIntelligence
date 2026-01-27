from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import database
from app.services import auth_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@router.post("/api/auth/signup")
async def signup(email: str = Form(...), password: str = Form(...), db: Session = Depends(database.get_db)):
    # Check if user exists
    user = db.query(database.User).filter(database.User.email == email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = auth_service.get_password_hash(password)
    new_user = database.User(email=email, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/api/auth/login")
async def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(database.get_db)):
    user = db.query(database.User).filter(database.User.email == email).first()
    if not user or not auth_service.verify_password(password, user.hashed_password):
        # On failure, stay on login
        return templates.TemplateResponse("login.html", {"request": {}, "error": "Invalid email or password"})
    
    access_token = auth_service.create_access_token(data={"sub": user.email})
    
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    # Store token in HttpOnly cookie for security
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response
