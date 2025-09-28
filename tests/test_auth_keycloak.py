"""
Unit tests for Keycloak authentication and authorization
"""
import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
import time

import grpc
from jose import jwt

from app.auth_interceptor import (
    AuthInterceptor, 
    KeycloakTokenValidator, 
    requires_role
)
from app.config import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing"""
    settings = Settings()
    settings.KEYCLOAK_ISSUER = "http://localhost:8080/realms/finstack"
    settings.KEYCLOAK_AUDIENCE = "paymentservice"
    settings.KEYCLOAK_JWKS_URL = "http://localhost:8080/realms/finstack/protocol/openid-connect/certs"
    return settings


@pytest.fixture
def sample_jwks():
    """Sample JWKS for testing"""
    return {
        "keys": [
            {
                "kid": "test-key-id",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "sample-n-value",
                "e": "AQAB"
            }
        ]
    }


@pytest.fixture
def sample_token_claims():
    """Sample JWT claims for testing"""
    current_time = int(time.time())
    return {
        "iss": "http://localhost:8080/realms/finstack",
        "aud": "paymentservice",
        "sub": "user-123",
        "iat": current_time - 10,
        "exp": current_time + 3600,
        "nbf": current_time - 10,
        "realm_access": {
            "roles": ["payment:read", "payment:write"]
        },
        "resource_access": {
            "paymentservice": {
                "roles": ["payment:admin"]
            }
        }
    }


class TestKeycloakTokenValidator:
    """Test cases for KeycloakTokenValidator"""
    
    @pytest.mark.asyncio
    async def test_get_jwks_success(self, mock_settings, sample_jwks):
        """Test successful JWKS retrieval"""
        validator = KeycloakTokenValidator(mock_settings)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_response = Mock()
            mock_response.json.return_value = sample_jwks
            mock_response.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response
            
            jwks = await validator.get_jwks()
            
            assert jwks == sample_jwks
            mock_client.get.assert_called_once_with(mock_settings.KEYCLOAK_JWKS_URL)
    
    @pytest.mark.asyncio
    async def test_get_jwks_caching(self, mock_settings, sample_jwks):
        """Test JWKS caching behavior"""
        validator = KeycloakTokenValidator(mock_settings)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_response = Mock()
            mock_response.json.return_value = sample_jwks
            mock_response.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response
            
            # First call should fetch from Keycloak
            jwks1 = await validator.get_jwks()
            
            # Second call should use cache
            jwks2 = await validator.get_jwks()
            
            assert jwks1 == jwks2
            mock_client.get.assert_called_once()  # Only called once due to caching
    
    @pytest.mark.asyncio
    async def test_validate_token_success(self, mock_settings, sample_jwks, sample_token_claims):
        """Test successful token validation"""
        validator = KeycloakTokenValidator(mock_settings)
        
        # Mock JWKS retrieval
        validator._jwks = sample_jwks
        validator._jwks_last_fetched = time.time()
        
        # Create a mock token
        test_token = "test.jwt.token"
        
        with patch('jose.jwt.get_unverified_headers') as mock_headers, \
             patch('jose.jwt.decode') as mock_decode:
            
            mock_headers.return_value = {"kid": "test-key-id"}
            mock_decode.return_value = sample_token_claims
            
            is_valid, claims, error = await validator.validate_token(test_token)
            
            assert is_valid is True
            assert claims == sample_token_claims
            assert error is None
    
    @pytest.mark.asyncio
    async def test_validate_token_missing_kid(self, mock_settings, sample_jwks):
        """Test token validation with missing kid"""
        validator = KeycloakTokenValidator(mock_settings)
        validator._jwks = sample_jwks
        validator._jwks_last_fetched = time.time()
        
        test_token = "test.jwt.token"
        
        with patch('jose.jwt.get_unverified_headers') as mock_headers:
            mock_headers.return_value = {}  # No kid
            
            is_valid, claims, error = await validator.validate_token(test_token)
            
            assert is_valid is False
            assert claims is None
            assert "Missing 'kid'" in error
    
    @pytest.mark.asyncio
    async def test_validate_token_key_not_found(self, mock_settings, sample_jwks):
        """Test token validation with unknown key ID"""
        validator = KeycloakTokenValidator(mock_settings)
        validator._jwks = sample_jwks
        validator._jwks_last_fetched = time.time()
        
        test_token = "test.jwt.token"
        
        with patch('jose.jwt.get_unverified_headers') as mock_headers:
            mock_headers.return_value = {"kid": "unknown-key-id"}
            
            is_valid, claims, error = await validator.validate_token(test_token)
            
            assert is_valid is False
            assert claims is None
            assert "not found in JWKS" in error


class TestAuthInterceptor:
    """Test cases for AuthInterceptor"""
    
    @pytest.mark.asyncio
    async def test_intercept_service_success(self, mock_settings):
        """Test successful request interception"""
        interceptor = AuthInterceptor(mock_settings)
        
        # Mock the token validator
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = (True, {"sub": "user-123"}, None)
        interceptor.validator = mock_validator
        
        # Mock handler call details
        mock_handler_details = Mock()
        mock_handler_details.method = "/payment.v1.PaymentService/CreatePayment"
        mock_handler_details.invocation_metadata = [
            ("authorization", "Bearer valid-token")
        ]
        
        # Mock continuation
        mock_continuation = AsyncMock()
        mock_continuation.return_value = "success"
        
        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)
        
        assert result == "success"
        mock_continuation.assert_called_once_with(mock_handler_details)
    
    @pytest.mark.asyncio
    async def test_intercept_service_missing_auth_header(self, mock_settings):
        """Test request with missing authorization header"""
        interceptor = AuthInterceptor(mock_settings)
        
        mock_handler_details = Mock()
        mock_handler_details.method = "/payment.v1.PaymentService/CreatePayment"
        mock_handler_details.invocation_metadata = []  # No auth header
        
        mock_continuation = AsyncMock()
        
        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)
        
        # Should return an abort handler
        assert callable(result)
        mock_continuation.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_intercept_service_invalid_token(self, mock_settings):
        """Test request with invalid token"""
        interceptor = AuthInterceptor(mock_settings)
        
        # Mock the token validator to return invalid token
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = (False, None, "Token expired")
        interceptor.validator = mock_validator
        
        mock_handler_details = Mock()
        mock_handler_details.method = "/payment.v1.PaymentService/CreatePayment"
        mock_handler_details.invocation_metadata = [
            ("authorization", "Bearer invalid-token")
        ]
        
        mock_continuation = AsyncMock()
        
        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)
        
        # Should return an abort handler
        assert callable(result)
        mock_continuation.assert_not_called()


class TestRequiresRoleDecorator:
    """Test cases for requires_role decorator"""
    
    def test_requires_role_success(self, sample_token_claims):
        """Test successful role validation"""
        
        @requires_role("payment:write")
        def test_method(self, request, context):
            return "success"
        
        # Mock self, request, and context
        mock_self = Mock()
        mock_request = Mock()
        mock_context = Mock()
        mock_context.invocation_metadata.return_value = [
            ("authorization", "Bearer test-token")
        ]
        
        with patch('jose.jwt.get_unverified_claims') as mock_claims:
            mock_claims.return_value = sample_token_claims
            
            result = test_method(mock_self, mock_request, mock_context)
            
            assert result == "success"
            mock_context.abort.assert_not_called()
    
    def test_requires_role_missing_role(self, sample_token_claims):
        """Test role validation with missing required role"""
        
        @requires_role("payment:admin")  # Not in sample claims
        def test_method(self, request, context):
            return "success"
        
        mock_self = Mock()
        mock_request = Mock()
        mock_context = Mock()
        mock_context.invocation_metadata.return_value = [
            ("authorization", "Bearer test-token")
        ]
        
        # Remove the admin role from resource access for this test
        claims = sample_token_claims.copy()
        claims["resource_access"] = {}
        
        with patch('jose.jwt.get_unverified_claims') as mock_claims:
            mock_claims.return_value = claims
            
            test_method(mock_self, mock_request, mock_context)
            
            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED
    
    def test_requires_role_missing_auth_header(self):
        """Test role validation with missing authorization header"""
        
        @requires_role("payment:write")
        def test_method(self, request, context):
            return "success"
        
        mock_self = Mock()
        mock_request = Mock()
        mock_context = Mock()
        mock_context.invocation_metadata.return_value = []  # No auth header
        
        test_method(mock_self, mock_request, mock_context)
        
        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED
    
    @pytest.mark.asyncio
    async def test_requires_role_async_method(self, sample_token_claims):
        """Test role validation with async method"""
        
        @requires_role("payment:write")
        async def async_test_method(self, request, context):
            return "async_success"
        
        mock_self = Mock()
        mock_request = Mock()
        mock_context = Mock()
        mock_context.invocation_metadata.return_value = [
            ("authorization", "Bearer test-token")
        ]
        
        with patch('jose.jwt.get_unverified_claims') as mock_claims:
            mock_claims.return_value = sample_token_claims
            
            result = await async_test_method(mock_self, mock_request, mock_context)
            
            assert result == "async_success"
            mock_context.abort.assert_not_called()


class TestTokenIntrospection:
    """Test cases for token introspection scenarios"""
    
    def test_token_with_realm_roles(self):
        """Test token with realm-level roles"""
        claims = {
            "realm_access": {
                "roles": ["payment:read", "user"]
            },
            "resource_access": {}
        }
        
        # Extract roles like the decorator does
        realm_roles = claims.get('realm_access', {}).get('roles', [])
        resource_access = claims.get('resource_access', {})
        client_roles = []
        for client, access in resource_access.items():
            client_roles.extend(access.get('roles', []))
        
        all_roles = realm_roles + client_roles
        
        assert "payment:read" in all_roles
        assert "user" in all_roles
        assert len(all_roles) == 2
    
    def test_token_with_client_roles(self):
        """Test token with client-specific roles"""
        claims = {
            "realm_access": {
                "roles": []
            },
            "resource_access": {
                "paymentservice": {
                    "roles": ["payment:write", "payment:admin"]
                },
                "other-client": {
                    "roles": ["other:role"]
                }
            }
        }
        
        realm_roles = claims.get('realm_access', {}).get('roles', [])
        resource_access = claims.get('resource_access', {})
        client_roles = []
        for client, access in resource_access.items():
            client_roles.extend(access.get('roles', []))
        
        all_roles = realm_roles + client_roles
        
        assert "payment:write" in all_roles
        assert "payment:admin" in all_roles
        assert "other:role" in all_roles
        assert len(all_roles) == 3