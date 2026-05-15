from tests.base import BaseTestCase
from app.services import inventory_service, order_service, patient_service
from app.models.account import Account
from app.models.patient import Patient
from app.schemas.inventory import MedicationCreate, InventoryCreate
from app.schemas.order import OrderCreate, OrderItemSchema
from app.schemas.patient import PatientCreate
from fastapi import HTTPException
from datetime import date, timedelta
import uuid

class TestInventoryOrderService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Setup Patient
        self.patient_id = uuid.uuid4()
        self.db.add(Account(account_id=self.patient_id, email="p@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="A", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090123456", address="H"
        ), patient_id=self.patient_id)

        # Setup Medication
        self.med = inventory_service.create_medication(self.db, MedicationCreate(
            med_code="PARA500", med_name="Paracetamol 500mg", unit="Tablet", price=1000
        ))

        # Add Inventory
        inventory_service.add_inventory_batch(self.db, InventoryCreate(
            medication_id=self.med.medication_id,
            batch_number="B123",
            quantity=100,
            expiration_date=date.today() + timedelta(days=365)
        ))

    def test_stock_management(self):
        total = inventory_service.get_stock_total(self.db, self.med.medication_id)
        self.assertEqual(total, 100)
        
        # Deduct stock
        inventory_service._deduct_stock(self.db, self.med.medication_id, 30)
        total_after = inventory_service.get_stock_total(self.db, self.med.medication_id)
        self.assertEqual(total_after, 70)

    def test_create_pharmacy_order_success(self):
        payload = OrderCreate(
            patient_id=self.patient_id,
            order_type="PHARMACY",
            items=[OrderItemSchema(item_id=self.med.medication_id, quantity=10)]
        )
        order_resp = order_service.create_order(self.db, payload)
        self.assertEqual(float(order_resp.total_amount), 10000.0)
        self.assertEqual(order_resp.status, "PENDING")

    def test_insufficient_stock_fails(self):
        payload = OrderCreate(
            patient_id=self.patient_id,
            order_type="PHARMACY",
            items=[OrderItemSchema(item_id=self.med.medication_id, quantity=500)]
        )
        with self.assertRaises(HTTPException) as cm:
            order_service.create_order(self.db, payload)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Not enough stock", cm.exception.detail)
