import httpx
from typing import List, Dict, Any

OPENROUTER_API_URL = "https://openrouter.ai/api/v1"

async def fetch_available_models() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetches models from OpenRouter and groups them by Maker (Organization).
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OPENROUTER_API_URL}/models")
            if response.status_code != 200:
                from app.services import logging_service
                logging_service.log_error(
                    "openrouter_api_error",
                    f"Status {response.status_code}: {response.text}",
                    context={"url": f"{OPENROUTER_API_URL}/models"}
                )
                return {}
            
            data = response.json()
            models = data.get("data", [])
            
            # Group by Architecture or 'pricing.developer' if avail, 
            # but usually splitting the ID (e.g. 'openai/gpt-4') is best.
            
            grouped = {}
            
            for m in models:
                model_id = m.get("id", "")
                name = m.get("name", model_id)
                # Makers are usually the prefix before '/'
                if "/" in model_id:
                    maker = model_id.split("/")[0].capitalize()
                else:
                    maker = "Other"
                
                if maker not in grouped:
                    grouped[maker] = []
                
                # Parse pricing to determine if free
                pricing = m.get("pricing", {})
                is_free = False
                try:
                    # Check if string "0" or float 0
                    prompt_price = float(pricing.get("prompt", 0))
                    completion_price = float(pricing.get("completion", 0))
                    if prompt_price == 0 and completion_price == 0:
                        is_free = True
                except:
                    pass

                grouped[maker].append({
                    "id": model_id,
                    "name": name,
                    "context_length": m.get("context_length", 0),
                    "pricing": pricing,
                    "is_free": is_free
                })
            
            # Sort makers alphabetically
            return dict(sorted(grouped.items()))
            
        except Exception as e:
            from app.services import logging_service
            logging_service.log_error(
                "openrouter_fetch_error",
                str(e),
                context={"url": f"{OPENROUTER_API_URL}/models"}
            )
            return {}

async def validate_key(api_key: str) -> bool:
    # Simple check, maybe try to fetch models with auth or user limits
    # OpenRouter /auth/key endpoint
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{OPENROUTER_API_URL}/auth/key", headers=headers)
            return resp.status_code == 200
        except:
            return False

async def generate_fast_summary(prompt: str) -> str:
    """
    Generates a concise summary for state management using a fast model.
    """
    from app.services.settings_service import load_settings
    settings = load_settings()
    api_key = settings.get("openrouter_api_key")
    # Use a cheap, fast model for summarization to minimize latency
    model = "openai/gpt-3.5-turbo" 
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{OPENROUTER_API_URL}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            return "[Summary Generation Failed]"
        except Exception as e:
            return f"[Error: {str(e)}]"
