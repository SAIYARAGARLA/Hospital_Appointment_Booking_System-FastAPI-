import logging, smtplib
from email.message import EmailMessage
from app.config import settings
log=logging.getLogger(__name__)

def send_email(to_email:str, subject:str, body:str):
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password or not settings.smtp_from:
        log.info('SMTP not configured; email skipped for %s: %s',to_email,subject); return
    try:
        msg=EmailMessage(); msg['Subject']=subject; msg['From']=settings.smtp_from; msg['To']=to_email; msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(); server.login(settings.smtp_username,settings.smtp_password); server.send_message(msg)
    except Exception: log.exception('Email delivery failed to %s',to_email)
