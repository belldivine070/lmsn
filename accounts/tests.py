from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Role

User = get_user_model()


class AccountsTests(TestCase):

    def setUp(self):
        # Create roles
        self.customer_role = Role.objects.create(name="Customer", slug="customer")
        self.staff_role = Role.objects.create(name="Staff", slug="staff")

        # Create a staff user
        self.staff_user = User.objects.create_user(
            username="adminuser",
            email="admin@test.com",
            password="testpass123",
            role=self.staff_role,
            is_staff=True
        )

        # Create a customer user
        self.customer_user = User.objects.create_user(
            username="customer1",
            email="customer@test.com",
            password="testpass123",
            role=self.customer_role
        )

    def test_signup_page_loads(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)

    def test_user_signup(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "newuser",
            "email": "newuser@test.com",
            "first_name": "New",
            "last_name": "User",
            "mobile": "1234567890",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!"
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_login(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "adminuser",
            "password": "testpass123"
        })

        self.assertEqual(response.status_code, 302)

    def test_account_list_requires_login(self):
        response = self.client.get(reverse("accounts:account_list"))
        self.assertNotEqual(response.status_code, 200)

    def test_staff_can_view_account_list(self):
        self.client.login(username="adminuser", password="testpass123")
        response = self.client.get(reverse("accounts:account_list"))
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_view_account_list(self):
        self.client.login(username="customer1", password="testpass123")
        response = self.client.get(reverse("accounts:account_list"))
        self.assertNotEqual(response.status_code, 200)