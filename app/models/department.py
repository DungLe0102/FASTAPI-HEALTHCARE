import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Department(Base):
    __tablename__ = "department"

    department_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_code = Column(String(20), unique=True, nullable=False)
    department_name = Column(String(100), nullable=False)

    # Relationships
    rooms = relationship("Room", back_populates="department", lazy="select")
    doctors = relationship("Doctor", back_populates="department", lazy="select")


class Room(Base):
    __tablename__ = "room"

    room_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("department.department_id", ondelete="RESTRICT"),
        nullable=False,
    )
    room_number = Column(String(20), nullable=False)
    room_type = Column(String(50), default="CONSULTATION")
    is_active = Column(Boolean, default=True)

    # Relationships
    department = relationship("Department", back_populates="rooms")
    schedules = relationship("DoctorSchedule", back_populates="room", lazy="select")