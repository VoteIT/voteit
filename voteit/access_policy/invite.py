from pydantic import EmailStr
from pydantic.main import BaseModel
from voteit.access_policy.registries import invite_data


@invite_data
class Email(BaseModel):
    email: EmailStr
