"""Diccionario inicial de fármacos (manual). ChEMBL ampliará los sinónimos cuando responda.

kind: inn = nombre genérico | brand = marca comercial | code = código de desarrollo.
"""

SEED: dict[str, dict[str, list[str]]] = {
    "encorafenib": {"brand": ["Braftovi"], "code": ["LGX818"]},
    "binimetinib": {"brand": ["Mektovi"], "code": ["MEK162", "ARRY-162"]},
    "dabrafenib": {"brand": ["Tafinlar"], "code": ["GSK2118436"]},
    "trametinib": {"brand": ["Mekinist"], "code": ["GSK1120212"]},
    "vemurafenib": {"brand": ["Zelboraf"], "code": ["PLX4032", "RG7204"]},
    "cobimetinib": {"brand": ["Cotellic"], "code": ["GDC-0973", "XL518"]},
    "pembrolizumab": {"brand": ["Keytruda"], "code": ["MK-3475", "lambrolizumab"]},
    "nivolumab": {"brand": ["Opdivo"], "code": ["BMS-936558", "ONO-4538"]},
    "ipilimumab": {"brand": ["Yervoy"], "code": ["MDX-010", "BMS-734016"]},
    "relatlimab": {"brand": ["Opdualag"], "code": ["BMS-986016"]},
}

# Mecanismo de acción (diana). Lo daría ChEMBL; mientras tanto, conocimiento estándar.
MECHANISM: dict[str, str] = {
    "encorafenib": "BRAF inhibitor",
    "dabrafenib": "BRAF inhibitor",
    "vemurafenib": "BRAF inhibitor",
    "binimetinib": "MEK inhibitor",
    "trametinib": "MEK inhibitor",
    "cobimetinib": "MEK inhibitor",
    "pembrolizumab": "anti-PD-1",
    "nivolumab": "anti-PD-1",
    "ipilimumab": "anti-CTLA-4",
    "relatlimab": "anti-LAG-3",
}
