from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class SchemeInputPayload(BaseModel):
    c0: Decimal = Field(ge=0)
    g: Decimal = Field(ge=0)
    eta_mau: Decimal = Field(alias="etaMau", ge=0, le=1)
    cov_mau: Decimal = Field(alias="covMau", ge=0, le=1)
    eta_ceil: Decimal = Field(alias="etaCeil", ge=0, le=1)
    cov_ceil: Decimal = Field(alias="covCeil", ge=0, le=1)
    eta_aru: Decimal = Field(alias="etaAru", ge=0, le=1)
    cov_aru: Decimal = Field(alias="covAru", ge=0, le=1)
    alpha: Decimal = Field(ge=0, le=1)
    beta: Decimal = Field(ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_ratio(self) -> "SchemeInputPayload":
        if abs(self.alpha + self.beta - Decimal("1")) > Decimal("1e-10"):
            raise ValueError("alpha 与 beta 之和必须为 1")
        return self


class SchemePayload(BaseModel):
    cleanroom_id: int = Field(alias="cleanroomId", gt=0)
    name: str = Field(min_length=1, max_length=100)
    conc_unit: str = Field(default="ug", alias="concUnit")
    molar_mass_m: Decimal | None = Field(default=None, alias="molarMassM", gt=0)
    molar_volume_vm: Decimal = Field(default=Decimal("24.04"), alias="molarVolumeVm", gt=0)
    std_source: Literal["industry", "enterprise", "customer", "manual"] = Field(
        default="manual", alias="stdSource"
    )
    std_pollutant_id: int | None = Field(default=None, alias="stdPollutantId", gt=0)
    std_library_id: int | None = Field(default=None, alias="stdLibraryId", gt=0)
    target_value: Decimal | None = Field(default=None, alias="targetValue", ge=0)
    input: SchemeInputPayload

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("conc_unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        value = {"ug": "ugm3", "ug/m3": "ugm3", "μg/m³": "ugm3"}.get(value, value)
        if value not in {"ppb", "ugm3"}:
            raise ValueError("concUnit 仅支持 ppb 或 ug")
        return value

    @model_validator(mode="after")
    def validate_conversion(self) -> "SchemePayload":
        if self.conc_unit == "ppb" and self.molar_mass_m is None:
            raise ValueError("使用 ppb 时必须提供 molarMassM")
        if self.std_source == "manual" and self.std_library_id is not None:
            raise ValueError("手工标准不能关联 stdLibraryId")
        return self


class CompareRequest(BaseModel):
    scheme_ids: list[int] = Field(alias="schemeIds", min_length=1, max_length=5)
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("scheme_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("schemeIds 必须为正整数")
        if len(set(value)) != len(value):
            raise ValueError("schemeIds 不能重复")
        return value


class CustomerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    remark: str | None = Field(default=None, max_length=255)


class ProjectPayload(BaseModel):
    customer_id: int = Field(alias="customerId", gt=0)
    name: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=150)
    remark: str | None = Field(default=None, max_length=255)
    model_config = ConfigDict(populate_by_name=True)


class CleanroomPayload(BaseModel):
    project_id: int = Field(alias="projectId", gt=0)
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=50)
    remark: str | None = Field(default=None, max_length=255)
    model_config = ConfigDict(populate_by_name=True)


class Envelope(BaseModel):
    code: int
    message: str
    data: Any = None
    request_id: str = Field(alias="requestId")
    model_config = ConfigDict(populate_by_name=True)
