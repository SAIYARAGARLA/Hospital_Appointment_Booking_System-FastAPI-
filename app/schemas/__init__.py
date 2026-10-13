from datetime import date, time
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class ORMModel(BaseModel): model_config=ConfigDict(from_attributes=True)
class RegisterIn(BaseModel):
    full_name:str=Field(min_length=2,max_length=120); email:EmailStr; phone:str; password:str=Field(min_length=8,max_length=72)
    @field_validator('phone')
    @classmethod
    def phone_digits(cls,v):
        if not v.isdigit() or len(v)!=10: raise ValueError('Phone must contain exactly 10 digits')
        return v
class LoginIn(BaseModel): email:EmailStr; password:str
class RefreshIn(BaseModel): refresh_token:str
class UserOut(ORMModel): id:int; full_name:str; email:EmailStr; phone:str; role:str; is_active:bool
class DepartmentIn(BaseModel): name:str=Field(min_length=2,max_length=100); description:str|None=None
class DoctorIn(BaseModel): user_id:int; name:str; department_id:int; specialization:str; qualification:str; experience_years:int=Field(ge=0); consultation_fee:float=Field(gt=0); slot_duration_minutes:int=15; is_active:bool=True

class ScheduleIn(BaseModel): day_of_week:str; start_time:time; end_time:time; break_start:time|None=None; break_end:time|None=None
class LeaveIn(BaseModel): leave_date:date; reason:str|None=None
class AppointmentIn(BaseModel): doctor_id:int; appointment_date:date; slot_time:time; reason:str|None=None
class ConsultationIn(BaseModel): symptoms:str; diagnosis:str; prescription:str|None=None; advice:str|None=None; follow_up_date:date|None=None
class ReviewIn(BaseModel): rating:int=Field(ge=1,le=5); feedback:str|None=None
