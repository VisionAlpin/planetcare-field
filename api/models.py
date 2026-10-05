"""SQLAlchemy models — PlanetCare Field (Phase 0, JSON geometry)"""

import uuid
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid():
    return str(uuid.uuid4())


class Farm(Base):
    __tablename__ = "pcf_farms"

    id          = Column(Text, primary_key=True, default=_uuid)
    owner_email = Column(Text, nullable=False, index=True)
    name        = Column(Text, nullable=False)
    country     = Column(String(2), default="AT")
    region      = Column(Text)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    fields = relationship("Field", back_populates="farm", cascade="all, delete-orphan")


class Field(Base):
    __tablename__ = "pcf_fields"

    id         = Column(Text, primary_key=True, default=_uuid)
    farm_id    = Column(Text, ForeignKey("pcf_farms.id", ondelete="CASCADE"), nullable=False)
    name       = Column(Text)
    area_ha    = Column(Numeric)
    geom       = Column(JSONB)   # GeoJSON Polygon
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    farm       = relationship("Farm", back_populates="fields")
    crop_years = relationship("CropYear", back_populates="field", cascade="all, delete-orphan")


class CropYear(Base):
    __tablename__ = "pcf_crop_years"

    id           = Column(Text, primary_key=True, default=_uuid)
    field_id     = Column(Text, ForeignKey("pcf_fields.id", ondelete="CASCADE"), nullable=False)
    year         = Column(Integer, nullable=False)
    crop_type    = Column(Text)
    sowing_date  = Column(Date)
    harvest_date = Column(Date)

    field      = relationship("Field", back_populates="crop_years")
    indicators = relationship("IndicatorValue", back_populates="crop_year", cascade="all, delete-orphan")
    profiles   = relationship("FieldProfile", back_populates="crop_year", cascade="all, delete-orphan")


class IndicatorValue(Base):
    __tablename__ = "pcf_indicator_values"

    id             = Column(Text, primary_key=True, default=_uuid)
    crop_year_id   = Column(Text, ForeignKey("pcf_crop_years.id", ondelete="CASCADE"), nullable=False)
    indicator      = Column(Text, nullable=False)
    value          = Column(Numeric)
    unit           = Column(Text)
    source         = Column(Text)
    acquired_at    = Column(Date)
    method_version = Column(Text, default="1.0")
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    crop_year = relationship("CropYear", back_populates="indicators")


class FieldProfile(Base):
    __tablename__ = "pcf_field_profiles"

    id                 = Column(Text, primary_key=True, default=_uuid)
    crop_year_id       = Column(Text, ForeignKey("pcf_crop_years.id"), nullable=False)
    score_water        = Column(Numeric)
    score_biodiversity = Column(Numeric)
    score_pesticide    = Column(Numeric)
    score_total        = Column(Numeric)
    method_version     = Column(Text, default="1.0")
    is_public          = Column(Boolean, default=False)
    calculated_at      = Column(DateTime(timezone=True), server_default=func.now())

    crop_year     = relationship("CropYear", back_populates="profiles")
    product_links = relationship("ProductLink", back_populates="profile", cascade="all, delete-orphan")


class ProductLink(Base):
    __tablename__ = "pcf_product_links"

    id               = Column(Text, primary_key=True, default=_uuid)
    gtin             = Column(Text, nullable=False, index=True)
    field_profile_id = Column(Text, ForeignKey("pcf_field_profiles.id", ondelete="CASCADE"))
    batch_id         = Column(Text)
    linked_at        = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("FieldProfile", back_populates="product_links")



# DemandEvent, DemandAggregate, Consent: ab v0.5.0 über bridge.py / direkt per SQL verwaltet

