import os
import httpx
from typing import Dict, Any, List, Optional
from azure.identity import DefaultAzureCredential
import logging

logger = logging.getLogger(__name__)

class FabricError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code}] {message}")

class FabricClient:
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or os.environ.get("FABRIC_ENDPOINT", "http://localhost:8000")
        self.credential = DefaultAzureCredential()
        # Ensure endpoint doesn't end with slash
        if self.endpoint.endswith("/"):
            self.endpoint = self.endpoint[:-1]
            
    def _get_token(self) -> str:
        # MVP: we get a token for the Azure Management API or a generic scope
        # since we are using DefaultAzureCredential locally to hit our own container app.
        try:
            token = self.credential.get_token("https://management.azure.com/.default")
            return token.token
        except Exception as e:
            logger.warning(f"Failed to get Entra ID token: {e}")
            return "dummy-token-fallback" # Only if identity fails or we mock locally
            
    def _request(self, method: str, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.endpoint}{path}"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.request(method, url, headers=headers, json=json_data)
                
            if response.status_code == 404:
                raise FabricError("FABRIC_NOT_FOUND", "Resource not found")
            elif response.status_code == 401:
                raise FabricError("FABRIC_AUTH_ERROR", "Unauthorized")
                
            response.raise_for_status()
            return response.json()
            
        except httpx.TimeoutException:
            raise FabricError("FABRIC_TIMEOUT", "Request to Fabric Node timed out")
        except httpx.NetworkError:
            raise FabricError("FABRIC_NETWORK_ERROR", "Network error connecting to Fabric Node")
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                if "detail" in error_data and isinstance(error_data["detail"], dict) and "error_code" in error_data["detail"]:
                    raise FabricError(error_data["detail"]["error_code"], error_data["detail"].get("message", "Unknown error"))
            except ValueError:
                pass
            raise FabricError("FABRIC_UNAVAILABLE", f"HTTP Error: {e.response.status_code}")
            
    def health(self) -> Dict[str, Any]:
        # Health endpoint does not require auth normally, but we use _request which adds it
        url = f"{self.endpoint}/health"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception:
            raise FabricError("FABRIC_NETWORK_ERROR", "Health check failed")
            
    def identity(self) -> Dict[str, Any]:
        url = f"{self.endpoint}/identity"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception:
            raise FabricError("FABRIC_NETWORK_ERROR", "Identity check failed")
            
    def list_resources(self) -> List[Dict[str, Any]]:
        res = self._request("GET", "/resources")
        return res.get("resources", [])
        
    def get_resource(self, resource_id: str) -> Dict[str, Any]:
        res = self._request("GET", f"/resources/{resource_id}")
        return res.get("resource", {})
        
    def register_resource(self, provider: str, external_id: str, name: str, r_type: str, source_revision: str, observed_by: str) -> Dict[str, Any]:
        payload = {
            "provider": provider,
            "external_id": external_id,
            "name": name,
            "type": r_type,
            "source_revision": source_revision,
            "observed_by": observed_by
        }
        res = self._request("POST", "/resources/register", json_data=payload)
        return res.get("resource", {})
        
    def get_provenance(self, resource_id: str) -> List[Dict[str, Any]]:
        res = self._request("GET", f"/resources/{resource_id}/provenance")
        return res.get("provenance", [])
