"""Deterministic rules: model output never decides which order is inconsistent."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    created_at: datetime
    financial_status: Literal["paid", "pending", "refunded", "voided"]
    fulfillment_status: Literal["unfulfilled", "partial", "fulfilled"]
    total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    physical_goods: bool = True
    tracking_number: str = Field(default="", max_length=100)
    delivery_method: Literal["tracked", "pickup", "digital"] = "tracked"
    provider_status: Literal["paid", "pending", "refunded", "unknown"] = "unknown"
    stock_status: Literal["available", "insufficient", "unknown"] = "unknown"
    shipment_status: Literal["not_shipped", "handed_over", "delivered", "unknown"] = "unknown"

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must contain a UTC offset")
        return value.astimezone(timezone.utc)

class ImportBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orders: list[Order] = Field(min_length=1, max_length=1000)
    @model_validator(mode="after")
    def unique_orders(self):
        ids = [o.order_id for o in self.orders]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate order IDs in batch")
        return self

class Finding(BaseModel):
    order_id: str
    code: str
    severity: Literal["high", "medium", "low"]
    reason: str
    suggested_action: str
    evidence: dict[str, str]

class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paid_unfulfilled_hours: int = Field(default=48, ge=1, le=720, strict=True)
    pending_payment_hours: int = Field(default=24, ge=1, le=720, strict=True)

RULE_VERSION = "1.1.0"

def evaluate(order: Order, now: datetime, policy: ReviewPolicy | None = None) -> list[Finding]:
    policy = policy or ReviewPolicy()
    if now.tzinfo is None:
        raise ValueError("Evaluation time must include UTC offset")
    age = (now - order.created_at).total_seconds() / 3600
    if age < 0:
        raise ValueError(f"{order.order_id}: created_at is in the future")
    result = []
    def add(code, severity, reason, action, **evidence):
        result.append(Finding(order_id=order.order_id, code=code, severity=severity,
            reason=reason, suggested_action=action, evidence={k: str(v) for k,v in evidence.items()}))
    if order.financial_status == "paid" and order.fulfillment_status != "fulfilled" and age >= policy.paid_unfulfilled_hours:
        add("PAID_NOT_FULFILLED", "high", f"Paid order remains unfulfilled or partial after {policy.paid_unfulfilled_hours} hours.",
            "Check stock allocation and fulfillment queue before contacting the customer.",
            age_hours=round(age,1), threshold_hours=policy.paid_unfulfilled_hours, financial=order.financial_status, fulfillment=order.fulfillment_status)
    if order.financial_status == "pending" and order.fulfillment_status == "unfulfilled" and age >= policy.pending_payment_hours:
        add("PAYMENT_PENDING", "medium", f"Payment remains pending after {policy.pending_payment_hours} hours.",
            "Check the payment provider record before a reminder or cancellation.", age_hours=round(age,1), threshold_hours=policy.pending_payment_hours)
    if order.financial_status in {"refunded", "voided"} and order.fulfillment_status == "fulfilled":
        add("REFUNDED_FULFILLED", "high", "Refunded or voided order is marked fulfilled.",
            "Compare refund and shipment records; this may be a legitimate return.", financial=order.financial_status)
    if order.provider_status != "unknown" and order.provider_status != order.financial_status:
        add("PAYMENT_MISMATCH", "high", "Store and provider payment states disagree.",
            "Check timestamps and transaction IDs; do not charge again.", store=order.financial_status, provider=order.provider_status)
    if order.physical_goods and order.delivery_method == "tracked" and order.fulfillment_status == "fulfilled" and not order.tracking_number.strip():
        add("TRACKING_MISSING", "low", "Tracked physical shipment has no tracking number.",
            "Check the carrier handover record and tracking sync.", delivery_method=order.delivery_method)
    if order.physical_goods and order.stock_status == "insufficient" and order.financial_status == "paid" and order.fulfillment_status != "fulfilled":
        add("STOCK_SHORTAGE", "high", "Paid physical order has insufficient stock.",
            "Verify allocation and replenishment; propose a resolution for human review.", stock=order.stock_status)
    if order.shipment_status in {"handed_over", "delivered"} and order.fulfillment_status == "unfulfilled":
        add("SHIPMENT_MISMATCH", "medium", "Carrier state indicates shipment but store says unfulfilled.",
            "Check carrier integration sync and verify before updating the store.", shipment=order.shipment_status, fulfillment=order.fulfillment_status)
    return result
