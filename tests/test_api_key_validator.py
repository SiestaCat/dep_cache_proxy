import unittest
from infrastructure.api_key_validator import ApiKeyValidator


class TestApiKeyValidator(unittest.TestCase):
    def test_public_server_allows_all_requests(self):
        validator = ApiKeyValidator(is_public=True)
        assert validator.validate(None) is True
        assert validator.validate("") is True
        assert validator.validate("any_key") is True

    def test_no_api_keys_configured_allows_all_requests(self):
        validator = ApiKeyValidator(api_keys=[], is_public=False)
        assert validator.validate(None) is True
        assert validator.validate("") is True
        assert validator.validate("any_key") is True

    def test_api_keys_configured_validates_correctly(self):
        valid_keys = ["key1", "key2", "key3"]
        validator = ApiKeyValidator(api_keys=valid_keys, is_public=False)
        
        assert validator.validate("key1") is True
        assert validator.validate("key2") is True
        assert validator.validate("key3") is True
        
        assert validator.validate("invalid_key") is False
        assert validator.validate("") is False
        assert validator.validate(None) is False

    def test_timing_safe_comparison(self):
        validator = ApiKeyValidator(api_keys=["secret_key"], is_public=False)
        
        assert validator.validate("secret_key") is True
        
        assert validator.validate("secret_kez") is False
        assert validator.validate("secret_ke") is False
        assert validator.validate("secret_key_extra") is False

    def test_empty_api_key_list_with_is_public_false(self):
        validator = ApiKeyValidator(api_keys=None, is_public=False)
        assert validator.validate(None) is True
        assert validator.validate("any_key") is True

    def test_multiple_api_keys_validation(self):
        api_keys = ["test-key-1", "test-key-2", "test-key-3"]
        validator = ApiKeyValidator(api_keys=api_keys, is_public=False)
        
        for key in api_keys:
            assert validator.validate(key) is True
        
        assert validator.validate("test-key-4") is False
        assert validator.validate("test-key") is False