import unittest
from datetime import timedelta
from app.security import get_password_hash, verify_password, create_access_token

class TestSecurity(unittest.TestCase):
    def test_password_hashing(self):
        password = "secret_password"
        hashed = get_password_hash(password)
        
        self.assertNotEqual(password, hashed)
        
        # Verify
        is_valid, _ = verify_password(password, hashed)
        self.assertTrue(is_valid)
        
        # Wrong password
        is_valid_wrong, _ = verify_password("wrong", hashed)
        self.assertFalse(is_valid_wrong)

    def test_create_access_token(self):
        data = "test@example.com"
        token = create_access_token(data, expires_delta=timedelta(minutes=15))
        
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)
