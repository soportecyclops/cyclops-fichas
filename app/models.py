"""Property: esquema normalizado, agnóstico de portal de origen."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator

class SourceInfo(BaseModel):
    url: str
    portal: str = "desconocido"

class Location(BaseModel):
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    address: Optional[str] = None

class FeatureCategory(BaseModel):
    """Grupo de características con título y sus ítems."""
    title: str
    items: list[str] = Field(default_factory=list)

class Property(BaseModel):
    type: Optional[str] = None
    operation: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    location: Location = Field(default_factory=Location)
    rooms: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_total: Optional[float] = None
    area_covered: Optional[float] = None
    expenses: Optional[float] = None
    title: Optional[str] = None
    description: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    feature_categories: list[FeatureCategory] = Field(default_factory=list)
    source: SourceInfo

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

    def is_usable(self) -> bool:
        has_price = self.price is not None
        has_title_or_desc = bool(self.title or self.description)
        has_image = bool(self.images)
        return has_title_or_desc and (has_price or has_image)

class AgentProfile(BaseModel):
    """Perfil del agente con datos extendidos."""
    name: str
    phone: str
    whatsapp: str
    email: Optional[str] = None
    agency_name: str = "CENTURY 21"
    address: Optional[str] = None
    website: Optional[str] = None
    social_media: Optional[str] = None
    logo_url: Optional[str] = None
    photo_url: Optional[str] = None
