"""Réexport : la validité dérivée est commune aux permis, habilitations et documents (app.core.validity)."""

from app.core.validity import ELIGIBLE, Validity, derive_validity

__all__ = ["ELIGIBLE", "Validity", "derive_validity"]
