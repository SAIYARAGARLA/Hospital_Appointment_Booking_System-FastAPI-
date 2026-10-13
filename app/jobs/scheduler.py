import logging
from datetime import datetime, timedelta, date
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.models import Appointment, User, Doctor, Consultation
from app.services.notifications import send_email
log=logging.getLogger(__name__)
scheduler=BackgroundScheduler(timezone='Asia/Kolkata')

def reminder_job():
    db=SessionLocal()
    try:
        now=datetime.now(); end=now+timedelta(hours=24)
        rows=db.query(Appointment).filter(Appointment.status=='Booked',Appointment.reminder_sent.is_(False),Appointment.appointment_date>=now.date(),Appointment.appointment_date<=end.date()).all()
        for a in rows:
            slot=datetime.combine(a.appointment_date,a.slot_time)
            if now < slot <= end:
                send_email(a.patient.email,'Appointment reminder',f'Reminder: {a.appointment_number} with Dr. {a.doctor.name} on {a.appointment_date} at {a.slot_time}. Token: {a.token_number}.')
                a.reminder_sent=True
        db.commit()
    except Exception: db.rollback(); log.exception('Reminder job failed')
    finally: db.close()

def no_show_job():
    db=SessionLocal()
    try:
        now=datetime.now(); rows=db.query(Appointment).filter(Appointment.status=='Booked',Appointment.appointment_date<=now.date()).all()
        for a in rows:
            if datetime.combine(a.appointment_date,a.slot_time)+timedelta(minutes=30) < now:
                old=a.status; a.status='No-Show'; db.add(__import__('app.models',fromlist=['AppointmentHistory']).AppointmentHistory(appointment_id=a.id,old_status=old,new_status=a.status,changed_by=a.patient_id))
        db.commit()
    except Exception: db.rollback(); log.exception('No-show job failed')
    finally: db.close()

def followup_job():
    db=SessionLocal()
    try:
        tomorrow=date.today()+timedelta(days=1)
        rows=db.query(Consultation).filter(Consultation.follow_up_date==tomorrow).all()
        for c in rows: send_email(c.appointment.patient.email,'Follow-up reminder',f'Your follow-up date is tomorrow ({tomorrow}) for appointment {c.appointment.appointment_number}.')
    except Exception: log.exception('Follow-up job failed')
    finally: db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(reminder_job,'interval',hours=1,id='reminders',replace_existing=True)
        scheduler.add_job(no_show_job,'interval',minutes=15,id='no_show',replace_existing=True)
        scheduler.add_job(followup_job,'cron',hour=9,minute=0,id='followups',replace_existing=True)
        scheduler.start()
