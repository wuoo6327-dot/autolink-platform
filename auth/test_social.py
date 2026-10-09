import unittest
from unittest.mock import Mock, patch

try:
    import social
except ModuleNotFoundError:
    social = None


def response(data):
    result = Mock()
    result.json.return_value = data
    return result


@unittest.skipIf(social is None, "Optional social OAuth draft dependencies are not installed; provider is not deployed.")
class ProviderVerificationTests(unittest.TestCase):
    def test_facebook_requires_matching_app_and_user(self):
        with patch("social.credentials", return_value=("app-123", "secret")), \
             patch("social.requests.get", side_effect=[
                 response({"access_token": "token"}),
                 response({"data": {"is_valid": True, "app_id": "app-123", "user_id": "person-1"}}),
                 response({"id": "person-1", "email": "person@example.com", "name": "Person"}),
             ]):
            identity = social.exchange("facebook", "code", "nonce")
        self.assertEqual(identity["subject"], "person-1")
        with patch("social.credentials", return_value=("app-123", "secret")), \
             patch("social.requests.get", side_effect=[
                 response({"access_token": "token"}),
                 response({"data": {"is_valid": True, "app_id": "another-app", "user_id": "person-1"}}),
             ]):
            with self.assertRaises(social.ProviderError):
                social.exchange("facebook", "code", "nonce")

    def test_instagram_requires_professional_account(self):
        with patch("social.credentials", return_value=("app-123", "secret")), \
             patch("social.requests.post", return_value=response({"user_id": "ig-1", "access_token": "token"})), \
             patch("social.requests.get", return_value=response({"user_id": "ig-1", "username": "motorco", "account_type": "BUSINESS"})):
            self.assertEqual(social.exchange("instagram", "code", "nonce")["subject"], "ig-1")
        with patch("social.credentials", return_value=("app-123", "secret")), \
             patch("social.requests.post", return_value=response({"user_id": "ig-1", "access_token": "token"})), \
             patch("social.requests.get", return_value=response({"user_id": "ig-1", "account_type": "PERSONAL"})):
            with self.assertRaises(social.ProviderError):
                social.exchange("instagram", "code", "nonce")

    def test_linkedin_rejects_invalid_signature_or_nonce(self):
        with patch("social.credentials", return_value=("app-123", "secret")), \
             patch("social.requests.post", return_value=response({"id_token": "signed-token"})), \
             patch("social.jwt.PyJWKClient") as key_client, \
             patch("social.jwt.decode", return_value={"sub": "li-1", "name": "Person", "nonce": "wrong"}):
            key_client.return_value.get_signing_key_from_jwt.return_value.key = "public-key"
            with self.assertRaises(social.ProviderError):
                social.exchange("linkedin", "code", "expected")


if __name__ == "__main__":
    unittest.main()
