"""
gRPC Server Interceptor for Keycloak JWT validation
"""
import asyncio
import time
from functools import wraps
from typing import Dict, Tuple, Optional, Callable, Any
import logging

import grpc
import httpx
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError

from config import Settings

logger = logging.getLogger(__name__)

def requires_role(role: str) -> Callable:
    """Decorator to check if the authenticated user has the required role"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(self, request, context, *args, **kwargs):
            metadata = dict(context.invocation_metadata())
            auth_header = metadata.get('authorization', '')
            
            if not auth_header.startswith('Bearer '):
                context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    'Missing or invalid Authorization header'
                )
                return
            
            token = auth_header.split(' ')[1]
            
            # Get unverified claims to check roles
            try:
                claims = jwt.get_unverified_claims(token)
                
                # Check realm roles
                realm_roles = claims.get('realm_access', {}).get('roles', [])
                # Also check resource access for client-specific roles
                resource_access = claims.get('resource_access', {})
                client_roles = []
                for client, access in resource_access.items():
                    client_roles.extend(access.get('roles', []))
                
                all_roles = realm_roles + client_roles
                
                if role not in all_roles:
                    context.abort(
                        grpc.StatusCode.PERMISSION_DENIED,
                        f'Required role "{role}" not found in token. Available roles: {", ".join(all_roles)}'
                    )
                    return
                
                return await func(self, request, context, *args, **kwargs)
            except Exception as e:
                logger.error(f"Role check failed: {str(e)}")
                context.abort(grpc.StatusCode.INTERNAL, 'Role validation failed')
                return
                
        @wraps(func)
        def sync_wrapper(self, request, context, *args, **kwargs):
            metadata = dict(context.invocation_metadata())
            auth_header = metadata.get('authorization', '')
            
            if not auth_header.startswith('Bearer '):
                context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    'Missing or invalid Authorization header'
                )
                return
            
            token = auth_header.split(' ')[1]
            
            # Get unverified claims to check roles
            try:
                claims = jwt.get_unverified_claims(token)
                
                # Check realm roles
                realm_roles = claims.get('realm_access', {}).get('roles', [])
                # Also check resource access for client-specific roles
                resource_access = claims.get('resource_access', {})
                client_roles = []
                for client, access in resource_access.items():
                    client_roles.extend(access.get('roles', []))
                
                all_roles = realm_roles + client_roles
                
                if role not in all_roles:
                    context.abort(
                        grpc.StatusCode.PERMISSION_DENIED,
                        f'Required role "{role}" not found in token. Available roles: {", ".join(all_roles)}'
                    )
                    return
                
                return func(self, request, context, *args, **kwargs)
            except Exception as e:
                logger.error(f"Role check failed: {str(e)}")
                context.abort(grpc.StatusCode.INTERNAL, 'Role validation failed')
                return
        
        # Return appropriate wrapper based on whether func is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

class KeycloakTokenValidator:
    """Validates JWT tokens against Keycloak JWKS with caching and async support"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._jwks: Optional[Dict] = None
        self._jwks_last_fetched: float = 0
        self._jwks_ttl: int = 3600  # Cache JWKS for 1 hour
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
        
    async def get_jwks(self) -> Dict:
        """Fetch and cache JWKS from Keycloak with TTL"""
        current_time = time.time()
        
        # Check if we need to refresh the JWKS
        if not self._jwks or (current_time - self._jwks_last_fetched) > self._jwks_ttl:
            try:
                client = await self._get_http_client()
                response = await client.get(self.settings.KEYCLOAK_JWKS_URL)
                response.raise_for_status()
                self._jwks = response.json()
                self._jwks_last_fetched = current_time
                logger.debug("JWKS refreshed from Keycloak")
            except Exception as e:
                logger.error(f"Failed to fetch JWKS: {str(e)}")
                if not self._jwks:
                    raise
                # Use cached JWKS if available
                logger.warning("Using cached JWKS due to fetch failure")
                
        return self._jwks
    
    async def validate_token(self, token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Validate a JWT token against Keycloak JWKS
        Returns (is_valid, claims, error_message) tuple
        """
        try:
            jwks = await self.get_jwks()
            headers = jwt.get_unverified_headers(token)
            kid = headers.get('kid')
            
            if not kid:
                return False, None, "Missing 'kid' in token header"
                
            # Find the matching key
            key = None
            for k in jwks['keys']:
                if k['kid'] == kid:
                    key = k
                    break
                    
            if not key:
                return False, None, f"Key with kid '{kid}' not found in JWKS"
                
            # Validate the token
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=self.settings.KEYCLOAK_AUDIENCE,
                issuer=self.settings.KEYCLOAK_ISSUER,
                options={
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                }
            )
            
            # Additional validation
            current_time = time.time()
            
            # Check token expiration
            exp = claims.get('exp')
            if exp and exp < current_time:
                return False, None, "Token has expired"
                
            # Check not before
            nbf = claims.get('nbf')
            if nbf and nbf > current_time:
                return False, None, "Token not yet valid"
            
            return True, claims, None
            
        except ExpiredSignatureError:
            return False, None, "Token has expired"
        except JWTClaimsError as e:
            return False, None, f"Token claims validation failed: {str(e)}"
        except JWTError as e:
            return False, None, f"Token validation failed: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {str(e)}")
            return False, None, "Internal token validation error"
            
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Async gRPC interceptor that validates Keycloak tokens"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.validator = KeycloakTokenValidator(settings)
        # Track public methods that don't require authentication
        self.public_methods = {
            # Add any public methods here if needed
        }
        
    async def intercept_service(self, continuation, handler_call_details):
        """Intercept and validate each gRPC call"""
        
        method_name = handler_call_details.method
        
        # Skip authentication for public methods
        if method_name in self.public_methods:
            return await continuation(handler_call_details)
        
        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata)
        auth_header = metadata.get('authorization', '')
        
        # Check auth header format
        if not auth_header.startswith('Bearer '):
            return self._create_abort_handler(
                grpc.StatusCode.UNAUTHENTICATED, 
                'Missing or invalid Authorization header. Please provide: Authorization: Bearer <token>'
            )
        
        # Extract and validate token
        token = auth_header.split(' ')[1]
        
        try:
            is_valid, claims, error_msg = await self.validator.validate_token(token)
            
            if not is_valid:
                error_detail = f'Token validation failed: {error_msg or "Unknown error"}'
                return self._create_abort_handler(
                    grpc.StatusCode.UNAUTHENTICATED, 
                    error_detail
                )
            
            # Add claims to context for use in handlers
            # We can't directly modify the context, but the handler can re-extract the token
            logger.debug(f"Token validated successfully for method {method_name}")
            
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {str(e)}")
            return self._create_abort_handler(
                grpc.StatusCode.INTERNAL, 
                'Internal authentication error'
            )
        
        # Continue with the call
        return await continuation(handler_call_details)
    
    def _create_abort_handler(self, code: grpc.StatusCode, details: str):
        """Helper to create an abort handler with specific status"""
        async def abort_handler(request, context):
            context.abort(code, details)
        
        return grpc.unary_unary_rpc_method_handler(abort_handler)
        
    async def close(self):
        """Close resources"""
        await self.validator.close()