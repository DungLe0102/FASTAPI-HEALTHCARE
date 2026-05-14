# All models registered here so SQLAlchemy Base populates metadata.

from app.models.department     import Department, Room                            
from app.models.patient        import Patient, PatientBHYT, PatientConsent         
from app.models.doctor         import Doctor, DoctorSchedule                       
from app.models.appointment    import Appointment                                  
from app.models.medical_record import MedicalRecord, ClinicalService, RecordService  
from app.models.inventory      import Medication, Inventory, Prescription,PrescriptionItem  
from app.models.billing        import Billing, PaymentTransaction, DoctorPayout
from app.models.notification   import Notification, SupportRequest                
from app.models.account        import Account                                      
from app.models.audit          import AuditLog                                    
from app.models.order          import Order