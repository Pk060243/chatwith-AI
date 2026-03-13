from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


def custom_auth_key(request:Request):
    user_id = request.headers.get("X-User-ID")
    client_ip = request.headers.get("X-Client-IP")
    
    if user_id and user_id != 'Guest':
        return f"user_{user_id}"
    return f"ip_{client_ip}"
limiter = Limiter(key_func=custom_auth_key)
