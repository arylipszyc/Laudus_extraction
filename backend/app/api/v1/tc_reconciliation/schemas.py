"""Schemas de la vista de cuadre TC — Story 6.6 (`GET /tc/reconciliation`).

Una fila por tarjeta × mes con los cinco chequeos C1–C5 y los números lado a lado (cartola vs.
ledger vs. Laudus). Reusa `TcLaudusPayment` del módulo de cartolas.
"""
from __future__ import annotations

from pydantic import BaseModel

from backend.app.api.v1.cartolas.schemas import TcLaudusPayment


class TcMovement(BaseModel):
    date: str
    narration: str
    amount: float            # delta a TC:Real (moneda CLP posteada); signo = dirección de la deuda
    operation_type: str


class TcReconciliationRow(BaseModel):
    """Cuadre C1–C5 de una cartola (tarjeta × mes), más los movimientos para el detalle expandible."""
    card: str                # bank_account_id
    year_month: str
    tc_real_account: str
    lump_account: str
    currency: str
    fx: float
    opening: float | None
    closing: float           # moneda nativa
    closing_clp: float       # closing × fx (CLP), lo que compara C1
    # C1
    c1_ok: bool
    tc_real_balance: float
    # C2
    c2_ok: bool
    c2_prior_closing: float | None = None
    c2_reason: str | None = None
    # C3
    c3_ok: bool
    c3_corrupted_count: int
    # C4 (pago)
    pago_cartola: float
    laudus_payment_total: float
    laudus_payments: list[TcLaudusPayment] = []
    pago_ok: bool
    # C5
    c5_ok: bool
    c5_residual: float
    # agregado + detalle
    status: str              # green | yellow | red
    movements: list[TcMovement] = []
    sum_compras: float
    sum_pagos: float
    sum_cargos: float
