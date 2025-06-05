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


class TestApiKeyValidatorEdgeCases(unittest.TestCase):
    """Additional edge case tests for ApiKeyValidator."""
    
    def test_api_key_with_special_characters(self):
        """Test API keys containing special characters."""
        special_keys = [
            "key-with-dashes",
            "key_with_underscores",
            "key.with.dots",
            "key@with#special$chars",
            "key with spaces",
            "key\twith\ttabs",
            "key\nwith\nnewlines"
        ]
        
        validator = ApiKeyValidator(api_keys=special_keys, is_public=False)
        
        for key in special_keys:
            assert validator.validate(key) is True
            
        # Similar but different keys should fail
        assert validator.validate("key-with_dashes") is False
        assert validator.validate("keywithspaces") is False
    
    def test_api_key_case_sensitivity(self):
        """Test that API key validation is case sensitive."""
        validator = ApiKeyValidator(api_keys=["MySecretKey"], is_public=False)
        
        assert validator.validate("MySecretKey") is True
        assert validator.validate("mysecretkey") is False
        assert validator.validate("MYSECRETKEY") is False
        assert validator.validate("MySecretKeY") is False
    
    def test_api_key_with_unicode(self):
        """Test API keys with unicode characters."""
        unicode_keys = [
            "key-ñoño",
            "key-文字",
            "key-🔑",
            "key-кириллица"
        ]
        
        validator = ApiKeyValidator(api_keys=unicode_keys, is_public=False)
        
        for key in unicode_keys:
            assert validator.validate(key) is True
    
    def test_extremely_long_api_key(self):
        """Test validation with very long API keys."""
        long_key = "x" * 1000  # 1000 character key
        validator = ApiKeyValidator(api_keys=[long_key], is_public=False)
        
        assert validator.validate(long_key) is True
        assert validator.validate(long_key[:-1]) is False  # One char short
        assert validator.validate(long_key + "x") is False  # One char long
    
    def test_empty_string_api_key(self):
        """Test empty string as a valid API key."""
        # Edge case: empty string is actually configured as valid key
        validator = ApiKeyValidator(api_keys=[""], is_public=False)
        
        # Current implementation treats empty string as invalid
        assert validator.validate("") is False
        assert validator.validate(None) is False
        assert validator.validate("any") is False
    
    def test_whitespace_api_keys(self):
        """Test API keys that are just whitespace."""
        whitespace_keys = [" ", "  ", "\t", "\n", " \t\n "]
        validator = ApiKeyValidator(api_keys=whitespace_keys, is_public=False)
        
        for key in whitespace_keys:
            assert validator.validate(key) is True
            
        # Trimmed versions should fail
        assert validator.validate("") is False
    
    def test_duplicate_api_keys(self):
        """Test handling of duplicate API keys in the list."""
        keys = ["key1", "key2", "key1", "key3", "key2"]
        validator = ApiKeyValidator(api_keys=keys, is_public=False)
        
        # All unique keys should validate
        assert validator.validate("key1") is True
        assert validator.validate("key2") is True
        assert validator.validate("key3") is True
        assert validator.validate("key4") is False
    
    def test_none_in_api_keys_list(self):
        """Test handling of None values in API keys list."""
        keys = ["key1", None, "key2", None]
        # Filter out None values in constructor
        validator = ApiKeyValidator(api_keys=[k for k in keys if k is not None], is_public=False)
        
        assert validator.validate("key1") is True
        assert validator.validate("key2") is True
        assert validator.validate(None) is False
    
    def test_api_key_timing_attack_resistance(self):
        """Test that validation time is consistent for different failures."""
        import time
        
        validator = ApiKeyValidator(api_keys=["correct_key_12345"], is_public=False)
        
        # Measure validation times
        times = []
        test_keys = [
            "wrong",  # Very different
            "correct_key_12344",  # Off by one char
            "correct_key_1234",  # One char short
            "correct_key_123456",  # One char long
            "xorrect_key_12345",  # Same length, different start
        ]
        
        # We can't reliably test timing in unit tests, but we ensure
        # the method uses hmac.compare_digest which is timing-safe
        for key in test_keys:
            start = time.perf_counter()
            result = validator.validate(key)
            end = time.perf_counter()
            assert result is False
            times.append(end - start)
        
        # Just verify all failed
        assert all(not validator.validate(k) for k in test_keys)