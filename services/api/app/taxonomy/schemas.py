from pydantic import BaseModel, Field


class SkillHit(BaseModel):
    id: str
    name: str
    synonyms: list[str] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)


class SpecializationOut(BaseModel):
    id: str
    name: str
    adjacent: list[str] = Field(default_factory=list)


class DomainOut(BaseModel):
    id: str
    name: str


class DeclineReasonOut(BaseModel):
    id: str
    name: str
