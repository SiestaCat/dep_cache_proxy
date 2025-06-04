import hmac
from typing import List, Optional


class ApiKeyValidator:
    def __init__(self, api_keys: Optional[List[str]] = None, is_public: bool = False):
        self.api_keys = api_keys or []
        self.is_public = is_public

    def validate(self, api_key: Optional[str]) -> bool:
        if self.is_public:
            return True
        
        if not self.api_keys:
            return True
        
        if not api_key:
            return False
        
        for valid_key in self.api_keys:
            if self._timing_safe_compare(api_key, valid_key):
                return True
        
        return False

    def _timing_safe_compare(self, a: str, b: str) -> bool:
        return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))