"""Interfaz de OncoResearchAI (Streamlit). Consume la API REST: no toca la base de datos.

uv run streamlit run app/streamlit_app.py      (con la API corriendo en el puerto 8000)
"""

import html
import os

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(
    page_title="OncoResearchAI", page_icon=":material/biotech:", layout="wide"
)

# ---------------------------------------------------------------- identidad visual
# Sistema dado por la skill design-taste-frontend (start.mjs deal: palette white-navy-tab,
# type host): tinta azul marino sobre blanco, acento naranja SOLO en rellenos y marcas (como
# texto tendría 2,3:1 de contraste), Host Grotesk para leer y JetBrains Mono para los códigos.
# Texto de lectura a 16 px; nada por debajo de 13 px.
# Un solo tema, a propósito: .streamlit/config.toml fija el fondo CLARO. No se mira
# st.context.theme.type, porque refleja el modo del sistema del usuario (oscuro) aunque el fondo
# siga claro, y eso pintaba texto blanco sobre blanco. Fondo y texto salen del mismo sitio.
DARK = False
T = {  # tokens
    "bg": "#f5f7fc",
    "surface": "#ffffff",
    "card": "#ffffff",
    "ink": "#1b2a4e",  # azul marino: títulos y texto principal
    "muted": "#4d5b78",  # gris azulado: texto secundario (6,4:1 sobre la página)
    "line": "#dfe5f2",
    "accent": "#f7941d",  # naranja: solo bordes y marcas, nunca texto
    "blue": "#2457d6",  # enlaces, pestaña activa, etiquetas pequeñas
    "blue_soft": "#e8effe",
    "green_soft": "#e2f5ed",
    "orange_soft": "#fff0e1",
    "ok": "#0e6b49",
    "ok_soft": "#e2f5ed",
    "warn": "#8a4b00",
    "warn_soft": "#fff0d6",
    "info_soft": "#e8effe",
    "side_bg": "#1b2a4e",  # barra lateral oscura
    "side_ink": "#eef1fb",
    "side_muted": "#b4bedb",
}
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@400..700&family=JetBrains+Mono:wght@400..500&display=swap');
html, body, .stApp, p, li, label, input, textarea, [data-testid="stMarkdownContainer"] {{
  font-family: 'Host Grotesk', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
.stApp, [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{
  font-size: 16px; line-height: 1.6; color: {T["ink"]};
}}
h1, h2, h3 {{ font-family: 'Host Grotesk', system-ui, sans-serif; font-weight: 600 !important;
  letter-spacing: -0.02em; text-wrap: balance; color: {T["ink"]}; }}
.block-container {{ padding-top: 2.4rem; max-width: 1200px; }}
[data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; }}
code, .mono {{ font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace; }}
a {{ color: {T["blue"]}; text-decoration-color: {T["blue"]}; text-underline-offset: 3px; }}

/* ---- barra lateral oscura ---- */
[data-testid="stSidebar"] {{ background: {T["side_bg"]}; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] li,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] label {{ color: {T["side_ink"]}; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color: {T["side_muted"]}; }}
.side-stats {{ font-size: .95rem; color: {T["side_muted"]}; line-height: 1.8; }}
.side-stats b {{ color: #ffffff; font-weight: 600; font-variant-numeric: tabular-nums; }}
.side-title {{ font-size: 1.25rem; font-weight: 600; color: #ffffff; letter-spacing: -0.02em;
  margin-bottom: .2rem; }}
.side-title i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  background: {T["accent"]}; margin-right: 8px; }}
.side-eyebrow {{ font-size: .78rem; letter-spacing: .07em; text-transform: uppercase; font-weight: 600;
  color: {T["side_muted"]}; margin: .9rem 0 .2rem; }}

/* ---- textos de sección ---- */
.eyebrow {{ font-size: .8rem; letter-spacing: .07em; text-transform: uppercase; color: {T["blue"]};
  font-weight: 700; margin: 0 0 .4rem; }}
.hero h1 {{ font-size: 2.1rem; line-height: 1.15; letter-spacing: -0.035em; margin: 0 0 .6rem; }}
.hero p {{ color: {T["muted"]}; max-width: 64ch; margin: 0; font-size: 1.08rem; line-height: 1.6; }}

/* ---- tres tarjetas de ayuda, cada una de su color ---- */
.expect {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px;
  margin: 1.4rem 0 1rem; }}
.expect div {{ border-radius: 12px; padding: 14px 16px 14px; border-top: 4px solid {T["blue"]};
  background: {T["blue_soft"]}; }}
.expect div:nth-child(2) {{ border-top-color: #1baf7a; background: {T["green_soft"]}; }}
.expect div:nth-child(3) {{ border-top-color: {T["accent"]}; background: {T["orange_soft"]}; }}
.expect b {{ display: block; color: {T["ink"]}; font-weight: 600; font-size: 1.02rem; margin-bottom: .25rem; }}
.expect span {{ color: {T["ink"]}; opacity: .82; font-size: .98rem; line-height: 1.55; }}

/* ---- ejemplos de preguntas, un color por grupo ---- */
.group-label {{ font-weight: 600; font-size: 1.05rem; color: {T["ink"]}; margin: 1rem 0 .15rem;
  display: flex; align-items: center; gap: 8px; }}
.group-label::before {{ content: ""; width: 10px; height: 10px; border-radius: 50%; background: {T["blue"]}; }}
.g2 .group-label::before {{ background: #1baf7a; }}
.g3 .group-label::before {{ background: {T["accent"]}; }}
.group-hint {{ color: {T["muted"]}; font-size: .95rem; line-height: 1.5; margin-bottom: .6rem; }}
[data-testid="stColumn"]:nth-child(1) .stButton button {{ border-left: 5px solid {T["blue"]}; }}
[data-testid="stColumn"]:nth-child(2) .stButton button {{ border-left: 5px solid #1baf7a; }}
[data-testid="stColumn"]:nth-child(3) .stButton button {{ border-left: 5px solid {T["accent"]}; }}

/* ---- etiquetas ---- */
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: .4rem 0 .3rem; }}
.chip {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 12px;
  font-size: .88rem; font-weight: 600; border: 1px solid {T["line"]}; color: {T["ink"]};
  background: {T["card"]}; }}
.chip.ok {{ color: {T["ok"]}; background: {T["ok_soft"]}; border-color: transparent; }}
.chip.warn {{ color: {T["warn"]}; background: {T["warn_soft"]}; border-color: transparent; }}
.chip.accent {{ color: #1d4fb8; background: {T["info_soft"]}; border-color: transparent; }}
.chip.braf {{ color: #1d4fb8; background: #e8effe; border-color: transparent; }}
.chip.mek {{ color: #9a4300; background: #fff0e1; border-color: transparent; }}
.chip.pd1 {{ color: #0e6b49; background: #e2f5ed; border-color: transparent; }}
.chip.ctla4 {{ color: #7a5400; background: #fff6d6; border-color: transparent; }}
.chip.lag3 {{ color: #a3285c; background: #fde8f0; border-color: transparent; }}

/* ---- respuesta y fuentes ---- */
.question {{ font-size: 1.3rem; font-weight: 600; letter-spacing: -0.01em; color: {T["ink"]};
  margin: 1.4rem 0 .4rem; }}
.src {{ border: 1px solid {T["line"]}; border-left: 5px solid {T["blue"]}; background: {T["card"]};
  border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
  transition: transform .15s ease, box-shadow .15s ease; }}
.src.s-publication {{ border-left-color: #1baf7a; }}
.src.s-label {{ border-left-color: {T["accent"]}; }}
.src.s-congress {{ border-left-color: #e87ba4; }}
.src:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(27,42,78,.10); }}
.src .top {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }}
.src .ref {{ font-family: 'JetBrains Mono', monospace; font-size: .82rem; font-weight: 500;
  color: #ffffff; background: {T["blue"]}; border-radius: 4px; padding: 1px 7px; }}
.src.s-publication .ref {{ background: #0e6b49; }}
.src.s-label .ref {{ background: #b35a00; }}
.src.s-congress .ref {{ background: #a3285c; }}
.src .kind {{ font-size: .8rem; letter-spacing: .05em; text-transform: uppercase; color: {T["muted"]};
  font-weight: 700; }}
.src a {{ color: {T["ink"]}; font-weight: 600; font-size: 1rem; text-decoration: none; line-height: 1.4; }}
.src a:hover {{ color: {T["blue"]}; text-decoration: underline; }}
.src .meta {{ font-family: 'JetBrains Mono', monospace; font-size: .82rem; color: {T["muted"]};
  margin-top: 6px; }}
.src .snip {{ font-size: .94rem; color: {T["muted"]}; margin-top: 8px; line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
.steps {{ font-size: .92rem; color: {T["muted"]}; line-height: 1.7; margin-top: .4rem; }}
.steps b {{ color: {T["blue"]}; font-weight: 600; }}
.takeaways {{ border-left: 4px solid {T["blue"]}; background: {T["blue_soft"]}; border-radius: 0 10px 10px 0;
  padding: .7rem 1rem .7rem 1.6rem; margin: .6rem 0 1.1rem; }}
.takeaways li {{ color: {T["ink"]}; font-size: 1.02rem; margin-bottom: .35rem; }}

/* ---- cifras, un color por columna ---- */
[data-testid="stMetric"] {{ background: {T["card"]}; border: 1px solid {T["line"]}; border-top: 4px solid {T["blue"]};
  border-radius: 12px; padding: 12px 16px; }}
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {{ border-top-color: #1baf7a; }}
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {{ border-top-color: {T["accent"]}; }}
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {{ border-top-color: #e87ba4; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div, [data-testid="stMetricValue"] p {{
  font-size: 2.3rem !important; line-height: 1.15 !important; font-variant-numeric: tabular-nums;
  font-weight: 600; letter-spacing: -0.03em; color: {T["ink"]}; }}
[data-testid="stMetricLabel"] p {{ font-size: .95rem; color: {T["muted"]}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaption"] {{ opacity: 1 !important; }}
[data-testid="stCaptionContainer"] p {{ font-size: .95rem; color: {T["muted"]}; }}
.stButton button {{ border-radius: 10px; min-height: 44px; text-align: left; justify-content: flex-start;
  background: {T["card"]}; border-color: {T["line"]}; color: {T["ink"]};
  transition: transform .12s ease, box-shadow .12s ease; }}
.stButton button:hover {{ color: {T["ink"]}; transform: translateY(-1px); box-shadow: 0 3px 10px rgba(27,42,78,.12); }}
.stButton button:active {{ transform: translateY(1px); }}
.stButton button p {{ font-size: .96rem; white-space: normal; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
""",
    unsafe_allow_html=True,
)

# Paleta categórica validada (orden fijo: el color sigue al mecanismo, nunca al ranking).
MECHANISMS = [
    "BRAF inhibitor",
    "MEK inhibitor",
    "anti-PD-1",
    "anti-CTLA-4",
    "anti-LAG-3",
]
PALETTE = (
    ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
    if DARK
    else ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
)
MECH_SCALE = alt.Scale(domain=MECHANISMS, range=PALETTE)
SEQ = (
    ["#1a2233", "#5d6b94", "#c9d1ea"] if DARK else ["#eef0f6", "#7b86a8", "#1f2b4d"]
)  # un solo tono (marino)
SOURCE_KIND = {
    "trial": "Ensayo clínico",
    "publication": "Artículo",
    "label": "Ficha técnica FDA",
    "congress": "Congreso (PDF)",
}
MECH_CLASS = {
    "BRAF inhibitor": "braf",
    "MEK inhibitor": "mek",
    "anti-PD-1": "pd1",
    "anti-CTLA-4": "ctla4",
    "anti-LAG-3": "lag3",
}
ROUTE = {
    "sql": "Consultó la base de datos (recuento exacto)",
    "search": "Buscó en los textos de ensayos, artículos y fichas",
    "both": "Consultó la base de datos y buscó en los textos",
}


def num(n: int) -> str:
    """3782 -> '3 782' (separador de miles con espacio, como en el resto del proyecto)."""
    return f"{n:,}".replace(",", "\u202f")  # espacio fino que no se parte en dos líneas


def esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def styled(chart: alt.Chart, height: int = 320) -> alt.Chart:
    return (
        chart.properties(height=height, background=T["surface"])
        .configure_view(stroke=None)
        .configure_axis(
            gridColor=T["line"],
            domainColor=T["line"],
            tickColor=T["line"],
            labelColor=T["muted"],
            titleColor=T["muted"],
            labelFont="Host Grotesk",
            titleFont="Host Grotesk",
            labelFontSize=13,
            titleFontWeight=500,
        )
        .configure_legend(
            labelColor=T["muted"],
            titleColor=T["muted"],
            orient="bottom",
            columns=3,  # dos filas: con una sola se cortaba «anti-CTLA-4» y faltaba «anti-LAG-3»
            labelLimit=0,
            labelFont="Host Grotesk",
        )
        .configure_text(font="Host Grotesk")
    )


# ---------------------------------------------------------------- acceso a la API
@st.cache_data(ttl=300, show_spinner=False)
def get(path: str, **params):
    r = httpx.get(
        f"{API}{path}", params={k: v for k, v in params.items() if v}, timeout=60
    )
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict, timeout: int = 180):
    r = httpx.post(f"{API}{path}", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def source_html(s: dict, score: float | None = None) -> str:
    ident = s.get("doc_id", "")
    meta = " · ".join(
        x
        for x in (
            ident if s["source"] in ("trial", "publication") else None,
            str(s["year"]) if s.get("year") else None,
            f"p. {s['page']}" if s.get("page") else None,
            f"relevancia {score:.2f}" if score is not None else None,
        )
        if x
    )
    ref = f'<span class="ref">[{esc(s["ref"])}]</span>' if s.get("ref") else ""
    return (
        f'<div class="src s-{esc(s["source"])}"><div class="top">{ref}'
        f'<span class="kind">{esc(SOURCE_KIND.get(s["source"], s["source"]))}</span></div>'
        f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a>'
        f'<div class="meta">{esc(meta)}</div><div class="snip">{esc(s["text"][:500])}</div></div>'
    )


def chips(items: list[tuple[str, str]]) -> str:
    return (
        '<div class="chips">'
        + "".join(f'<span class="chip {k}">{esc(t)}</span>' for k, t in items)
        + "</div>"
    )


# ---------------------------------------------------------------- comprobación de la API
try:
    health = get("/health")
except Exception:  # noqa: BLE001
    st.error(
        f"La interfaz no encuentra la API en {API}. Ábrela en otra terminal con `make api` "
        "(o `uv run uvicorn onco_research_ai.api.main:app --port 8000`) y recarga esta página."
    )
    st.stop()
pg = health["postgres"]
DRUGS = get("/drugs")

# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown(
        '<div class="side-title"><i></i>OncoResearchAI</div>', unsafe_allow_html=True
    )
    st.caption("Inteligencia competitiva en melanoma a partir de datos públicos.")
    st.markdown(
        f"""<div class="side-stats">
<b>{num(pg["trials"])}</b> ensayos clínicos (ClinicalTrials.gov)<br>
<b>{num(pg["publications"])}</b> artículos científicos (Europe PMC)<br>
<b>{pg["labels"]}</b> fichas técnicas (FDA)</div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="side-eyebrow">Fármacos seguidos</div>', unsafe_allow_html=True
    )
    by_mech: dict[str, list[str]] = {}
    for d in DRUGS:
        by_mech.setdefault(d["mechanism"], []).append(d["name"])
    for mech in MECHANISMS:
        if mech in by_mech:
            st.markdown(
                f'<div class="side-eyebrow" style="margin-top:.6rem">{esc(mech)}</div>'
                + chips([(MECH_CLASS[mech], n) for n in by_mech[mech]]),
                unsafe_allow_html=True,
            )
    st.caption(
        "Las preguntas sobre otros fármacos solo se responden con lo que digan los textos."
    )

tab_ask, tab_land, tab_drug, tab_search = st.tabs(
    [
        ":material/forum: Preguntar",
        ":material/monitoring: Panorama competitivo",
        ":material/medication: Perfil de fármaco",
        ":material/search: Buscar documentos",
    ]
)

# ---------------------------------------------------------------- 1. preguntar
EXAMPLES = {
    "Datos exactos": (
        "Recuentos y listas: el asistente escribe una consulta a la base de datos.",
        [
            "¿Cuántos ensayos de fase 3 hay con inhibidores de BRAF, por fármaco y estado?",
            "¿Qué ensayos de fase 3 ha patrocinado Pierre Fabre y en qué estado están?",
        ],
    ),
    "Contenido de los documentos": (
        "Resultados, seguridad, mecanismos: el asistente lee ensayos, artículos y fichas.",
        [
            "¿Qué reacciones adversas describe la ficha técnica de Braftovi?",
            "What are the main resistance mechanisms to BRAF inhibitors?",
        ],
    ),
    "Las dos cosas": (
        "Una lista de ensayos más lo que dicen sus documentos.",
        ["¿Qué ensayos de fase 3 con encorafenib están activos y qué comparan?"],
    ),
}

with tab_ask:
    st.session_state.setdefault("history", [])
    st.markdown(
        f"""<div class="hero"><div class="eyebrow">Asistente</div>
<h1>Pregunta sobre el panorama del melanoma</h1>
<p>Escribe una pregunta en español o en inglés. El asistente busca en {num(pg["trials"])} ensayos,
{num(pg["publications"])} artículos y {pg["labels"]} fichas técnicas, y responde citando de dónde sale
cada dato.</p></div>
<div class="expect">
<div><b>Tarda de 3 a 20 segundos</b><span>La primera pregunta tarda más porque carga los modelos.</span></div>
<div><b>Cada dato lleva su fuente</b><span>[S1], [S2]… son documentos que puedes abrir; [SQL] es un
recuento exacto de la base de datos.</span></div>
<div><b>La respuesta se verifica sola</b><span>Una etiqueta indica si todas las citas y cifras están
respaldadas, o qué conviene revisar.</span></div>
</div>""",
        unsafe_allow_html=True,
    )

    question = st.chat_input(
        "Escribe tu pregunta, por ejemplo: ¿qué ensayos de relatlimab están activos?"
    )
    clicked = None
    if not st.session_state.history:  # estado vacío: enseñar qué se puede preguntar
        cols = st.columns(3, gap="large")
        for col, (group, (hint, qs)) in zip(cols, EXAMPLES.items(), strict=True):
            with col:
                st.markdown(
                    f'<div class="g{list(EXAMPLES).index(group) + 1}"><div class="group-label">'
                    f'{esc(group)}</div><div class="group-hint">{esc(hint)}</div></div>',
                    unsafe_allow_html=True,
                )
                for q in qs:
                    if st.button(q, key=f"ex-{q}", width="stretch"):
                        clicked = q
    question = question or clicked

    if question:
        with st.status("Trabajando en tu pregunta…", expanded=True) as status:
            st.write(
                "Decidiendo si hace falta un recuento, una búsqueda en textos o ambas cosas."
            )
            st.write("Buscando y consultando; después redacta y verifica cada cita.")
            try:
                res = post("/ask", {"question": question})
                st.session_state.history.insert(0, res)
                status.update(
                    label=f"Listo en {res['timings']['total']:.0f} s",
                    state="complete",
                    expanded=False,
                )
                st.rerun()  # vuelve a dibujar sin los ejemplos y con la respuesta arriba
            except Exception as exc:  # noqa: BLE001
                status.update(label="No se pudo responder", state="error")
                st.error(
                    f"El asistente falló ({exc}). Si dice 429, se agotó la cuota por minuto de Groq: "
                    "espera un minuto y vuelve a intentarlo."
                )

    for i, res in enumerate(st.session_state.history):
        if i:
            st.divider()
        st.markdown(
            f'<div class="question">{esc(res["question"])}</div>',
            unsafe_allow_html=True,
        )
        c = res["check"]
        badges = [("accent", ROUTE[res["route"]])]
        if c.get("invalid"):
            badges.append(
                ("warn", "Cita a una fuente inexistente: " + ", ".join(c["invalid"]))
            )
        if c.get("unsupported_numbers"):
            badges.append(
                ("warn", "Cifras sin respaldo: " + ", ".join(c["unsupported_numbers"]))
            )
        if c.get("uncited_sentences"):
            badges.append(("warn", f"{len(c['uncited_sentences'])} frase(s) sin cita"))
        if len(badges) == 1:
            badges.append(("ok", "Citas y cifras verificadas"))
        st.markdown(chips(badges), unsafe_allow_html=True)

        left, right = st.columns([3, 2], gap="large")
        with left:
            st.markdown(res["answer"])
            t = res["timings"]
            steps = [f"<b>Planificar</b> {t.get('plan', 0):.1f} s"]
            if "sql" in t:
                steps.append(f"<b>Base de datos</b> {t['sql']:.1f} s")
            if "search" in t:
                steps.append(f"<b>Búsqueda</b> {t['search']:.1f} s")
            steps.append(f"<b>Redactar</b> {t.get('generate', 0):.1f} s")
            extra = (
                " · reescrita tras la verificación"
                if res.get("attempts", 1) > 1
                else ""
            )
            st.markdown(
                f'<div class="steps">{" → ".join(steps)} · total {t["total"]:.1f} s{extra}</div>',
                unsafe_allow_html=True,
            )
            if res.get("sql") and res["sql"].get("sql"):
                with st.expander("Ver la consulta [SQL] y sus filas"):
                    st.code(res["sql"]["sql"], language="sql")
                    if res["sql"]["rows"]:
                        st.dataframe(
                            pd.DataFrame(
                                res["sql"]["rows"], columns=res["sql"]["columns"]
                            ),
                            hide_index=True,
                        )
        with right:
            cited = res["cited_sources"]
            st.markdown(
                f'<div class="eyebrow">Fuentes citadas · {len(cited)}</div>',
                unsafe_allow_html=True,
            )
            if cited:
                st.markdown(
                    "".join(source_html(s) for s in cited), unsafe_allow_html=True
                )
            elif res.get("sql"):
                st.caption(
                    "La respuesta sale de la base de datos: abre «Ver la consulta [SQL]»."
                )
            else:
                st.caption("No encontró documentos que respondan a la pregunta.")
            others = [s for s in res["sources"] if s not in cited]
            if others:
                with st.expander(f"Otros {len(others)} documentos consultados"):
                    st.markdown(
                        "".join(source_html(s) for s in others), unsafe_allow_html=True
                    )

# ---------------------------------------------------------------- 2. panorama
with tab_land:
    land = get("/landscape")
    active = pd.DataFrame(land["active_by_drug"])
    tot = land["totals"]
    st.markdown(
        '<div class="hero"><div class="eyebrow">Panorama competitivo</div>'
        "<h1>Quién está haciendo qué en melanoma</h1>"
        "<p>Ensayos clínicos que usan alguno de los 10 fármacos seguidos. Un ensayo está "
        "<b>activo</b> si recluta o está en curso.</p></div>",
        unsafe_allow_html=True,
    )
    m = st.columns(4)
    m[0].metric("Ensayos con estos fármacos", tot["n_trials"])
    m[1].metric("Activos hoy", tot["n_active"])
    m[2].metric("Activos con inmunoterapia", tot["n_active_io"])
    m[3].metric("Activos con terapia dirigida", tot["n_active_targeted"])

    top = active.sort_values("n_active", ascending=False).iloc[0]
    sp = pd.DataFrame(land["top_industry_sponsors"])
    pf = sp[sp["sponsor"].str.contains("Pierre Fabre", case=False)]
    targeted = active[active["mechanism"].str.contains("inhibitor")].sort_values(
        "n_active", ascending=False
    )
    lines = [
        (
            f"La inmunoterapia está en {tot['n_active_io']} de los {tot['n_active']} ensayos activos; "
            f"la terapia dirigida (BRAF/MEK), en {tot['n_active_targeted']} (algunos combinan las dos)."
        ),
        f"{top['drug'].capitalize()} es el fármaco con más ensayos activos ({top['n_active']}).",
        "Entre los BRAF/MEK, "
        + ", ".join(f"{r.drug} ({r.n_active})" for r in targeted.head(3).itertuples())
        + ".",
    ]
    if not pf.empty:
        lines.append(
            f"Pierre Fabre patrocina {int(pf['n'].iloc[0])} ensayos con estos fármacos."
        )
    st.markdown(
        '<ul class="takeaways">'
        + "".join(f"<li>{esc(x)}</li>" for x in lines)
        + "</ul>",
        unsafe_allow_html=True,
    )
    st.caption(
        "En los gráficos por fármaco, un ensayo que combina dos fármacos aparece en ambos, y se "
        "cuentan también los fármacos usados como comparador."
    )

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Ensayos activos por fármaco**")
        order = active.sort_values("n_active", ascending=False)["drug"].tolist()
        base = alt.Chart(active).encode(
            y=alt.Y("drug:N", sort=order, title=None),
            x=alt.X("n_active:Q", title="Ensayos activos"),
            tooltip=[
                alt.Tooltip("drug", title="Fármaco"),
                alt.Tooltip("mechanism", title="Mecanismo"),
                alt.Tooltip("n_active", title="Activos"),
                alt.Tooltip("n_total", title="Total"),
            ],
        )
        bars = base.mark_bar(cornerRadiusEnd=4, size=16).encode(
            color=alt.Color("mechanism:N", scale=MECH_SCALE, title="Mecanismo")
        )
        labels = base.mark_text(align="left", dx=4, color=T["ink"]).encode(
            text="n_active:Q"
        )
        st.altair_chart(styled(bars + labels), width="stretch", theme=None)
    with right:
        st.markdown("**Ensayos por fármaco y fase**")
        ph = pd.DataFrame(land["by_phase"])
        phase_order = [
            "EARLY_PHASE1",
            "PHASE1",
            "PHASE2",
            "PHASE3",
            "PHASE4",
            "NA",
            "NO_PHASE",
        ]
        ph["fase"] = ph["phase"].map(
            {
                "EARLY_PHASE1": "Fase 0-1",
                "PHASE1": "Fase 1",
                "PHASE2": "Fase 2",
                "PHASE3": "Fase 3",
                "PHASE4": "Fase 4",
                "NA": "N/A",
                "NO_PHASE": "Sin fase",
            }
        )
        fase_order = [
            "Fase 0-1",
            "Fase 1",
            "Fase 2",
            "Fase 3",
            "Fase 4",
            "N/A",
            "Sin fase",
        ]
        heat = alt.Chart(ph).encode(
            x=alt.X("fase:N", sort=fase_order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("drug:N", title=None),
            tooltip=[
                alt.Tooltip("drug", title="Fármaco"),
                alt.Tooltip("fase", title="Fase"),
                alt.Tooltip("n", title="Ensayos"),
            ],
        )
        cells = heat.mark_rect(
            cornerRadius=3, stroke=T["surface"], strokeWidth=2
        ).encode(color=alt.Color("n:Q", scale=alt.Scale(range=SEQ), title="Ensayos"))
        text = heat.mark_text(fontSize=11).encode(
            text="n:Q",
            color=alt.condition(
                alt.datum.n > ph["n"].max() * 0.5,
                alt.value("#ffffff"),
                alt.value(T["ink"]),
            ),
        )
        st.altair_chart(styled(cells + text), width="stretch", theme=None)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Ensayos iniciados por año y mecanismo**")
        yr = pd.DataFrame(land["by_start_year"])
        yr["mechanism"] = yr["drug"].map(
            dict(zip(active["drug"], active["mechanism"], strict=True))
        )
        yr = yr[(yr["year"] >= 2008) & (yr["year"] <= pd.Timestamp.now().year)]
        yr = yr.groupby(["year", "mechanism"], as_index=False)["n"].sum()
        hover = alt.selection_point(
            fields=["year"], nearest=True, on="pointerover", empty=False
        )
        lines_c = (
            alt.Chart(yr)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X(
                    "year:O",
                    title=None,
                    axis=alt.Axis(labelAngle=0, values=list(range(2008, 2027, 3))),
                ),
                y=alt.Y("n:Q", title="Ensayos iniciados"),
                color=alt.Color("mechanism:N", scale=MECH_SCALE, title="Mecanismo"),
            )
        )
        points = (
            lines_c.mark_point(size=60, filled=True)
            .encode(
                opacity=alt.condition(hover, alt.value(1), alt.value(0)),
                tooltip=[
                    alt.Tooltip("year", title="Año"),
                    alt.Tooltip("mechanism", title="Mecanismo"),
                    alt.Tooltip("n", title="Ensayos"),
                ],
            )
            .add_params(hover)
        )
        rule = (
            alt.Chart(yr)
            .mark_rule(color=T["muted"])
            .encode(x="year:O")
            .transform_filter(hover)
        )
        st.altair_chart(styled(lines_c + points + rule), width="stretch", theme=None)
        st.caption("El año en curso está incompleto.")
    with right:
        st.markdown("**Laboratorios con más ensayos**")
        sp["destacado"] = sp["sponsor"].str.contains("Pierre Fabre", case=False)
        b = alt.Chart(sp).encode(
            y=alt.Y("sponsor:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            x=alt.X("n:Q", title="Ensayos"),
            tooltip=[
                alt.Tooltip("sponsor", title="Laboratorio"),
                alt.Tooltip("n", title="Ensayos"),
            ],
        )
        chart = b.mark_bar(cornerRadiusEnd=4, size=14).encode(
            color=alt.condition(
                alt.datum.destacado, alt.value(T["accent"]), alt.value(T["muted"])
            )
        ) + b.mark_text(align="left", dx=4, color=T["ink"]).encode(text="n:Q")
        st.altair_chart(styled(chart), width="stretch", theme=None)
        st.caption("Pierre Fabre resaltado. Solo patrocinadores de la industria.")

    with st.expander("Ver los datos en tabla"):
        st.dataframe(
            active.rename(
                columns={
                    "drug": "Fármaco",
                    "mechanism": "Mecanismo",
                    "n_total": "Ensayos",
                    "n_active": "Activos",
                }
            ),
            hide_index=True,
        )
        st.dataframe(
            ph.pivot_table(index="drug", columns="fase", values="n", fill_value=0),
            width="stretch",
        )

# ---------------------------------------------------------------- 3. perfil de fármaco
with tab_drug:
    names = [d["name"] for d in DRUGS]
    st.markdown(
        '<div class="hero"><div class="eyebrow">Perfil de fármaco</div>'
        "<h1>Todo lo que hay sobre un fármaco</h1>"
        "<p>Sus ensayos, los artículos que tratan de él y su ficha técnica de la FDA.</p></div>",
        unsafe_allow_html=True,
    )
    choice = st.selectbox(
        "Fármaco",
        names,
        index=names.index("encorafenib") if "encorafenib" in names else 0,
        key="drug-choice",
    )
    p = get(f"/drugs/{choice}")
    st.markdown(
        f"### {esc(p['name'].capitalize())}"
        + chips(
            [("accent", p["mechanism"])]
            + [("", f"También: {s}") for s in p["synonyms"]]
        ),
        unsafe_allow_html=True,
    )
    m = st.columns(4)
    m[0].metric("Ensayos", p["n_trials"])
    m[1].metric("Artículos que lo mencionan", p["n_publications"]["n"])
    m[2].metric(
        "Artículos centrados en él",
        p["n_publications"]["n_about"],
        help="El fármaco aparece en el título.",
    )
    m[3].metric("Fichas FDA", len(p["fda_labels"]))
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Ensayos por fase**")
        dfp = pd.DataFrame(p["trials_by_phase"])
        b = alt.Chart(dfp).encode(
            x=alt.X("phase:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("n:Q", title="Ensayos"),
            tooltip=[
                alt.Tooltip("phase", title="Fase"),
                alt.Tooltip("n", title="Ensayos"),
            ],
        )
        color = (
            PALETTE[MECHANISMS.index(p["mechanism"])]
            if p["mechanism"] in MECHANISMS
            else T["accent"]
        )
        st.altair_chart(
            styled(
                b.mark_bar(cornerRadiusEnd=4, size=28, color=color)
                + b.mark_text(dy=-8, color=T["ink"]).encode(text="n:Q"),
                260,
            ),
            width="stretch",
            theme=None,
        )
    with right:
        st.markdown("**Estado de los ensayos**")
        st.dataframe(
            pd.DataFrame(p["trials_by_status"]).rename(
                columns={"status": "Estado", "n": "Ensayos"}
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Principales patrocinadores**")
        st.dataframe(
            pd.DataFrame(p["top_sponsors"]).rename(
                columns={
                    "sponsor": "Patrocinador",
                    "sponsor_class": "Tipo",
                    "n": "Ensayos",
                }
            ),
            hide_index=True,
            width="stretch",
        )
    st.markdown("**Ensayos más recientes**")
    rt = pd.DataFrame(p["recent_trials"])
    if not rt.empty:
        rt["phases"] = rt["phases"].apply(lambda x: ", ".join(x) if x else "—")
        rt["drugs"] = rt["drugs"].apply(", ".join)
        st.dataframe(
            rt[
                [
                    "nct_id",
                    "brief_title",
                    "phases",
                    "overall_status",
                    "sponsor_name",
                    "start_date",
                    "drugs",
                    "url",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "nct_id": "NCT",
                "brief_title": "Título",
                "phases": "Fase",
                "overall_status": "Estado",
                "sponsor_name": "Patrocinador",
                "start_date": "Inicio",
                "drugs": "Fármacos",
                "url": st.column_config.LinkColumn("Enlace", display_text="abrir"),
            },
        )
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Artículos más citados sobre él**")
        for a in p["top_publications"]:
            st.markdown(
                f"- [{a['title']}]({a['url']}) · *{a['journal']}*, {a['pub_year']} · {a['cited_by_count']} citas"
            )
    with right:
        st.markdown("**Fichas técnicas FDA**")
        for lab in p["fda_labels"]:
            st.markdown(
                f"- [{lab['brand_name'] or lab['generic_name']}]({lab['url']}) · "
                f"{lab['manufacturer'] or ''} ({lab['effective_date']})"
            )
        if not p["fda_labels"]:
            st.caption("Sin ficha FDA enlazada.")

# ---------------------------------------------------------------- 4. buscar documentos
with tab_search:
    st.markdown(
        '<div class="hero"><div class="eyebrow">Buscar documentos</div>'
        "<h1>Encuentra los documentos sin pasar por el asistente</h1>"
        "<p>Devuelve los fragmentos más relevantes, sin redactar una respuesta. Funciona mejor en "
        "inglés, porque los documentos están en inglés.</p></div>",
        unsafe_allow_html=True,
    )
    f = st.columns([4, 1, 1, 1])
    q = f[0].text_input(
        "Qué buscas", "adverse events of encorafenib plus binimetinib", key="search-q"
    )
    src = f[1].selectbox(
        "Tipo",
        ["Todos", "trial", "publication", "label", "congress"],
        key="search-src",
        format_func=lambda x: SOURCE_KIND.get(x, x),
    )
    drug = f[2].selectbox("Fármaco", ["Todos", *names], key="search-drug")
    phase = f[3].selectbox(
        "Fase",
        ["Todas", "PHASE1", "PHASE2", "PHASE3", "PHASE4"],
        key="search-phase",
        format_func=lambda x: x.replace("PHASE", "Fase "),
    )
    if q:
        body = {
            "query": q,
            "k": 8,
            "source": None if src == "Todos" else src,
            "drug": None if drug == "Todos" else drug,
            "phase": None if phase == "Todas" else phase,
        }
        with st.spinner("Buscando…"):
            hits = post("/search", body, timeout=120)
        if not hits:
            st.info("Ningún documento cumple esos filtros. Prueba a quitar alguno.")
        cols = st.columns(2, gap="medium")
        for i, h in enumerate(hits):
            cols[i % 2].markdown(
                source_html(h, score=h["score"]), unsafe_allow_html=True
            )
