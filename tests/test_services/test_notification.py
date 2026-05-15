from tests.base import BaseTestCase
from app.services import notification_service, patient_service
from app.models.account import Account
from app.schemas.notification import NotificationCreate, SupportRequestCreate
from app.schemas.patient import PatientCreate
from unittest.mock import patch
from datetime import date
import uuid

class TestNotificationService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Setup Patient
        self.patient_id = uuid.uuid4()
        self.db.add(Account(account_id=self.patient_id, email="p@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="A", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090123456", address="H"
        ), patient_id=self.patient_id)

    @patch("app.services.notification_service.settings")
    def test_create_notification_success(self, mock_settings):
        mock_settings.emails_enabled = False
        payload = NotificationCreate(
            recipient_id=self.patient_id,
            recipient_type="PATIENT",
            title="Test Title",
            content="Test Content",
            notification_type="SYSTEM_ALERT"
        )
        notif = notification_service.create_notification(self.db, payload)
        self.assertEqual(notif.title, "Test Title")
        self.assertEqual(notif.status, "PENDING")

    @patch("app.services.notification_service.settings")
    def test_support_request_lifecycle(self, mock_settings):
        mock_settings.emails_enabled = False
        req = notification_service.create_support_request(self.db, SupportRequestCreate(
            patient_id=self.patient_id,
            request_type="TECHNICAL",
            title="Problem",
            content="I cannot login",
            priority="HIGH"
        ))
        self.assertEqual(req.status, "OPEN")
        
        # Check auto-notification
        notifs = notification_service.list_notifications(self.db, recipient_id=self.patient_id)
        self.assertGreater(len(notifs), 0)
        self.assertIn("đã được tiếp nhận", notifs[0].title)
