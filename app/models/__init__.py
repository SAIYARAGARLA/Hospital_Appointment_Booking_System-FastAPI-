from datetime import datetime
from sqlalchemy import (Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

class User(TimestampMixin, Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    full_name: Mapped[str]=mapped_column(String(120), nullable=False)
    email: Mapped[str]=mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str]=mapped_column(String(10), nullable=False)
    password_hash: Mapped[str]=mapped_column(String(255), nullable=False)
    role: Mapped[str]=mapped_column(String(20), default='Patient', nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    refresh_tokens=relationship('RefreshToken', back_populates='user', cascade='all, delete-orphan')
    patient_appointments=relationship('Appointment', back_populates='patient', foreign_keys='Appointment.patient_id')

class RefreshToken(TimestampMixin, Base):
    __tablename__='refresh_tokens'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'), index=True)
    token_jti: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool]=mapped_column(Boolean, default=False, nullable=False)
    user=relationship('User', back_populates='refresh_tokens')

class Department(TimestampMixin, Base):
    __tablename__='departments'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    doctors=relationship('Doctor', back_populates='department')

class Doctor(TimestampMixin, Base):
    __tablename__='doctors'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'), unique=True, nullable=False)
    name: Mapped[str]=mapped_column(String(120), nullable=False)
    department_id: Mapped[int]=mapped_column(ForeignKey('departments.id'), nullable=False)
    specialization: Mapped[str]=mapped_column(String(120), nullable=False)
    qualification: Mapped[str]=mapped_column(String(120), nullable=False)
    experience_years: Mapped[int]=mapped_column(Integer, default=0)
    consultation_fee: Mapped[float]=mapped_column(Float, nullable=False)
    slot_duration_minutes: Mapped[int]=mapped_column(Integer, default=15)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)
    department=relationship('Department', back_populates='doctors')
    schedules=relationship('Schedule', back_populates='doctor', cascade='all, delete-orphan')
    leaves=relationship('DoctorLeave', back_populates='doctor', cascade='all, delete-orphan')
    appointments=relationship('Appointment', back_populates='doctor')

class Schedule(TimestampMixin, Base):
    __tablename__='schedules'
    id: Mapped[int]=mapped_column(primary_key=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey('doctors.id'), index=True)
    day_of_week: Mapped[str]=mapped_column(String(10), nullable=False)
    start_time: Mapped[object]=mapped_column(Time, nullable=False)
    end_time: Mapped[object]=mapped_column(Time, nullable=False)
    break_start: Mapped[object|None]=mapped_column(Time)
    break_end: Mapped[object|None]=mapped_column(Time)
    doctor=relationship('Doctor', back_populates='schedules')

class DoctorLeave(TimestampMixin, Base):
    __tablename__='doctor_leaves'
    id: Mapped[int]=mapped_column(primary_key=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey('doctors.id'), index=True)
    leave_date: Mapped[object]=mapped_column(Date, nullable=False)
    reason: Mapped[str|None]=mapped_column(String(255))
    doctor=relationship('Doctor', back_populates='leaves')

class Appointment(TimestampMixin, Base):
    __tablename__='appointments'
    __table_args__=(UniqueConstraint('doctor_id','appointment_date','slot_time', name='uq_doctor_date_slot'), UniqueConstraint('appointment_number', name='uq_appointment_number'))
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_number: Mapped[str]=mapped_column(String(30), unique=True, nullable=False)
    patient_id: Mapped[int]=mapped_column(ForeignKey('users.id'), index=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey('doctors.id'), index=True)
    appointment_date: Mapped[object]=mapped_column(Date, index=True)
    slot_time: Mapped[object]=mapped_column(Time)
    token_number: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str|None]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default='Booked', index=True)
    consultation_fee: Mapped[float]=mapped_column(Float)
    reschedule_count: Mapped[int]=mapped_column(Integer, default=0)
    reminder_sent: Mapped[bool]=mapped_column(Boolean, default=False)
    patient=relationship('User', back_populates='patient_appointments', foreign_keys=[patient_id])
    doctor=relationship('Doctor', back_populates='appointments')
    consultation=relationship('Consultation', back_populates='appointment', uselist=False, cascade='all, delete-orphan')
    files=relationship('UploadedFile', back_populates='appointment', cascade='all, delete-orphan')
    history=relationship('AppointmentHistory', back_populates='appointment', cascade='all, delete-orphan')
    review=relationship('Review', back_populates='appointment', uselist=False)

class AppointmentHistory(TimestampMixin, Base):
    __tablename__='appointment_history'
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_id: Mapped[int]=mapped_column(ForeignKey('appointments.id'), index=True)
    old_status: Mapped[str|None]=mapped_column(String(30))
    new_status: Mapped[str]=mapped_column(String(30))
    changed_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    changed_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
    appointment=relationship('Appointment', back_populates='history')

class Consultation(TimestampMixin, Base):
    __tablename__='consultations'
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_id: Mapped[int]=mapped_column(ForeignKey('appointments.id'), unique=True)
    symptoms: Mapped[str]=mapped_column(Text)
    diagnosis: Mapped[str]=mapped_column(Text)
    prescription: Mapped[str|None]=mapped_column(Text)
    advice: Mapped[str|None]=mapped_column(Text)
    follow_up_date: Mapped[object|None]=mapped_column(Date)
    appointment=relationship('Appointment', back_populates='consultation')

class UploadedFile(TimestampMixin, Base):
    __tablename__='uploaded_files'
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_id: Mapped[int]=mapped_column(ForeignKey('appointments.id'), index=True)
    uploaded_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    file_type: Mapped[str]=mapped_column(String(30))
    original_name: Mapped[str]=mapped_column(String(255))
    stored_name: Mapped[str]=mapped_column(String(255), unique=True)
    size_kb: Mapped[float]=mapped_column(Float)
    appointment=relationship('Appointment', back_populates='files')

class Review(TimestampMixin, Base):
    __tablename__='reviews'
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_id: Mapped[int]=mapped_column(ForeignKey('appointments.id'), unique=True)
    patient_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    doctor_id: Mapped[int]=mapped_column(ForeignKey('doctors.id'))
    rating: Mapped[int]=mapped_column(Integer)
    feedback: Mapped[str|None]=mapped_column(Text)
    appointment=relationship('Appointment', back_populates='review')
