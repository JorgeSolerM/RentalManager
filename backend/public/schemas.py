from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from typing import Literal


class PublicFeatureDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category: str
    icon_key: str | None = None


class PublicFilterFeatureDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    category: str


class PublicFeatureGroupDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    icon_url: str
    features: tuple[PublicFeatureDTO, ...]


class PublicHousingRuleDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    allowed: bool


class PublicTenantAgeDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum: int | None = None
    maximum: int | None = None


class PublicRequirementDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None


class PublicImageDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    url_320: str
    url_768: str
    url_1600: str
    source: Literal["room", "property"]
    width: int
    height: int

    @property
    def srcset(self) -> str:
        return (
            f"{self.url_320} 320w, {self.url_768} 768w, "
            f"{self.url_1600} 1600w"
        )


class PublicAvailabilityDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["available_now", "available_from", "available_period"]
    available_from: date | None = None
    available_until: date | None = None


class PublicManagerPhotoDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    url_320: str
    url_768: str
    url_1600: str
    width: int
    height: int


class PublicManagerDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    initials: str
    photo: PublicManagerPhotoDTO | None = None
    whatsapp_url: str | None = None


class PublicRoomCardDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    title: str
    location: str
    price_monthly: Decimal
    square_meters: Decimal | None
    availability: PublicAvailabilityDTO
    features: tuple[PublicFeatureDTO, ...]
    primary_image: PublicImageDTO
    contact_url: str | None = None


class PublicRoomDetailDTO(PublicRoomCardDTO):
    description: str
    map_url: str | None
    minimum_stay_months: int
    maximum_stay_months: int | None
    flatmates_count: int
    tenant_gender_preference: Literal["any", "male", "female"]
    room_features: tuple[PublicFeatureDTO, ...]
    property_features: tuple[PublicFeatureDTO, ...]
    feature_groups: tuple[PublicFeatureGroupDTO, ...]
    highlighted_features: tuple[PublicFeatureDTO, ...]
    housing_rules: tuple[PublicHousingRuleDTO, ...]
    tenant_age: PublicTenantAgeDTO | None
    requirements: tuple[PublicRequirementDTO, ...]
    has_private_bathroom: bool
    shared_full_bathroom_count: int | None
    shared_toilet_count: int | None
    manager: PublicManagerDTO
    gallery: tuple[PublicImageDTO, ...]
    meta_description: str
