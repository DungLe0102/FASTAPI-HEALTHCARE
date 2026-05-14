# Healthcare System Database ERD

Here is the Entity Relationship Diagram for the current database schema based on the SQLAlchemy models defined in the `app/models` directory.

```mermaid
erDiagram
    ACCOUNT {
        UUID account_id PK
        string email
        string role
        boolean is_active
    }
    PATIENT {
        UUID patient_id PK
        string full_name
        string phone
        date date_of_birth
    }
    PATIENT_BHYT {
        UUID bhyt_id PK
        UUID patient_id FK
        string bhyt_code
    }
    PATIENT_CONSENT {
        UUID consent_id PK
        UUID patient_id FK
        string consent_type
    }
    DEPARTMENT {
        UUID department_id PK
        string name
        boolean is_active
    }
    ROOM {
        UUID room_id PK
        UUID department_id FK
        string room_number
        boolean is_active
    }
    DOCTOR {
        UUID doctor_id PK
        UUID department_id FK
        string full_name
        string specialization
    }
    DOCTOR_SCHEDULE {
        UUID schedule_id PK
        UUID doctor_id FK
        UUID room_id FK
        date work_date
    }
    APPOINTMENT {
        UUID appointment_id PK
        UUID patient_id FK
        UUID doctor_id FK
        UUID schedule_id FK
        UUID applied_bhyt_id FK
        string status
    }
    MEDICAL_RECORD {
        UUID record_id PK
        UUID appointment_id FK
        string diagnosis
    }
    CLINICAL_SERVICE {
        UUID service_id PK
        string name
        numeric price
        boolean is_active
    }
    RECORD_SERVICE {
        UUID record_id FK
        UUID service_id FK
        int quantity
    }
    PRESCRIPTION {
        UUID prescription_id PK
        UUID record_id FK
        UUID doctor_id FK
        string instructions
    }
    MEDICATION {
        UUID medication_id PK
        string name
        numeric price
        boolean is_active
    }
    PRESCRIPTION_ITEM {
        UUID prescription_id FK
        UUID medication_id FK
        int quantity
    }
    INVENTORY {
        UUID batch_id PK
        UUID medication_id FK
        int stock_quantity
        date expiry_date
    }
    BILLING {
        UUID billing_id PK
        UUID appointment_id FK
        numeric total_amount
        string payment_status
    }
    PAYMENT_TRANSACTION {
        UUID transaction_id PK
        UUID billing_id FK
        numeric amount
        string method
    }
    DOCTOR_PAYOUT {
        UUID payout_id PK
        UUID doctor_id FK
        numeric amount
        string period
    }
    ORDER {
        UUID order_id PK
        UUID patient_id FK
        numeric total_amount
    }
    NOTIFICATION {
        UUID notification_id PK
        UUID patient_id FK
        string title
        string type
    }
    SUPPORT_REQUEST {
        UUID request_id PK
        string user_email
        string issue_description
    }
    AUDIT_LOG {
        UUID log_id PK
        string action
        string entity_type
    }

    PATIENT ||--o{ PATIENT_BHYT : "has"
    PATIENT ||--o{ PATIENT_CONSENT : "has"
    PATIENT ||--o{ APPOINTMENT : "books"
    PATIENT ||--o{ ORDER : "places"
    PATIENT ||--o{ NOTIFICATION : "receives"
    
    DEPARTMENT ||--o{ ROOM : "contains"
    DEPARTMENT ||--o{ DOCTOR : "employs"
    
    DOCTOR ||--o{ DOCTOR_SCHEDULE : "has"
    DOCTOR ||--o{ APPOINTMENT : "assigned to"
    DOCTOR ||--o{ PRESCRIPTION : "writes"
    DOCTOR ||--o{ DOCTOR_PAYOUT : "receives"
    
    ROOM ||--o{ DOCTOR_SCHEDULE : "hosts"
    
    DOCTOR_SCHEDULE ||--o{ APPOINTMENT : "scheduled in"
    PATIENT_BHYT |o--o{ APPOINTMENT : "applied to"
    
    APPOINTMENT ||--o| MEDICAL_RECORD : "generates"
    APPOINTMENT ||--o| BILLING : "incurred"
    
    MEDICAL_RECORD ||--o{ RECORD_SERVICE : "includes"
    CLINICAL_SERVICE ||--o{ RECORD_SERVICE : "used in"
    MEDICAL_RECORD ||--o{ PRESCRIPTION : "has"
    
    PRESCRIPTION ||--o{ PRESCRIPTION_ITEM : "contains"
    MEDICATION ||--o{ PRESCRIPTION_ITEM : "prescribed as"
    MEDICATION ||--o{ INVENTORY : "stocked as"
    
    BILLING ||--o{ PAYMENT_TRANSACTION : "paid via"
```
