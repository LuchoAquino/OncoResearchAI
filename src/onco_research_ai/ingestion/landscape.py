"""Qué panorama estudiamos. Un solo sitio para cambiar el alcance."""

from datetime import date

CONDITION = "melanoma"

# Fármacos de referencia: terapia dirigida BRAF/MEK
# e inmunoterapia (anti-PD-1, anti-CTLA-4, anti-LAG-3).
DRUGS = [
    "encorafenib",
    "binimetinib",
    "dabrafenib",
    "trametinib",
    "vemurafenib",
    "cobimetinib",
    "pembrolizumab",
    "nivolumab",
    "ipilimumab",
    "relatlimab",
]

FIRST_YEAR = 2020


def last_year() -> int:
    return date.today().year
