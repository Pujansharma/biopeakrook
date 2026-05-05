import logging
from accounts.utils.auth import get_user_model

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.utils.db import get_password_reset_token_for_user

User = get_user_model()

logger = logging.getLogger("accounts.tests")


class AccountTests(APITestCase):
    def setUp(self):
        self.user_data = {
            "email": "test@example.com",
            "password": "securepassword123",
        }

        self.user = User.objects.create_user(**self.user_data)
        logger.info(f"Created test user: {self.user.email}")

        # Get access token for authenticated requests
        login_url = reverse("accounts:login")
        login_response = self.client.post(login_url, self.user_data, format="json")
        data = login_response.data.get("data")
        self.access_token = data["access"]
        logger.info(f"Obtained access token for user: {self.user.email}")

    def _get_auth_header(self):
        """Helper method to get Bearer authentication header"""
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}

    def test_login_view(self):
        """
        Ensure login endpoint returns valid tokens for valid credentials.
        """
        url = reverse("accounts:login")
        response = self.client.post(url, self.user_data, format="json")
        logger.info(f"Login response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get("data")
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["email"], self.user_data["email"])
        logger.info("Login test passed.")

    def test_login_view_invalid_credentials(self):
        """
        Ensure login fails with invalid credentials.
        """
        url = reverse("accounts:login")
        invalid_data = {"email": "test@example.com", "password": "wrongpassword"}
        response = self.client.post(url, invalid_data, format="json")
        logger.info(f"Login with invalid credentials response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)
        logger.info("Invalid login test passed.")

    def test_token_refresh_view(self):
        """
        Ensure token refresh endpoint returns new access token.
        """
        # First get the refresh token
        login_url = reverse("accounts:login")
        login_response = self.client.post(login_url, self.user_data, format="json")
        login_data = login_response.data.get("data")
        refresh_token = login_data["refresh"]
        old_access_token = login_data["access"]
        logger.info(f"Old access token: {old_access_token}")

        # Now try to refresh
        url = reverse("accounts:refresh")
        data = {"refresh": refresh_token}
        response = self.client.post(url, data, format="json", **self._get_auth_header())
        logger.info(f"Token refresh response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.data.get("data")
        self.assertIn("access", response_data)
        new_access_token = response_data["access"]
        self.assertNotEqual(old_access_token, new_access_token)
        logger.info("Token refresh test passed.")

    def test_password_change_view(self):
        """
        Ensure password can be changed when authenticated.
        """
        url = reverse("accounts:change_password")
        data = {
            "password": self.user_data["password"],
            "password1": "newsecurepassword123",
            "password2": "newsecurepassword123",
        }
        response = self.client.post(url, data, format="json", **self._get_auth_header())
        logger.info(f"Password change response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Password changed successfully.")
        logger.info("Password change test passed.")

    def test_password_change_view_invalid_old_password(self):
        """
        Ensure password change fails with invalid old password.
        """
        url = reverse("accounts:change_password")
        data = {
            "old_password": "wrongoldpassword",
            "new_password": "newsecurepassword123",
        }
        response = self.client.post(url, data, format="json", **self._get_auth_header())
        logger.info(
            f"Password change with invalid old password response: {response.data}"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        logger.info("Invalid old password change test passed.")

    def test_password_reset_request(self):
        """
        Ensure password reset request can be initiated.
        """
        url = reverse("accounts:forgot_password")
        data = {"email": self.user_data["email"]}
        response = self.client.post(url, data, format="json")
        logger.info(f"Password reset request response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["detail"],
            "Request received, you shall receive a link shortly.",
        )
        logger.info("Password reset request test passed.")

    def test_password_reset_token_check(self):
        """
        Ensure password reset token can be validated.
        """
        # Generate token for user
        uid, token = get_password_reset_token_for_user(user=self.user)
        logger.info(f"Generated password reset token: {token} for uid: {uid}")

        # Check token for user
        url = reverse("accounts:check_password_token")
        data = {
            "uid": uid,
            "token": token,
        }
        response = self.client.post(url, data, format="json")
        logger.info(f"Password reset token check response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Token is valid.")
        logger.info("Password reset token check test passed.")

    def test_password_reset(self):
        """
        Ensure password can be reset using valid token.
        """
        # Generate token for user
        uid, token = get_password_reset_token_for_user(user=self.user)
        url = reverse("accounts:reset_password")
        data = {
            "uid": uid,
            "token": token,
            "password1": "newsecurepassword123",
            "password2": "newsecurepassword123",
        }
        response = self.client.post(url, data, format="json")
        logger.info(f"Password reset response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Password reset successful.")
        logger.info("Password reset test passed.")

    def test_password_reset_invalid_token(self):
        """
        Ensure password reset fails with invalid token.
        """
        url = reverse("accounts:reset_password")
        data = {
            "token": "invalid-token",
            "uidb64": "invalid-id",
            "password1": "newsecurepassword123",
            "password2": "newsecurepassword123",
        }
        response = self.client.post(url, data, format="json")
        logger.info(f"Password reset with invalid token response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        logger.info("Invalid password reset token test passed.")

    def test_user_profile_view(self):
        """
        Ensure authenticated user can view their profile.
        """
        url = reverse("users:profile")
        response = self.client.get(url, **self._get_auth_header())
        data = response.data.get("data")
        logger.info(f"User profile response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data["email"], self.user.email)
        logger.info("User profile view test passed.")

    def test_user_profile_unauthenticated(self):
        """
        Ensure unauthenticated user cannot view user profile.
        """
        url = reverse("users:profile")
        response = self.client.get(url)
        logger.info(f"Unauthenticated user profile response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        logger.info("Unauthenticated user profile test passed.")
