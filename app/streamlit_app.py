"""Interfaz de OncoResearchAI (Streamlit). Consume la API REST: no toca la base de datos.

uv run streamlit run app/streamlit_app.py      (con la API corriendo en el puerto 8000)
"""

import os

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="OncoResearchAI", page_icon="🔬", layout="wide")

# ---------------------------------------------------------------- estilo de los gráficos
# Paleta categórica validada (orden fijo: el color sigue al mecanismo, nunca al ranking).
MECHANISMS = [
    "BRAF inhibitor",
    "MEK inhibitor",
    "anti-PD-1",
    "anti-CTLA-4",
    "anti-LAG-3",
]
DARK = st.context.theme.type == "dark"
PALETTE = (
    ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
    if DARK
    else ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
)
INK = {
    "surface": "#1a1a19" if DARK else "#fcfcfb",
    "primary": "#f0efec" if DARK else "#0b0b0b",
    "secondary": "#c3c2b7" if DARK else "#52514e",
    "muted": "#898781",
    "grid": "#2c2c2a" if DARK else "#e1e0d9",
    "axis": "#383835" if DARK else "#c3c2b7",
}
SEQ = ["#184f95", "#3987e5", "#86b6ef"] if DARK else ["#cde2fb", "#6da7ec", "#1c5cab"]
MECH_SCALE = alt.Scale(domain=MECHANISMS, range=PALETTE)
SOURCE_LABEL = {
    "trial": "🧪 Ensayo clínico",
    "publication": "📄 Artículo",
    "label": "💊 Ficha FDA",
    "congress": "🎤 Congreso (PDF)",
}


def styled(chart: alt.Chart, height: int = 320) -> alt.Chart:
    return (
        chart.properties(height=height, background=INK["surface"])
        .configure_view(stroke=None)
        .configure_axis(
            gridColor=INK["grid"],
            domainColor=INK["axis"],
            tickColor=INK["axis"],
            labelColor=INK["secondary"],
            titleColor=INK["secondary"],
            labelFontSize=12,
        )
        .configure_legend(
            labelColor=INK["secondary"], titleColor=INK["secondary"], orient="top"
        )
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


def source_card(s: dict, score: float | None = None) -> None:
    head = f"**[{s['ref']}]** " if s.get("ref") else ""
    meta = " · ".join(
        str(x)
        for x in (
            SOURCE_LABEL.get(s["source"], s["source"]),
            s.get("year"),
            f"p. {s['page']}" if s.get("page") else None,
        )
        if x
    )
    with st.container(border=True):
        st.markdown(f"{head}[{s['title']}]({s['url']})")
        st.caption(meta + (f" · relevancia {score:.2f}" if score is not None else ""))
        st.markdown(f"<small>{s['text'][:420]}…</small>", unsafe_allow_html=True)


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.title("🔬 OncoResearchAI")
    st.caption(
        "Veille concurrentielle en melanoma: ensayos clínicos, literatura y fichas FDA, "
        "con un agente que responde citando sus fuentes."
    )
    try:
        h = get("/health")
        pg = h["postgres"]
        st.success(
            f"API conectada · {pg['trials']:,} ensayos · {pg['publications']:,} artículos · "
            f"{pg['labels']} fichas".replace(",", " ")
        )
    except Exception:  # noqa: BLE001
        st.error(
            f"No hay conexión con la API en {API}. Arráncala con:\n\n"
            "`uv run uvicorn onco_research_ai.api.main:app --port 8000`"
        )
        st.stop()
    st.markdown("**Fármacos seguidos**")
    for d in get("/drugs"):
        st.caption(f"{d['name']} — {d['mechanism']}")

tab_chat, tab_land, tab_drug, tab_search = st.tabs(
    ["💬 Asistente", "📊 Panorama competitivo", "💊 Perfil de fármaco", "🔎 Búsqueda"]
)

# ---------------------------------------------------------------- 1. asistente
with tab_chat:
    st.subheader("Pregunta al asistente")
    st.caption(
        "Responde solo con las fuentes que encuentra y cita cada afirmación: [S1] documento, "
        "[SQL] consulta a la base de datos. Funciona en español o inglés."
    )
    examples = [
        "¿Qué ensayos de fase 3 con encorafenib están activos y qué comparan?",
        "¿Cuántos ensayos de fase 3 hay con inhibidores de BRAF, por fármaco y estado?",
        "What are the main resistance mechanisms to BRAF inhibitors?",
        "¿Qué reacciones adversas describe la ficha FDA de Braftovi?",
    ]
    cols = st.columns(len(examples))
    clicked = next(
        (
            q
            for c, q in zip(cols, examples, strict=True)
            if c.button(q, width="stretch")
        ),
        None,
    )
    st.session_state.setdefault("history", [])
    question = st.chat_input("Escribe tu pregunta…") or clicked

    if question:
        with st.spinner("Buscando, consultando y redactando con citas…"):
            try:
                st.session_state.history.insert(0, post("/ask", {"question": question}))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error del agente: {exc}")

    for res in st.session_state.history:
        with st.chat_message("user"):
            st.write(res["question"])
        with st.chat_message("assistant"):
            st.markdown(res["answer"])
            c = res["check"]
            problems = []
            if c.get("invalid"):
                problems.append(f"citas inexistentes: {', '.join(c['invalid'])}")
            if c.get("unsupported_numbers"):
                problems.append(
                    f"números sin respaldo: {', '.join(c['unsupported_numbers'])}"
                )
            if c.get("uncited_sentences"):
                problems.append(f"{len(c['uncited_sentences'])} frase(s) sin cita")
            route = {
                "sql": "base de datos",
                "search": "búsqueda",
                "both": "base de datos + búsqueda",
            }
            st.caption(
                (
                    "✅ Citas verificadas"
                    if not problems
                    else "⚠️ Revisar: " + "; ".join(problems)
                )
                + f" · ruta: {route[res['route']]} · {res['timings']['total']:.1f} s"
            )
            if res.get("sql") and res["sql"].get("sql"):
                with st.expander("Consulta SQL usada [SQL]"):
                    st.code(res["sql"]["sql"], language="sql")
                    if res["sql"]["rows"]:
                        st.dataframe(
                            pd.DataFrame(
                                res["sql"]["rows"], columns=res["sql"]["columns"]
                            ),
                            hide_index=True,
                        )
            if res["cited_sources"]:
                with st.expander(
                    f"Fuentes citadas ({len(res['cited_sources'])})", expanded=True
                ):
                    for s in res["cited_sources"]:
                        source_card(s)

# ---------------------------------------------------------------- 2. panorama
with tab_land:
    land = get("/landscape")
    active = pd.DataFrame(land["active_by_drug"])
    st.subheader("Panorama competitivo en melanoma")
    tot = land["totals"]  # ensayos DISTINTOS, calculados en SQL
    m = st.columns(4)
    m[0].metric("Ensayos con fármacos seguidos", tot["n_trials"])
    m[1].metric("…de ellos activos", tot["n_active"])
    m[2].metric("Activos con inmunoterapia", tot["n_active_io"])
    m[3].metric("Activos con terapia dirigida", tot["n_active_targeted"])
    st.caption(
        "Cifras de ensayos distintos. En los gráficos por fármaco, un ensayo que combina dos "
        "fármacos aparece en ambos. Incluye fármacos usados como comparador."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Ensayos activos por fármaco** (reclutando o en curso)")
        base = alt.Chart(active).encode(
            y=alt.Y(
                "drug:N",
                sort=active.sort_values("n_active", ascending=False)["drug"].tolist(),
                title=None,
            ),
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
        labels = base.mark_text(align="left", dx=4, color=INK["primary"]).encode(
            text="n_active:Q"
        )
        st.altair_chart(styled(bars + labels), width="stretch", theme=None)
    with right:
        st.markdown("**Ensayos por fármaco y fase**")
        ph = pd.DataFrame(land["by_phase"])
        order = [
            "EARLY_PHASE1",
            "PHASE1",
            "PHASE2",
            "PHASE3",
            "PHASE4",
            "NA",
            "NO_PHASE",
        ]
        heat = alt.Chart(ph).encode(
            x=alt.X(
                "phase:N",
                sort=order,
                title=None,
                axis=alt.Axis(labelAngle=0, labelFontSize=10),
            ),
            y=alt.Y("drug:N", title=None),
            tooltip=[
                alt.Tooltip("drug", title="Fármaco"),
                alt.Tooltip("phase", title="Fase"),
                alt.Tooltip("n", title="Ensayos"),
            ],
        )
        cells = heat.mark_rect(
            cornerRadius=3, stroke=INK["surface"], strokeWidth=2
        ).encode(color=alt.Color("n:Q", scale=alt.Scale(range=SEQ), title="Ensayos"))
        text = heat.mark_text(fontSize=11).encode(
            text="n:Q",
            color=alt.condition(
                alt.datum.n > ph["n"].max() * 0.55,
                alt.value("#ffffff"),
                alt.value(INK["primary"]),
            ),
        )
        st.altair_chart(styled(cells + text), width="stretch", theme=None)

    left, right = st.columns(2)
    with left:
        st.markdown("**Ensayos iniciados por año y mecanismo**")
        yr = pd.DataFrame(land["by_start_year"])
        mech_of = dict(zip(active["drug"], active["mechanism"], strict=True))
        yr["mechanism"] = yr["drug"].map(mech_of)
        yr = yr[(yr["year"] >= 2008) & (yr["year"] <= pd.Timestamp.now().year)]
        yr = yr.groupby(["year", "mechanism"], as_index=False)["n"].sum()
        hover = alt.selection_point(
            fields=["year"], nearest=True, on="pointerover", empty=False
        )
        lines = (
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
            lines.mark_point(size=60, filled=True)
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
            .mark_rule(color=INK["muted"])
            .encode(x="year:O")
            .transform_filter(hover)
        )
        st.altair_chart(styled(lines + points + rule), width="stretch", theme=None)
        st.caption("El último año está incompleto.")
    with right:
        st.markdown("**Principales patrocinadores de la industria**")
        sp = pd.DataFrame(land["top_industry_sponsors"])
        b = alt.Chart(sp).encode(
            y=alt.Y("sponsor:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            x=alt.X("n:Q", title="Ensayos"),
            tooltip=[
                alt.Tooltip("sponsor", title="Patrocinador"),
                alt.Tooltip("n", title="Ensayos"),
            ],
        )
        chart = b.mark_bar(cornerRadiusEnd=4, size=14, color=PALETTE[0]) + b.mark_text(
            align="left", dx=4, color=INK["primary"]
        ).encode(text="n:Q")
        st.altair_chart(styled(chart), width="stretch", theme=None)

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
            ph.pivot_table(index="drug", columns="phase", values="n", fill_value=0),
            width="stretch",
        )

# ---------------------------------------------------------------- 3. perfil de fármaco
with tab_drug:
    names = [d["name"] for d in get("/drugs")]
    choice = st.selectbox(
        "Fármaco (también acepta marca o código en la API)",
        names,
        index=names.index("encorafenib") if "encorafenib" in names else 0,
    )
    p = get(f"/drugs/{choice}")
    st.subheader(f"{p['name']} · {p['mechanism']}")
    st.caption("Otros nombres: " + ", ".join(p["synonyms"]))
    m = st.columns(4)
    m[0].metric("Ensayos", p["n_trials"])
    m[1].metric("Artículos que lo mencionan", p["n_publications"]["n"])
    m[2].metric("…centrados en él (título)", p["n_publications"]["n_about"])
    m[3].metric("Fichas FDA", len(p["fda_labels"]))
    left, right = st.columns(2)
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
            else PALETTE[0]
        )
        st.altair_chart(
            styled(
                b.mark_bar(cornerRadiusEnd=4, size=28, color=color)
                + b.mark_text(dy=-8, color=INK["primary"]).encode(text="n:Q"),
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
                "url": st.column_config.LinkColumn("Enlace", display_text="abrir")
            },
        )
    left, right = st.columns(2)
    with left:
        st.markdown("**Artículos más citados sobre él**")
        for a in p["top_publications"]:
            st.markdown(
                f"- [{a['title']}]({a['url']}) — *{a['journal']}*, {a['pub_year']} · {a['cited_by_count']} citas"
            )
    with right:
        st.markdown("**Fichas técnicas FDA**")
        for lab in p["fda_labels"]:
            st.markdown(
                f"- [{lab['brand_name'] or lab['generic_name']}]({lab['url']}) — {lab['manufacturer'] or ''} "
                f"({lab['effective_date']})"
            )
        if not p["fda_labels"]:
            st.caption("Sin ficha FDA enlazada.")

# ---------------------------------------------------------------- 4. búsqueda
with tab_search:
    st.subheader("Búsqueda de evidencia")
    st.caption(
        "Búsqueda híbrida: palabras exactas (BM25) + significado (embeddings) + reordenación "
        "(cross-encoder). Mejor en inglés."
    )
    f = st.columns([4, 1, 1, 1])
    q = f[0].text_input("Consulta", "adverse events of encorafenib plus binimetinib")
    src = f[1].selectbox(
        "Fuente", ["(todas)", "trial", "publication", "label", "congress"]
    )
    drug = f[2].selectbox("Fármaco", ["(todos)", *names])
    phase = f[3].selectbox("Fase", ["(todas)", "PHASE1", "PHASE2", "PHASE3", "PHASE4"])
    if q:
        body = {
            "query": q,
            "k": 8,
            "source": None if src.startswith("(") else src,
            "drug": None if drug.startswith("(") else drug,
            "phase": None if phase.startswith("(") else phase,
        }
        with st.spinner("Buscando…"):
            hits = post("/search", body, timeout=120)
        if not hits:
            st.info("Sin resultados con esos filtros.")
        for h in hits:
            source_card(h, score=h["score"])
