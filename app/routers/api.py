from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.database import get_db
from app.models import *
from app.schemas import *
from app.dependencies import get_current_user, require_roles
from app.auth.security import hash_password, verify_password, create_token, decode_token
from app.config import settings
from app.services.notifications import send_email
from app.websockets.manager import manager

router=APIRouter()
UPLOAD_DIR=Path('uploads'); UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXT={'.pdf','.jpg','.jpeg','.png'}; MAX_FILE=5*1024*1024

def safe_appointment(a):
    return {
        "id": a.id,
        "appointment_number": a.appointment_number,
        "patient_id": a.patient_id,
        "doctor_id": a.doctor_id,
        "appointment_date": a.appointment_date,
        "slot_time": a.slot_time,
        "token_number": a.token_number,
        "reason": a.reason,
        "status": a.status,
        "consultation_fee": a.consultation_fee,
        "reschedule_count": a.reschedule_count,
        "patient": UserOut.model_validate(a.patient).model_dump(),
        "doctor": {
            "id": a.doctor.id,
            "name": a.doctor.name,
            "specialization": a.doctor.specialization,
            "department_id": a.doctor.department_id,
        } if a.doctor else None,
    }

def role(user, *roles):
    if user.role not in roles: raise HTTPException(403,'Insufficient permissions')
def log_status(db,a,new_status,actor):
    old=a.status; a.status=new_status; db.add(AppointmentHistory(appointment_id=a.id,old_status=old,new_status=new_status,changed_by=actor.id))
def appointment_access(a,user):
    if user.role=='Admin': return
    if user.role=='Doctor' and a.doctor.user_id==user.id: return
    if user.role=='Patient' and a.patient_id==user.id: return
    raise HTTPException(403,'You cannot access this appointment')
def get_doctor_for_user(db,user):
    d=db.query(Doctor).filter(Doctor.user_id==user.id,Doctor.is_active.is_(True)).first()
    if not d: raise HTTPException(404,'Doctor profile not found or inactive')
    return d
def day_name(d): return d.strftime('%A')
def slot_is_valid(db, doctor, d, t):
    if d<=date.today() or d>date.today()+timedelta(days=30): raise HTTPException(400,'Appointments must be in the future and at most 30 days ahead')
    if db.query(DoctorLeave).filter_by(doctor_id=doctor.id,leave_date=d).first(): raise HTTPException(400,'Doctor is on leave on this date')
    schedules=db.query(Schedule).filter_by(doctor_id=doctor.id,day_of_week=day_name(d)).all()
    end=(datetime.combine(d,t)+timedelta(minutes=doctor.slot_duration_minutes)).time()
    for s in schedules:
        if t>=s.start_time and end<=s.end_time:
            if s.break_start and s.break_end and t<s.break_end and end>s.break_start: continue
            if datetime.combine(d,t)<=datetime.now(): continue
            return True
    raise HTTPException(400,'Requested time is outside schedule, in break time, or in the past')
def make_appointment(db,user,doctor,d,t,reason):
    slot_is_valid(db,doctor,d,t)
    if db.query(Appointment).filter_by(doctor_id=doctor.id,appointment_date=d,slot_time=t).filter(Appointment.status!='Cancelled').first(): raise HTTPException(409,'This slot is already booked')
    if db.query(Appointment).filter_by(patient_id=user.id,appointment_date=d).filter(Appointment.status.notin_(['Cancelled'])).filter(Appointment.slot_time==t).first(): raise HTTPException(409,'You already have an appointment at this date and time')
    if db.query(Appointment).filter_by(patient_id=user.id,doctor_id=doctor.id,appointment_date=d).filter(Appointment.status!='Cancelled').first(): raise HTTPException(409,'Only one appointment per doctor per day is allowed')
    token=(db.query(func.max(Appointment.token_number)).filter_by(doctor_id=doctor.id,appointment_date=d).scalar() or 0)+1
    number=f'APT-{d:%Y%m%d}-{uuid4().hex[:6].upper()}'
    a=Appointment(appointment_number=number,patient_id=user.id,doctor_id=doctor.id,appointment_date=d,slot_time=t,token_number=token,reason=reason,status='Booked',consultation_fee=doctor.consultation_fee)
    db.add(a); db.flush(); db.add(AppointmentHistory(appointment_id=a.id,old_status=None,new_status='Booked',changed_by=user.id)); db.commit(); db.refresh(a)
    return a

@router.post('/auth/register',status_code=201)
def register(data:RegisterIn, db:Session=Depends(get_db)):
    if db.query(User).filter(func.lower(User.email)==data.email.lower()).first(): raise HTTPException(409,'Email already registered')
    u=User(full_name=data.full_name,email=data.email.lower(),phone=data.phone,password_hash=hash_password(data.password),role='Patient'); db.add(u); db.commit(); db.refresh(u); return UserOut.model_validate(u)
@router.post('/auth/login')
def login(data:LoginIn, db:Session=Depends(get_db)):
    u=db.query(User).filter(func.lower(User.email)==data.email.lower()).first()
    if not u or not verify_password(data.password,u.password_hash): raise HTTPException(401,'Incorrect email or password')
    if not u.is_active: raise HTTPException(403,'Inactive users cannot log in')
    access,ap=create_token(u.id,u.role,'access',timedelta(minutes=settings.access_token_minutes)); refresh,rp=create_token(u.id,u.role,'refresh',timedelta(days=settings.refresh_token_days))
    db.add(RefreshToken(user_id=u.id,token_jti=rp['jti'],expires_at=datetime.fromtimestamp(rp['exp'], tz=timezone.utc).replace(tzinfo=None),revoked=False)); db.commit()
    return {'access_token':access,'refresh_token':refresh,'token_type':'bearer','expires_in_minutes':settings.access_token_minutes,'user':UserOut.model_validate(u)}
@router.post('/auth/refresh')
def refresh(data:RefreshIn,db:Session=Depends(get_db)):
    p=decode_token(data.refresh_token)
    if not p or p.get('type')!='refresh': raise HTTPException(401,'Invalid or expired refresh token')
    row=db.query(RefreshToken).filter_by(token_jti=p.get('jti'),revoked=False).first()
    if not row or row.expires_at<datetime.utcnow(): raise HTTPException(401,'Refresh token revoked or expired')
    u=db.get(User,row.user_id)
    if not u or not u.is_active: raise HTTPException(401,'User inactive')
    access,_=create_token(u.id,u.role,'access',timedelta(minutes=settings.access_token_minutes)); return {'access_token':access,'token_type':'bearer'}
@router.post('/auth/logout')
def logout(data:RefreshIn, user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    p=decode_token(data.refresh_token)
    if p and p.get('type')=='refresh':
        row=db.query(RefreshToken).filter_by(token_jti=p.get('jti'),user_id=user.id).first()
        if row: row.revoked=True; db.commit()
    return {'message':'Logged out; refresh token revoked'}
@router.get('/auth/me')
def me(user:User=Depends(get_current_user)): return UserOut.model_validate(user)
@router.post('/admin/users',status_code=201)
def create_staff(data:RegisterIn, role_name:str=Query(pattern='^(Admin|Doctor)$'), admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    if db.query(User).filter(func.lower(User.email)==data.email.lower()).first(): raise HTTPException(409,'Email already registered')
    u=User(full_name=data.full_name,email=data.email.lower(),phone=data.phone,password_hash=hash_password(data.password),role=role_name); db.add(u); db.commit(); db.refresh(u); return UserOut.model_validate(u)

@router.post('/departments',status_code=201)
def create_department(data:DepartmentIn,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    if db.query(Department).filter(func.lower(Department.name)==data.name.lower()).first(): raise HTTPException(409,'Department name already exists')
    x=Department(name=data.name,description=data.description); db.add(x); db.commit(); db.refresh(x); return x
@router.get('/departments')
def list_departments(skip:int=0,limit:int=20,db:Session=Depends(get_db)): return db.query(Department).offset(skip).limit(min(limit,100)).all()
@router.put('/departments/{department_id}')
def update_department(department_id:int,data:DepartmentIn,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    x=db.get(Department,department_id)
    if not x: raise HTTPException(404,'Department not found')
    if db.query(Department).filter(Department.id!=department_id,func.lower(Department.name)==data.name.lower()).first(): raise HTTPException(409,'Department name already exists')
    x.name=data.name; x.description=data.description; db.commit(); db.refresh(x); return x
@router.delete('/departments/{department_id}')
def delete_department(department_id:int,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    x=db.get(Department,department_id)
    if not x: raise HTTPException(404,'Department not found')
    if db.query(Doctor).filter_by(department_id=department_id,is_active=True).first(): raise HTTPException(409,'Department has active doctors')
    db.delete(x); db.commit(); return {'message':'Department deleted'}

@router.post('/doctors',status_code=201)
def create_doctor(data:DoctorIn,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    if data.slot_duration_minutes not in (10,15,20,30): raise HTTPException(422,'Slot duration must be 10, 15, 20, or 30')
    u=db.get(User,data.user_id); dep=db.get(Department,data.department_id)
    if not u or u.role!='Doctor': raise HTTPException(400,'user_id must belong to a Doctor account created by Admin')
    if not dep: raise HTTPException(404,'Department not found')
    if db.query(Doctor).filter_by(user_id=data.user_id).first(): raise HTTPException(409,'Doctor profile already exists')
    d=Doctor(**data.model_dump()); db.add(d); db.commit(); db.refresh(d); return d
@router.get('/doctors')
def list_doctors(department_id:int|None=None,specialization:str|None=None,name:str|None=None,skip:int=0,limit:int=20,db:Session=Depends(get_db)):
    q=db.query(Doctor).filter(Doctor.is_active.is_(True))
    if department_id: q=q.filter(Doctor.department_id==department_id)
    if specialization: q=q.filter(Doctor.specialization.ilike(f'%{specialization}%'))
    if name: q=q.filter(Doctor.name.ilike(f'%{name}%'))
    return q.offset(skip).limit(min(limit,100)).all()
@router.get('/doctors/{doctor_id}')
def get_doctor(doctor_id:int,db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d or not d.is_active: raise HTTPException(404,'Active doctor not found')
    return d
@router.put('/doctors/{doctor_id}')
def update_doctor(doctor_id:int,data:DoctorIn,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d: raise HTTPException(404,'Doctor not found')
    if data.slot_duration_minutes not in (10,15,20,30): raise HTTPException(422,'Invalid slot duration')
    if not data.is_active and db.query(Appointment).filter(Appointment.doctor_id==doctor_id,Appointment.appointment_date>=date.today(),Appointment.status.in_(['Booked','Checked-In','In Consultation'])).first(): raise HTTPException(409,'Doctor has upcoming appointments')
    for k,v in data.model_dump().items(): setattr(d,k,v)
    db.commit(); db.refresh(d); return d
@router.delete('/doctors/{doctor_id}')
def deactivate_doctor(doctor_id:int,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d: raise HTTPException(404,'Doctor not found')
    if db.query(Appointment).filter(Appointment.doctor_id==doctor_id,Appointment.appointment_date>=date.today(),Appointment.status.in_(['Booked','Checked-In','In Consultation'])).first(): raise HTTPException(409,'Doctor has upcoming appointments')
    d.is_active=False; db.commit(); return {'message':'Doctor deactivated'}

@router.post('/doctors/{doctor_id}/schedules',status_code=201)
def add_schedule(doctor_id:int,data:ScheduleIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d: raise HTTPException(404,'Doctor not found')
    if user.role!='Admin' and d.user_id!=user.id: raise HTTPException(403,'Doctors can manage only their own schedules')
    if data.day_of_week not in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']: raise HTTPException(422,'Invalid day_of_week')
    if data.end_time<=data.start_time: raise HTTPException(422,'End time must be after start time')
    if (data.break_start is None)!=(data.break_end is None): raise HTTPException(422,'Provide both break_start and break_end')
    if data.break_start and not(data.start_time<=data.break_start<data.break_end<=data.end_time): raise HTTPException(422,'Break must be inside working hours')
    for s in db.query(Schedule).filter_by(doctor_id=doctor_id,day_of_week=data.day_of_week):
        if data.start_time<s.end_time and data.end_time>s.start_time: raise HTTPException(409,'Schedule overlaps an existing schedule')
    x=Schedule(doctor_id=doctor_id,**data.model_dump()); db.add(x); db.commit(); db.refresh(x); return x
@router.get('/doctors/{doctor_id}/schedules')
def list_schedules(doctor_id:int,skip:int=0,limit:int=100,db:Session=Depends(get_db)): return db.query(Schedule).filter_by(doctor_id=doctor_id).offset(skip).limit(min(limit,100)).all()
@router.put('/schedules/{schedule_id}')
def update_schedule(schedule_id:int,data:ScheduleIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    s=db.get(Schedule,schedule_id)
    if not s: raise HTTPException(404,'Schedule not found')
    if user.role!='Admin' and s.doctor.user_id!=user.id: raise HTTPException(403,'Not your schedule')
    if data.end_time<=data.start_time or (data.break_start and not(data.start_time<=data.break_start<data.break_end<=data.end_time)): raise HTTPException(422,'Invalid schedule times')
    for other in db.query(Schedule).filter(Schedule.doctor_id==s.doctor_id,Schedule.day_of_week==data.day_of_week,Schedule.id!=s.id):
        if data.start_time<other.end_time and data.end_time>other.start_time: raise HTTPException(409,'Schedule overlaps an existing schedule')
    for k,v in data.model_dump().items(): setattr(s,k,v)
    db.commit(); db.refresh(s); return s
@router.delete('/schedules/{schedule_id}')
def delete_schedule(schedule_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    s=db.get(Schedule,schedule_id)
    if not s: raise HTTPException(404,'Schedule not found')
    if user.role!='Admin' and s.doctor.user_id!=user.id: raise HTTPException(403,'Not your schedule')
    db.delete(s); db.commit(); return {'message':'Schedule deleted'}
@router.post('/doctors/{doctor_id}/leaves',status_code=201)
def add_leave(doctor_id:int,data:LeaveIn,bg:BackgroundTasks,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d: raise HTTPException(404,'Doctor not found')
    if user.role!='Admin' and d.user_id!=user.id: raise HTTPException(403,'Not your doctor profile')
    if db.query(DoctorLeave).filter_by(doctor_id=doctor_id,leave_date=data.leave_date).first(): raise HTTPException(409,'Leave already exists')
    lv=DoctorLeave(doctor_id=doctor_id,**data.model_dump()); db.add(lv)
    appointments=db.query(Appointment).filter_by(doctor_id=doctor_id,appointment_date=data.leave_date).filter(Appointment.status=='Booked').all()
    for a in appointments:
        log_status(db,a,'Cancelled',user); bg.add_task(send_email,a.patient.email,'Appointment cancelled: doctor leave',f'Appointment {a.appointment_number} on {a.appointment_date} was cancelled because Dr. {d.name} is on leave.')
    db.commit(); return {'message':'Leave added','cancelled_appointments':len(appointments)}
@router.get('/doctors/{doctor_id}/leaves')
def list_leaves(doctor_id:int,skip:int=0,limit:int=100,db:Session=Depends(get_db)): return db.query(DoctorLeave).filter_by(doctor_id=doctor_id).offset(skip).limit(min(limit,100)).all()
@router.get('/doctors/{doctor_id}/available-slots')
def available_slots(doctor_id:int, date_value:date=Query(alias='date'),db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d or not d.is_active: raise HTTPException(404,'Active doctor not found')
    if date_value<date.today() or date_value>date.today()+timedelta(days=30): raise HTTPException(400,'Date must be today through 30 days ahead')
    if db.query(DoctorLeave).filter_by(doctor_id=doctor_id,leave_date=date_value).first(): return {'date':date_value,'slots':[],'reason':'Doctor on leave'}
    out=[]; now=datetime.now()
    for s in db.query(Schedule).filter_by(doctor_id=doctor_id,day_of_week=day_name(date_value)).order_by(Schedule.start_time):
        cur=datetime.combine(date_value,s.start_time); end=datetime.combine(date_value,s.end_time)
        while cur+timedelta(minutes=d.slot_duration_minutes)<=end:
            nxt=cur+timedelta(minutes=d.slot_duration_minutes)
            if s.break_start and s.break_end and cur.time()<s.break_end and nxt.time()>s.break_start: cur=nxt; continue
            t=cur.time()
            booked=db.query(Appointment).filter_by(doctor_id=doctor_id,appointment_date=date_value,slot_time=t).filter(Appointment.status!='Cancelled').first()
            if cur>now and not booked: out.append(t.strftime('%H:%M'))
            cur=nxt
    return {'date':date_value,'slots':out}

@router.post('/appointments',status_code=201)
def book_appointment(data:AppointmentIn,bg:BackgroundTasks,user:User=Depends(require_roles('Patient')),db:Session=Depends(get_db)):
    d=db.get(Doctor,data.doctor_id)
    if not d or not d.is_active: raise HTTPException(404,'Active doctor not found')
    try:
        # MySQL row lock on doctor record serializes bookings for that doctor.
        d=db.query(Doctor).filter_by(id=d.id).with_for_update().one()
        a=make_appointment(db,user,d,data.appointment_date,data.slot_time,data.reason)
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); raise HTTPException(409,'Could not book this slot; it may have just been taken') from e
    bg.add_task(send_email,user.email,'Appointment booked',f'Appointment {a.appointment_number}\nDoctor: {d.name}\nDate: {a.appointment_date}\nTime: {a.slot_time}\nToken: {a.token_number}')
    return safe_appointment(a)
@router.get('/appointments')
def list_appointments(status:str|None=None,doctor_id:int|None=None,date_from:date|None=None,date_to:date|None=None,appointment_number:str|None=None,skip:int=0,limit:int=20,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    q=db.query(Appointment)
    if user.role=='Patient': q=q.filter(Appointment.patient_id==user.id)
    elif user.role=='Doctor':
        d=get_doctor_for_user(db,user); q=q.filter(Appointment.doctor_id==d.id)
    if status: q=q.filter(Appointment.status==status)
    if doctor_id: q=q.filter(Appointment.doctor_id==doctor_id)
    if date_from: q=q.filter(Appointment.appointment_date>=date_from)
    if date_to: q=q.filter(Appointment.appointment_date<=date_to)
    if appointment_number: q=q.filter(Appointment.appointment_number.ilike(f'%{appointment_number}%'))
    appointments = q.order_by(
        Appointment.appointment_date,
        Appointment.slot_time
    ).offset(skip).limit(min(limit, 100)).all()

    return [safe_appointment(a) for a in appointments]
@router.get('/appointments/{appointment_id}')
def get_appointment(appointment_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a, user)
    return safe_appointment(a)
@router.put('/appointments/{appointment_id}/cancel')
def cancel_appointment(appointment_id:int,bg:BackgroundTasks,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if user.role!='Patient': raise HTTPException(403,'Only patients may cancel their own appointments')
    if a.status!='Booked': raise HTTPException(409,'Only Booked appointments can be cancelled')
    if datetime.combine(a.appointment_date,a.slot_time)-datetime.now()<timedelta(hours=2): raise HTTPException(400,'Cancellation must be at least 2 hours before slot')
    log_status(db,a,'Cancelled',user); db.commit(); bg.add_task(send_email,a.patient.email,'Appointment cancelled',f'Appointment {a.appointment_number} was cancelled.');
    return safe_appointment(a)
@router.put('/appointments/{appointment_id}/reschedule')
def reschedule(appointment_id:int,data:AppointmentIn,bg:BackgroundTasks,user:User=Depends(require_roles('Patient')),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if a.status!='Booked': raise HTTPException(409,'Only Booked appointments can be rescheduled')
    if a.reschedule_count>=2: raise HTTPException(409,'Maximum reschedule count reached')
    if datetime.combine(a.appointment_date,a.slot_time)-datetime.now()<timedelta(hours=2): raise HTTPException(400,'Reschedule must be at least 2 hours before slot')
    d=db.get(Doctor,data.doctor_id)
    if not d or not d.is_active: raise HTTPException(404,'Active doctor not found')
    # Validate new slot before releasing the old one.
    slot_is_valid(db,d,data.appointment_date,data.slot_time)
    if db.query(Appointment).filter(Appointment.doctor_id==d.id,Appointment.appointment_date==data.appointment_date,Appointment.slot_time==data.slot_time,Appointment.id!=a.id,Appointment.status!='Cancelled').first(): raise HTTPException(409,'Target slot already booked')
    old=a.status; a.status='Cancelled'; db.add(AppointmentHistory(appointment_id=a.id,old_status=old,new_status='Cancelled',changed_by=user.id))
    new=make_appointment(db,user,d,data.appointment_date,data.slot_time,data.reason); new.reschedule_count=a.reschedule_count+1; db.commit(); db.refresh(new)
    bg.add_task(send_email,user.email,'Appointment rescheduled',f'Old appointment {a.appointment_number} cancelled. New appointment {new.appointment_number} on {new.appointment_date} at {new.slot_time}.');
    return {
    "cancelled_appointment": safe_appointment(a),
    "new_appointment": safe_appointment(new),
    }
def check_in(appointment_id:int,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    if a.status!='Booked': raise HTTPException(409,'Only Booked appointments can be checked in')
    now=datetime.now(); slot=datetime.combine(a.appointment_date,a.slot_time)
    if date.today()!=a.appointment_date or now<slot-timedelta(minutes=30): raise HTTPException(400,'Check-in is allowed on appointment date from 30 minutes before slot')
    log_status(db,a,'Checked-In',admin); db.commit()
    import asyncio
    try: asyncio.run(manager.queue_broadcast(a.doctor_id,{'event':'queue_updated','doctor_id':a.doctor_id}))
    except RuntimeError: pass
    return safe_appointment(a)

@router.post('/appointments/{appointment_id}/consultation',status_code=201)
def save_consultation(appointment_id:int,data:ConsultationIn,bg:BackgroundTasks,user:User=Depends(require_roles('Doctor')),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if a.status!='In Consultation': raise HTTPException(409,'Consultation can be saved only while In Consultation')
    if a.consultation: raise HTTPException(409,'Consultation already exists')
    c=Consultation(appointment_id=a.id,**data.model_dump()); db.add(c); log_status(db,a,'Completed',user); db.commit(); db.refresh(c)
    bg.add_task(send_email,a.patient.email,'Consultation completed',f'Consultation for {a.appointment_number} is completed. Follow-up: {data.follow_up_date or "Not scheduled"}.')
    return c
@router.get('/appointments/{appointment_id}/consultation')
def get_consultation(appointment_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if not a.consultation: raise HTTPException(404,'Consultation not found')
    return a.consultation
@router.post('/appointments/{appointment_id}/files',status_code=201)
def upload_file(appointment_id:int,file_type:str=Query(pattern='^(Lab Report|Prescription|Scan)$'),file:UploadFile=File(...),user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if user.role=='Patient' and file_type!='Lab Report': raise HTTPException(403,'Patients may upload Lab Reports only')
    if user.role=='Doctor' and file_type=='Lab Report': raise HTTPException(403,'Doctors may upload prescriptions or scans')
    ext=Path(file.filename or '').suffix.lower()
    if ext not in ALLOWED_EXT: raise HTTPException(415,'Only PDF, JPG, and PNG files are allowed')
    content=file.file.read(MAX_FILE+1)
    if len(content)>MAX_FILE: raise HTTPException(413,'File exceeds 5 MB')
    stored=f'{uuid4().hex}{ext}'; (UPLOAD_DIR/stored).write_bytes(content)
    x=UploadedFile(appointment_id=a.id,uploaded_by=user.id,file_type=file_type,original_name=file.filename or 'upload',stored_name=stored,size_kb=round(len(content)/1024,2)); db.add(x); db.commit(); db.refresh(x); return x
@router.get('/appointments/{appointment_id}/files')
def list_files(appointment_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user); return a.files
@router.get('/files/{file_id}/download')
def download_file(file_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    f=db.get(UploadedFile,file_id)
    if not f: raise HTTPException(404,'File not found')
    appointment_access(f.appointment,user); path=UPLOAD_DIR/f.stored_name
    if not path.exists(): raise HTTPException(404,'Stored file not found')
    return FileResponse(path,filename=f.original_name)
@router.get('/patients/me/history')
def patient_history(user:User=Depends(require_roles('Patient')),db:Session=Depends(get_db)):
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == user.id,
            Appointment.appointment_date < date.today()
       )
       .order_by(Appointment.appointment_date.desc())
       .all()
   )
    return [safe_appointment(a) for a in appointments]  
def review(appointment_id:int,data:ReviewIn,user:User=Depends(require_roles('Patient')),db:Session=Depends(get_db)):
    a=db.get(Appointment,appointment_id)
    if not a: raise HTTPException(404,'Appointment not found')
    appointment_access(a,user)
    if a.status!='Completed': raise HTTPException(400,'Review is available only after a completed appointment')
    if a.review: raise HTTPException(409,'One review per appointment is allowed')
    r=Review(appointment_id=a.id,patient_id=user.id,doctor_id=a.doctor_id,**data.model_dump()); db.add(r); db.commit(); db.refresh(r); return r

@router.put('/doctors/me/call-next')
def call_next(user:User=Depends(require_roles('Doctor')),db:Session=Depends(get_db)):
    d=get_doctor_for_user(db,user)
    if db.query(Appointment).filter_by(doctor_id=d.id,appointment_date=date.today(),status='In Consultation').first(): raise HTTPException(409,'Complete the current consultation before calling next')
    a=db.query(Appointment).filter_by(doctor_id=d.id,appointment_date=date.today(),status='Checked-In').order_by(Appointment.token_number).first()
    if not a: raise HTTPException(404,'No checked-in patients waiting')
    log_status(db,a,'In Consultation',user); db.commit()
    import asyncio
    try: asyncio.run(manager.queue_broadcast(d.id,{'event':'queue_updated','current_token':a.token_number,'appointment_id':a.id}))
    except RuntimeError: pass
    return {
    "message": "Next patient called",
    "token_number": a.token_number,
    "appointment": safe_appointment(a),
    }
@router.websocket('/ws/queue/{doctor_id}')
async def ws_queue(websocket:WebSocket,doctor_id:int,token:str):
    payload=decode_token(token)
    if not payload or payload.get('type')!='access': await websocket.close(code=1008); return
    await manager.connect_queue(doctor_id,websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: await manager.disconnect(websocket)
    except Exception: await manager.disconnect(websocket)
@router.websocket('/ws/notifications')
async def ws_notifications(websocket:WebSocket,token:str):
    payload=decode_token(token)
    if not payload or payload.get('type')!='access': await websocket.close(code=1008); return
    uid=int(payload['sub']); await manager.connect_user(uid,websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: await manager.disconnect(websocket)
    except Exception: await manager.disconnect(websocket)
@router.get('/queue-test',response_class=HTMLResponse)
def queue_test():
    return """<!doctype html><html><head><title>Queue WebSocket Test</title></head><body><h2>Live Queue Test</h2><label>Doctor ID <input id="doctor" value="1"></label><label>Access token <input id="token" size="80"></label><button onclick="connectWs()">Connect</button><pre id="messages"></pre><script>let ws;function connectWs(){if(ws)ws.close();const d=document.getElementById('doctor').value;const t=document.getElementById('token').value;ws=new WebSocket(`ws://${location.host}/ws/queue/${d}?token=${encodeURIComponent(t)}`);ws.onmessage=e=>document.getElementById('messages').textContent+=e.data+'\n';ws.onopen=()=>document.getElementById('messages').textContent+='Connected\n';ws.onclose=()=>document.getElementById('messages').textContent+='Disconnected\n';}</script></body></html>"""

@router.get('/reports/dashboard')
def dashboard(admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    q=db.query(Appointment).filter(Appointment.appointment_date==date.today()); rows=q.all()
    return {'date':date.today(),'total_appointments':len(rows),'checked_in':sum(a.status=='Checked-In' for a in rows),'completed':sum(a.status=='Completed' for a in rows),'cancelled':sum(a.status=='Cancelled' for a in rows),'no_shows':sum(a.status=='No-Show' for a in rows),'consultation_revenue':sum(a.consultation_fee for a in rows if a.status=='Completed')}
@router.get('/reports/doctor-performance')
def doctor_performance(date_from:date,date_to:date,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    rows=db.query(Doctor).all(); out=[]
    for d in rows:
        a=db.query(Appointment).filter(Appointment.doctor_id==d.id,Appointment.appointment_date.between(date_from,date_to)).all(); completed=sum(x.status=='Completed' for x in a); no_show=sum(x.status=='No-Show' for x in a)
        out.append({'doctor_id':d.id,'doctor_name':d.name,'appointments':len(a),'completed_consultations':completed,'no_show_percentage':round(no_show*100/len(a),2) if a else 0,'revenue':sum(x.consultation_fee for x in a if x.status=='Completed')})
    return out
@router.get('/reports/department-summary')
def department_summary(date_from:date,date_to:date,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    return [{'department':name,'appointment_count':count} for name,count in db.query(Department.name,func.count(Appointment.id)).join(Doctor,Doctor.department_id==Department.id).join(Appointment,Appointment.doctor_id==Doctor.id).filter(Appointment.appointment_date.between(date_from,date_to)).group_by(Department.name).all()]
@router.get('/reports/peak-hours')
def peak_hours(date_from:date|None=None,date_to:date|None=None,admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    q=db.query(Appointment).filter(Appointment.status!='Cancelled')
    if date_from: q=q.filter(Appointment.appointment_date>=date_from)
    if date_to: q=q.filter(Appointment.appointment_date<=date_to)
    counts={h:0 for h in range(24)}
    for a in q.all(): counts[a.slot_time.hour]+=1
    return [{'hour':f'{h:02d}:00','appointments':n} for h,n in counts.items()]
@router.get('/reports/frequent-no-shows')
def frequent_no_shows(admin:User=Depends(require_roles('Admin')),db:Session=Depends(get_db)):
    since=date.today()-timedelta(days=90)
    rows=db.query(User.id,User.full_name,User.email,func.count(Appointment.id).label('no_shows')).join(Appointment,Appointment.patient_id==User.id).filter(Appointment.status=='No-Show',Appointment.appointment_date>=since).group_by(User.id,User.full_name,User.email).having(func.count(Appointment.id)>=3).all()
    return [{'patient_id':r.id,'name':r.full_name,'email':r.email,'no_shows':r.no_shows} for r in rows]
