import streamlit as st
import pandas as pd
import json
import os
import hashlib
from datetime import datetime, date
from supabase import create_client, Client
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
import calendar
import plotly.express as px
import plotly.graph_objects as go

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Finanzas Personales",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
SUPABASE_URL   = os.getenv("SUPABASE_URL")   or st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")   or st.secrets.get("SUPABASE_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY") or st.secrets.get("GROK_API_KEY", "")

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def build_financial_context(data, mes, ingreso, total_gastado,
                             presupuesto_reajustado, dia_actual,
                             total_dias, dias_restantes, ahorro_proyectado):
    gastos_mes = [g for g in data["gastos"] if g["fecha"].startswith(mes)]
    cat_totals = {}
    for g in gastos_mes:
        cat_totals[g["categoria"]] = cat_totals.get(g["categoria"], 0) + float(g["monto"])
    cat_str = "\n".join([
        f"  - {k}: ${v:,.0f}" for k, v in sorted(cat_totals.items(), key=lambda x: -x[1])
    ])
    last5 = sorted(gastos_mes, key=lambda x: x["fecha"], reverse=True)[:5]
    last5_str = "\n".join([
        f"  - {g['fecha']} | {g['categoria']} | ${float(g['monto']):,.0f} | {g.get('descripcion','')}"
        for g in last5
    ])
    fijos_str = "\n".join([
        f"  - {f['nombre']}: ${float(f['monto']):,.0f}"
        for f in data.get("gastos_fijos", [])
    ])
    pct = (total_gastado / ingreso * 100) if ingreso > 0 else 0
    return (
        "Sos un asesor financiero personal amigable y directo. "
        "Respondé siempre en español argentino, de forma concisa y práctica. "
        "No uses lenguaje técnico complejo.\n\n"
        f"DATOS FINANCIEROS DEL USUARIO - {mes}:\n"
        f"- Ingreso mensual: ${ingreso:,.0f}\n"
        f"- Dia actual: {dia_actual} de {total_dias}\n"
        f"- Dias restantes: {dias_restantes}\n"
        f"- Total gastado hasta hoy: ${total_gastado:,.0f} ({pct:.1f}% del ingreso)\n"
        f"- Presupuesto diario reajustado: ${presupuesto_reajustado:,.0f}/dia\n"
        f"- Dinero restante proyectado: ${ahorro_proyectado:,.0f}\n\n"
        f"GASTOS POR CATEGORIA:\n{cat_str or '  (sin gastos registrados)'}\n\n"
        f"ULTIMOS 5 GASTOS:\n{last5_str or '  (sin gastos registrados)'}\n\n"
        f"GASTOS FIJOS MENSUALES:\n{fijos_str or '  (sin gastos fijos)'}"
    )


def call_grok(prompt, context):
    try:
        client = OpenAI(
            api_key=GROK_API_KEY,
            base_url="https://api.x.ai/v1",
        )
        response = client.chat.completions.create(
            model="grok-3-mini",
            messages=[
                {"role": "system", "content": context},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error al conectar con el asesor IA: {str(e)}"


DEFAULT_CATEGORIES = [
    "Alimentación", "Transporte", "Salud", "Entretenimiento",
    "Educación", "Ropa", "Hogar", "Otros"
]

# ── Auth helpers ──────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def load_users() -> dict:
    sb = get_supabase()
    res = sb.table("users").select("username, password, name").execute()
    return {row["username"]: {"password": row["password"], "name": row.get("name", "")} for row in res.data}

def save_users(users: dict):
    pass  # users saved individually via register_user()

def register_user(username: str, password_hash: str, name: str):
    sb = get_supabase()
    sb.table("users").upsert({"username": username, "password": password_hash, "name": name}).execute()

def data_file_for(username: str) -> str:
    safe = "".join(c for c in username.lower() if c.isalnum() or c == "_")
    return f"data_{safe}.json"

# ── Data helpers ──────────────────────────────────────────────────────────────
def load_data(username: str) -> dict:
    sb = get_supabase()
    res = sb.table("user_data").select("data").eq("username", username).execute()
    if res.data:
        return res.data[0]["data"]
    return {
        "ingresos": [],
        "gastos": [],
        "gastos_fijos": [],
        "categorias": DEFAULT_CATEGORIES,
        "fijos_aplicados": [],
    }

def save_data(username: str, data: dict):
    sb = get_supabase()
    sb.table("user_data").upsert({"username": username, "data": data}).execute()

# ── Utility ───────────────────────────────────────────────────────────────────
def mes_actual() -> str:
    return date.today().strftime("%Y-%m")

def dias_en_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]

def ingreso_del_mes(data: dict, mes: str) -> float:
    for i in data["ingresos"]:
        if i["mes"] == mes:
            return float(i["monto"])
    return 0.0

def gastos_del_mes(data: dict, mes: str) -> list:
    return [g for g in data["gastos"] if g["fecha"].startswith(mes)]


def fmt(n: float) -> str:
    """Format number: dot as thousands sep, comma as decimal."""
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    s = f"{n:,.2f}"
    integer_part, decimal_part = s.split(".")
    integer_part = integer_part.replace(",", ".")
    return integer_part + "," + decimal_part

def aplicar_fijos_si_necesario(username: str, data: dict):
    mes = mes_actual()
    if mes in data.get("fijos_aplicados", []):
        return
    hoy = date.today()
    if hoy.day == 1:
        for fijo in data["gastos_fijos"]:
            data["gastos"].append({
                "fecha": hoy.strftime("%Y-%m-%d"),
                "categoria": fijo.get("categoria", "Hogar"),
                "monto": float(fijo["monto"]),
                "descripcion": f"[FIJO] {fijo['nombre']}",
            })
        data["fijos_aplicados"].append(mes)
        save_data(username, data)

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: #000000; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color: #000000; }

.stMarkdown, .stMarkdown p, .stMarkdown li,
p, span, div, label, .stText,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
.stSelectbox label, .stTextInput label,
.stNumberInput label, .stDateInput label,
.stRadio label, .stCheckbox label,
.stExpander summary, .stExpander p,
.stMetric label, .stMetric [data-testid="stMetricValue"],
.stMetric [data-testid="stMetricLabel"],
.stAlert p, .stInfo p, .stSuccess p, .stWarning p,
.stDataFrame, .stDataFrame td, .stDataFrame th,
.element-container p, .element-container span,
.stProgress .stMarkdown { color: #000000 !important; }

[data-testid="stSidebar"] {
    background: linear-gradient(175deg, #0f172a 0%, #1e293b 100%);
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stRadio label { font-family:'Syne',sans-serif; font-size:1rem; color:#ffffff !important; }
[data-testid="stSidebar"] .stRadio p { color:#ffffff !important; }
[data-testid="stSidebar"] .stRadio span { color:#ffffff !important; }

.stApp { background: #f8fafc; }

/* Login card */
.login-wrap {
    max-width: 420px; margin: 60px auto 0;
    background: white; border-radius: 20px;
    padding: 2.5rem 2.5rem 2rem;
    box-shadow: 0 4px 32px rgba(99,102,241,.12);
    border-top: 5px solid #6366f1;
}
.login-title {
    font-family:'Syne',sans-serif; font-weight:800;
    font-size:1.7rem; color:#000 !important; margin-bottom:.2rem;
}
.login-sub { font-size:.88rem; color:#555 !important; margin-bottom:1.5rem; }

/* Metric cards */
.card {
    background: white; border-radius: 16px;
    padding: 1.4rem 1.6rem;
    box-shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.04);
    margin-bottom: 1rem; border-left: 5px solid #6366f1;
}
.card.green  { border-left-color: #10b981; }
.card.red    { border-left-color: #ef4444; }
.card.yellow { border-left-color: #f59e0b; }
.card .label { font-size:.8rem; color:#555555 !important; text-transform:uppercase; letter-spacing:.08em; margin-bottom:.3rem; }
.card .value { font-family:'Syne',sans-serif; font-size:1.9rem; font-weight:800; color:#000000 !important; }
.card .sub   { font-size:.78rem; color:#333333 !important; margin-top:.3rem; }

/* Tooltips */
.card-wrap { position: relative; }
.info-btn {
    position: absolute; top: 10px; right: 12px;
    width: 22px; height: 22px; border-radius: 50%;
    background: #e0e7ff; color: #4338ca !important;
    font-size: .75rem; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; border: none; outline: none;
    transition: background .15s; font-family: 'Syne', sans-serif; z-index: 10;
}
.info-btn:hover { background: #c7d2fe; }
.tooltip-box {
    display: none;
    position: absolute; top: 36px; right: 8px;
    background: #1e293b; color: #f1f5f9 !important;
    border-radius: 10px; padding: .7rem .9rem;
    font-size: .75rem; line-height: 1.5;
    width: 230px; z-index: 100;
    box-shadow: 0 8px 24px rgba(0,0,0,.25);
}
.tooltip-box strong { color: #a5b4fc !important; }
.card-wrap:hover .tooltip-box,
.info-btn:focus + .tooltip-box { display: block; }

/* Section title */
.sec-title {
    font-family:'Syne',sans-serif; font-weight:800;
    font-size:1.35rem; color:#000000 !important;
    border-bottom:3px solid #6366f1;
    padding-bottom:.4rem; margin-bottom:1.2rem; margin-top:1.5rem;
}

/* Status pill */
.pill { display:inline-block; border-radius:999px; padding:.3rem 1rem; font-weight:600; font-size:.85rem; }
.pill.ok   { background:#d1fae5; color:#065f46 !important; }
.pill.warn { background:#fef3c7; color:#92400e !important; }
.pill.bad  { background:#fee2e2; color:#991b1b !important; }

/* Date input, number input fields: black bg white text */
input[type="number"], input[type="text"], input[type="date"],
div[data-testid="stDateInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input,
.stDateInput input, .stNumberInput input, .stTextInput input {
    background-color: #1e293b !important;
    color: #ffffff !important;
    border-color: #475569 !important;
}
/* Number input +/- buttons */
div[data-testid="stNumberInput"] button {
    background-color: #334155 !important;
    color: #ffffff !important;
    border-color: #475569 !important;
}
/* Date input wrapper */
div[data-testid="stDateInput"] > div,
div[data-baseweb="datepicker"] input {
    background-color: #1e293b !important;
    color: #ffffff !important;
}

/* Selectbox: black bg, white text everywhere */
div[data-baseweb="select"] > div,
div[data-baseweb="select"] > div > div,
div[data-baseweb="select"] input {
    background-color: #1e293b !important;
    color: #ffffff !important;
    border-color: #475569 !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] div,
div[data-baseweb="select"] p {
    color: #ffffff !important;
}
/* Dropdown list container */
div[data-baseweb="popover"],
div[data-baseweb="popover"] > div,
div[data-baseweb="popover"] ul,
div[data-baseweb="popover"] li,
div[data-baseweb="popover"] [role="option"] {
    background-color: #1e293b !important;
    color: #ffffff !important;
}
div[data-baseweb="popover"] li:hover,
div[data-baseweb="popover"] [role="option"]:hover,
div[data-baseweb="popover"] [aria-selected="true"] {
    background-color: #334155 !important;
    color: #ffffff !important;
}
/* All text nodes inside options */
div[data-baseweb="popover"] span,
div[data-baseweb="popover"] div,
div[data-baseweb="popover"] p {
    color: #ffffff !important;
    background-color: transparent !important;
}
[data-baseweb="menu"],
[data-baseweb="menu"] > div,
[data-baseweb="menu"] ul,
[data-baseweb="menu"] li,
[data-baseweb="menu"] [role="option"] {
    background-color: #1e293b !important;
    color: #ffffff !important;
}
[data-baseweb="menu"] span,
[data-baseweb="menu"] div,
[data-baseweb="menu"] p {
    color: #ffffff !important;
}
[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover {
    background-color: #334155 !important;
}

/* User badge in sidebar */
.user-badge {
    background: rgba(99,102,241,.25); border-radius: 10px;
    padding: .5rem .8rem; margin-bottom: .5rem;
    font-size: .82rem; color: #c7d2fe !important;
}
.user-badge strong { color: #fff !important; font-size:.95rem; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH FLOW — shown before anything else if not logged in
# ══════════════════════════════════════════════════════════════════════════════
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"

if not st.session_state.logged_in:
    # Center the form
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div class="login-wrap">
          <div class="login-title">💰 Finanzas Personales</div>
          <div class="login-sub">Gestioná tus ingresos y gastos de forma privada.</div>
        </div>
        """, unsafe_allow_html=True)

        mode = st.radio(
            "Modo",
            ["Iniciar sesión", "Crear cuenta"],
            horizontal=True,
            label_visibility="collapsed",
        )

        users = load_users()

        if mode == "Iniciar sesión":
            with st.form("form_login"):
                username = st.text_input("Usuario", placeholder="Tu nombre de usuario")
                password = st.text_input("Contraseña", type="password", placeholder="••••••••")
                ok = st.form_submit_button("Entrar →", use_container_width=True)
                if ok:
                    if username in users and users[username]["password"] == hash_password(password):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.rerun()
                    elif username not in users:
                        st.error("Usuario no encontrado.")
                    else:
                        st.error("Contraseña incorrecta.")

        else:  # Crear cuenta
            with st.form("form_register"):
                new_user = st.text_input("Elegí un usuario", placeholder="ej: juan123")
                new_name = st.text_input("Tu nombre", placeholder="ej: Juan")
                new_pass = st.text_input("Contraseña", type="password", placeholder="Mínimo 4 caracteres")
                new_pass2 = st.text_input("Repetí la contraseña", type="password", placeholder="••••••••")
                ok = st.form_submit_button("Crear cuenta →", use_container_width=True)
                if ok:
                    if len(new_user) < 3:
                        st.error("El usuario debe tener al menos 3 caracteres.")
                    elif new_user in users:
                        st.error("Ese usuario ya existe. Elegí otro.")
                    elif len(new_pass) < 4:
                        st.error("La contraseña debe tener al menos 4 caracteres.")
                    elif new_pass != new_pass2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        register_user(new_user, hash_password(new_pass), new_name)
                        st.success(f"¡Cuenta creada! Ya podés iniciar sesión como **{new_user}**.")

    st.stop()   # Nothing below renders until logged in

# ══════════════════════════════════════════════════════════════════════════════
# LOGGED IN — load user data
# ══════════════════════════════════════════════════════════════════════════════
username = st.session_state.username
users    = load_users()
display_name = users.get(username, {}).get("name", username)

data = load_data(username)
aplicar_fijos_si_necesario(username, data)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div class="user-badge">
        👤 <strong>{display_name}</strong><br>
        <span style="font-size:.75rem;opacity:.7">@{username}</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio(
        "Navegación",
        ["🏠 Resumen", "💵 Ingresos", "🧾 Gastos", "📌 Gastos Fijos", "📊 Gráficos", "🤖 Asesor IA"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    mes_sel = st.selectbox(
        "Mes seleccionado",
        options=[mes_actual()] + sorted(
            set(i["mes"] for i in data["ingresos"]) |
            set(g["fecha"][:7] for g in data["gastos"]),
            reverse=True
        ),
        index=0,
    )
    st.markdown("---")
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

mes = mes_sel if mes_sel else mes_actual()

# ── Computations ──────────────────────────────────────────────────────────────
anio_n, mes_n    = int(mes[:4]), int(mes[5:])
total_dias       = dias_en_mes(anio_n, mes_n)
hoy              = date.today()
dia_actual       = hoy.day if (hoy.year == anio_n and hoy.month == mes_n) else total_dias

ingreso          = ingreso_del_mes(data, mes)
gastos_mes       = gastos_del_mes(data, mes)
total_gastado    = sum(float(g["monto"]) for g in gastos_mes)
presupuesto_diario_original = ingreso / total_dias if ingreso > 0 else 0

dias_restantes   = max(total_dias - dia_actual, 0)
gastado_hasta_hoy = sum(
    float(g["monto"]) for g in gastos_mes
    if datetime.strptime(g["fecha"], "%Y-%m-%d").date() <= hoy
)
presupuesto_acumulado = presupuesto_diario_original * dia_actual
diferencia = presupuesto_acumulado - gastado_hasta_hoy

if dias_restantes > 0 and ingreso > 0:
    presupuesto_reajustado = (ingreso - gastado_hasta_hoy) / dias_restantes
else:
    presupuesto_reajustado = presupuesto_diario_original

ahorro_proyectado = ingreso - total_gastado

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Resumen":
    st.markdown(f"<h1>Hola, {display_name} 👋</h1>", unsafe_allow_html=True)
    st.markdown(f"**Período:** {mes}  |  **Día {dia_actual} de {total_dias}**")

    if ingreso == 0:
        st.warning("⚠️ No cargaste ingresos para este mes. Andá a la sección **Ingresos** para comenzar.")

    if ingreso > 0:
        if diferencia >= 0:
            estado_html = f'<span class="pill ok">✅ Vas ahorrando ${fmt(diferencia)}</span>'
        else:
            estado_html = f'<span class="pill bad">⚠️ Gastaste ${fmt(abs(diferencia))} de más — ajustá los próximos días</span>'
        st.markdown(estado_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # Budget card color/tag
    # reajustado > original → sobró plata → podés gastar más (verde)
    # reajustado < original → gastaste de más → ajustá gastos (amarillo)
    if presupuesto_reajustado > presupuesto_diario_original:
        budget_color = "green"
        budget_label_tag = "<span style='font-size:.72rem;color:#065f46;background:#d1fae5;border-radius:4px;padding:1px 6px;margin-left:6px;'>↑ podés gastar más</span>"
    elif presupuesto_reajustado < presupuesto_diario_original:
        budget_color = "yellow"
        budget_label_tag = "<span style='font-size:.72rem;color:#92400e;background:#fef3c7;border-radius:4px;padding:1px 6px;margin-left:6px;'>↓ ajustá gastos</span>"
    else:
        budget_color = ""
        budget_label_tag = ""

    # ── Metric cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(f"""
        <div class="card-wrap"><div class="card">
            <button class="info-btn" tabindex="0">ⓘ</button>
            <div class="tooltip-box"><strong>Ingreso mensual</strong><br>
            El dinero total que registraste como ingreso para este mes.<br><br>
            <strong>Cálculo:</strong> valor ingresado manualmente en la sección Ingresos.</div>
            <div class="label">Ingreso mensual</div>
            <div class="value">${fmt(ingreso)}</div>
        </div></div>""", unsafe_allow_html=True)

    with c2:
        card_color2 = 'green' if (ingreso > 0 and total_gastado <= ingreso * 0.8) else ('red' if ingreso > 0 else '')
        sub2 = f"<div class='sub'>{total_gastado/ingreso*100:.1f}% del ingreso</div>" if ingreso > 0 else ""
        st.markdown(f"""
        <div class="card-wrap"><div class="card {card_color2}">
            <button class="info-btn" tabindex="0">ⓘ</button>
            <div class="tooltip-box"><strong>Total gastado</strong><br>
            Suma de todos los gastos del mes, incluyendo fijos.<br><br>
            <strong>Cálculo:</strong> Σ(montos de gastos del mes)<br>
            Verde = menos del 80% del ingreso. Rojo = más del 80%.</div>
            <div class="label">Total gastado</div>
            <div class="value">${fmt(total_gastado)}</div>
            {sub2}
        </div></div>""", unsafe_allow_html=True)

    with c3:
        sub3 = f"<div class='sub'>Original: ${fmt(presupuesto_diario_original)}/día{budget_label_tag}</div>" if presupuesto_reajustado != presupuesto_diario_original else ""
        st.markdown(f"""
        <div class="card-wrap"><div class="card {budget_color}">
            <button class="info-btn" tabindex="0">ⓘ</button>
            <div class="tooltip-box"><strong>Presupuesto diario</strong><br>
            Cuánto podés gastar por día para los días restantes.<br><br>
            <strong>Cálculo:</strong><br>
            (Ingreso − Gastado hasta hoy) ÷ Días restantes<br><br>
            Se reajusta según si gastaste de más o de menos.</div>
            <div class="label">Presupuesto diario</div>
            <div class="value">${fmt(presupuesto_reajustado)}<span style="font-size:1rem;font-weight:400">/día</span></div>
            {sub3}
        </div></div>""", unsafe_allow_html=True)

    with c4:
        color4 = "green" if ahorro_proyectado >= 0 else "red"
        sub4 = f"<div class='sub'>{ahorro_proyectado/ingreso*100:.1f}% del ingreso</div>" if ingreso > 0 else ""
        st.markdown(f"""
        <div class="card-wrap"><div class="card {color4}">
            <button class="info-btn" tabindex="0">ⓘ</button>
            <div class="tooltip-box"><strong>Dinero restante</strong><br>
            Lo que te quedaría si no gastás nada más en el mes.<br><br>
            <strong>Cálculo:</strong><br>
            Ingreso mensual − Total gastado hasta ahora<br><br>
            Verde = ahorrando. Rojo = gastaste más de lo que ingresaste.</div>
            <div class="label">Dinero restante</div>
            <div class="value">${fmt(ahorro_proyectado)}</div>
            {sub4}
        </div></div>""", unsafe_allow_html=True)

    # Progress
    if ingreso > 0:
        st.markdown('<div class="sec-title">Progreso del mes</div>', unsafe_allow_html=True)
        pct = min(total_gastado / ingreso, 1.0)
        pct_dia = dia_actual / total_dias
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.progress(pct, text=f"Gastado: {pct*100:.1f}% del ingreso")
            st.progress(pct_dia, text=f"Tiempo transcurrido: {pct_dia*100:.1f}% del mes")
        with col_b:
            st.metric("Días restantes", dias_restantes)
            st.metric("Presupuesto diario", f"${fmt(presupuesto_reajustado)}/día")

    if gastos_mes:
        st.markdown('<div class="sec-title">Últimos gastos</div>', unsafe_allow_html=True)
        df = pd.DataFrame(gastos_mes).sort_values("fecha", ascending=False).head(10)
        df.columns = [c.title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)

    if ingreso > 0 and GROK_API_KEY:
        st.markdown('<div class="sec-title">🤖 Análisis del mes</div>', unsafe_allow_html=True)
        if st.button('✨ Generar análisis con IA', use_container_width=False):
            with st.spinner('Analizando tus finanzas...'):
                ctx = build_financial_context(
                    data, mes, ingreso, total_gastado, presupuesto_reajustado,
                    dia_actual, total_dias, dias_restantes, ahorro_proyectado
                )
                analysis = call_grok(
                    'Analiza mis finanzas del mes y dame un resumen con: '
                    '1) como voy en general, 2) en que categoria gasto mas, '
                    '3) si voy a llegar bien a fin de mes, 4) un consejo concreto. '
                    'Se directo y breve, maximo 5 oraciones.',
                    ctx
                )
            st.info(analysis)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INGRESOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💵 Ingresos":
    st.markdown("<h1>Ingresos</h1>", unsafe_allow_html=True)

    st.markdown('<div class="sec-title">Registrar ingreso mensual</div>', unsafe_allow_html=True)
    with st.form("form_ingreso"):
        col1, col2 = st.columns(2)
        with col1:
            mes_ing = st.text_input("Mes (YYYY-MM)", value=mes_actual())
        with col2:
            monto_ing = st.number_input("Monto ($)", min_value=0.0, max_value=99_999_999.0, step=100.0)
        submitted = st.form_submit_button("💾 Guardar ingreso", use_container_width=True)
        if submitted:
            data["ingresos"] = [i for i in data["ingresos"] if i["mes"] != mes_ing]
            data["ingresos"].append({"mes": mes_ing, "monto": monto_ing})
            save_data(username, data)
            st.success(f"✅ Ingreso de ${fmt(monto_ing)} guardado para {mes_ing}")
            st.rerun()

    st.markdown('<div class="sec-title">Historial de ingresos</div>', unsafe_allow_html=True)
    if data["ingresos"]:
        ingresos_sorted = sorted(data["ingresos"], key=lambda x: x["mes"], reverse=True)
        for ing in ingresos_sorted:
            col1, col2, col3 = st.columns([2, 2, 1])
            col1.write(ing["mes"])
            col2.write(f"${fmt(float(ing['monto']))}")
            if col3.button("🗑️", key=f"del_ing_{ing['mes']}"):
                data["ingresos"] = [i for i in data["ingresos"] if i["mes"] != ing["mes"]]
                save_data(username, data)
                st.rerun()
    else:
        st.info("No hay ingresos registrados aún.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: GASTOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🧾 Gastos":
    st.markdown("<h1>Gastos</h1>", unsafe_allow_html=True)

    with st.expander("➕ Agregar nueva categoría"):
        nueva_cat = st.text_input("Nombre de la categoría")
        if st.button("Agregar categoría") and nueva_cat:
            if nueva_cat not in data["categorias"]:
                data["categorias"].append(nueva_cat)
                save_data(username, data)
                st.success(f"Categoría '{nueva_cat}' agregada.")
                st.rerun()

    st.markdown('<div class="sec-title">Registrar gasto</div>', unsafe_allow_html=True)
    with st.form("form_gasto"):
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_g = st.date_input("Fecha", value=hoy)
        with col2:
            cat_g = st.selectbox("Categoría", data["categorias"])
        with col3:
            monto_g = st.number_input("Monto ($)", min_value=0.0, max_value=99_999_999.0, step=10.0)
        desc_g = st.text_input("Descripción (opcional)")
        submitted = st.form_submit_button("💾 Registrar gasto", use_container_width=True)
        if submitted and monto_g > 0:
            data["gastos"].append({
                "fecha": fecha_g.strftime("%Y-%m-%d"),
                "categoria": cat_g,
                "monto": monto_g,
                "descripcion": desc_g,
            })
            save_data(username, data)
            st.success(f"✅ Gasto de ${fmt(monto_g)} en '{cat_g}' registrado.")
            st.rerun()

    if ingreso > 0:
        st.markdown('<div class="sec-title">Estado del presupuesto</div>', unsafe_allow_html=True)
        if diferencia >= 0:
            st.success(f"✅ Vas bien. Podés gastar hasta **${fmt(presupuesto_reajustado)}/día** los próximos {dias_restantes} días.")
        else:
            st.warning(f"⚠️ Gastaste ${fmt(abs(diferencia))} de más. Ajustá a **${fmt(presupuesto_reajustado)}/día** para los próximos {dias_restantes} días.")

    st.markdown('<div class="sec-title">Gastos del mes seleccionado</div>', unsafe_allow_html=True)
    if gastos_mes:
        gastos_sorted = sorted(
            [(i, g) for i, g in enumerate(data["gastos"]) if g["fecha"].startswith(mes)],
            key=lambda x: x[1]["fecha"], reverse=True
        )
        for orig_idx, g in gastos_sorted:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 3, 1])
            col1.write(g["fecha"])
            col2.write(g["categoria"])
            col3.write(f"${fmt(float(g['monto']))}")
            col4.write(g.get("descripcion", ""))
            if col5.button("🗑️", key=f"del_gasto_{orig_idx}"):
                data["gastos"].pop(orig_idx)
                save_data(username, data)
                st.rerun()
    else:
        st.info("No hay gastos para este mes.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: GASTOS FIJOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📌 Gastos Fijos":
    st.markdown("<h1>Gastos Fijos Mensuales</h1>", unsafe_allow_html=True)
    st.info("Estos gastos se descuentan **automáticamente el 1° de cada mes**.")

    st.markdown('<div class="sec-title">Agregar gasto fijo</div>', unsafe_allow_html=True)
    with st.form("form_fijo"):
        col1, col2, col3 = st.columns(3)
        with col1:
            nombre_f = st.text_input("Nombre (ej: Alquiler)")
        with col2:
            cat_f = st.selectbox("Categoría", data["categorias"])
        with col3:
            monto_f = st.number_input("Monto mensual ($)", min_value=0.0, max_value=99_999_999.0, step=50.0)
        submitted = st.form_submit_button("💾 Agregar gasto fijo", use_container_width=True)
        if submitted and nombre_f and monto_f > 0:
            data["gastos_fijos"].append({"nombre": nombre_f, "categoria": cat_f, "monto": monto_f})
            save_data(username, data)
            st.success(f"✅ Gasto fijo '{nombre_f}' agregado.")
            st.rerun()

    st.markdown('<div class="sec-title">Gastos fijos registrados</div>', unsafe_allow_html=True)
    if data["gastos_fijos"]:
        total_fijos = sum(f["monto"] for f in data["gastos_fijos"])
        for idx, fijo in enumerate(data["gastos_fijos"]):
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            col1.write(fijo["nombre"])
            col2.write(fijo.get("categoria", "—"))
            col3.write(f"${fmt(float(fijo['monto']))}/mes")
            if col4.button("🗑️", key=f"del_fijo_{idx}"):
                data["gastos_fijos"].pop(idx)
                save_data(username, data)
                st.rerun()
        st.markdown(f"**Total fijos mensuales: ${fmt(total_fijos)}**")
        if ingreso > 0:
            st.markdown(f"Representan el **{total_fijos/ingreso*100:.1f}%** de tus ingresos.")
    else:
        st.info("No hay gastos fijos registrados aún.")

    st.markdown('<div class="sec-title">Aplicar fijos manualmente</div>', unsafe_allow_html=True)
    st.warning("Usá esto solo para testing o si los fijos no se aplicaron el 1° del mes.")
    if st.button("⚡ Aplicar gastos fijos ahora al mes actual"):
        m = mes_actual()
        if m in data["fijos_aplicados"]:
            data["fijos_aplicados"].remove(m)
        for fijo in data["gastos_fijos"]:
            data["gastos"].append({
                "fecha": hoy.strftime("%Y-%m-%d"),
                "categoria": fijo.get("categoria", "Hogar"),
                "monto": float(fijo["monto"]),
                "descripcion": f"[FIJO] {fijo['nombre']}",
            })
        data["fijos_aplicados"].append(m)
        save_data(username, data)
        st.success("Gastos fijos aplicados.")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 Gráficos":
    st.markdown("<h1>Gráficos</h1>", unsafe_allow_html=True)

    if not gastos_mes:
        st.info("No hay gastos para el mes seleccionado. Registrá gastos para ver los gráficos.")
    else:
        df_plot = pd.DataFrame(gastos_mes)
        by_cat = df_plot.groupby("categoria")["monto"].sum().reset_index()
        by_cat.columns = ["Categoría", "Total"]
        by_cat = by_cat.sort_values("Total", ascending=False)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="sec-title">Distribución de gastos por categoría</div>', unsafe_allow_html=True)
            fig1 = px.pie(by_cat, values="Total", names="Categoría", hole=0.45,
                          color_discrete_sequence=px.colors.qualitative.Set3)
            fig1.update_traces(textposition="outside", textinfo="percent+label", textfont=dict(color="#000000", size=12))
            fig1.update_layout(showlegend=True,
                               legend=dict(orientation="v", x=1.0, y=0.5, font=dict(color="#000000")),
                               font=dict(color="#000000"),
                               margin=dict(t=30,b=30,l=10,r=10),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            st.markdown('<div class="sec-title">Gastos como % del ingreso mensual</div>', unsafe_allow_html=True)
            if ingreso > 0:
                by_cat_pct = by_cat.copy()
                by_cat_pct["% del ingreso"] = by_cat_pct["Total"] / ingreso * 100
                extra = pd.DataFrame([{"Categoría": "💚 Ahorro",
                                        "Total": max(0, ingreso - total_gastado),
                                        "% del ingreso": max(0, (ingreso - total_gastado) / ingreso * 100)}])
                by_cat_full = pd.concat([by_cat_pct, extra], ignore_index=True)
                colors = px.colors.qualitative.Set3[:len(by_cat_pct)] + ["#6ee7b7"]
                fig2 = px.pie(by_cat_full, values="Total", names="Categoría", hole=0.45,
                              color_discrete_sequence=colors, custom_data=["% del ingreso"])
                fig2.update_traces(textposition="outside", textinfo="percent+label",
                                   textfont=dict(color="#000000", size=12),
                                   hovertemplate="%{label}: $%{value:,.0f} (%{customdata[0]:.1f}% del ingreso)<extra></extra>")
                fig2.update_layout(showlegend=True,
                                   legend=dict(orientation="v", x=1.0, y=0.5, font=dict(color="#000000")),
                                   font=dict(color="#000000"),
                                   margin=dict(t=30,b=30,l=10,r=10),
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Cargá el ingreso del mes para ver este gráfico.")

        st.markdown('<div class="sec-title">Gasto diario vs presupuesto</div>', unsafe_allow_html=True)
        df_plot["dia"] = pd.to_datetime(df_plot["fecha"]).dt.day
        daily = df_plot.groupby("dia")["monto"].sum().reset_index()
        daily.columns = ["Día", "Gastado"]
        all_days = pd.DataFrame({"Día": range(1, total_dias + 1)})
        daily = all_days.merge(daily, on="Día", how="left").fillna(0)
        daily["Presupuesto"] = presupuesto_diario_original

        fig3 = go.Figure()
        fig3.add_bar(x=daily["Día"], y=daily["Gastado"], name="Gastado",
                     marker_color="#6366f1", opacity=0.85)
        fig3.add_scatter(x=daily["Día"], y=daily["Presupuesto"], name="Presupuesto diario",
                         line=dict(color="#ef4444", width=2, dash="dash"))
        fig3.update_layout(xaxis_title="Día del mes", yaxis_title="$",
                           font=dict(color="#000000"),
                           legend=dict(orientation="h", y=1.08, font=dict(color="#000000")),
                           margin=dict(t=20,b=40),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           xaxis=dict(showgrid=False, color="#000000", title_font=dict(color="#000000")),
                           yaxis=dict(gridcolor="#f1f5f9", color="#000000", title_font=dict(color="#000000")),
                           bargap=0.3)
        st.plotly_chart(fig3, use_container_width=True)

        st.markdown('<div class="sec-title">Resumen por categoría</div>', unsafe_allow_html=True)
        summary = by_cat.copy()
        if ingreso > 0:
            summary["% del ingreso"] = (summary["Total"] / ingreso * 100).map("{:.1f}%".format)
        summary["Total"] = summary["Total"].map("${:,}".format)
        st.dataframe(summary, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ASESOR IA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🤖 Asesor IA":
    st.markdown("<h1>🤖 Asesor IA</h1>", unsafe_allow_html=True)
    st.markdown("Hacé preguntas sobre tus finanzas y el asesor responde con datos reales de tu cuenta.")

    if not GROK_API_KEY:
        st.error("No hay API key de Gemini configurada. Agregala en el archivo .env o en Streamlit Secrets.")
    elif ingreso == 0:
        st.warning("Carga tu ingreso mensual primero para que el asesor tenga contexto.")
    else:
        ctx = build_financial_context(
            data, mes, ingreso, total_gastado, presupuesto_reajustado,
            dia_actual, total_dias, dias_restantes, ahorro_proyectado
        )

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Suggested questions
        st.markdown('<div class="sec-title">Preguntas sugeridas</div>', unsafe_allow_html=True)
        sugerencias = [
            "En que categoria gasto mas?",
            "Voy a llegar bien a fin de mes?",
            "Dame 3 consejos para ahorrar",
            "Puedo gastar $10.000 esta semana?",
            "Como estan mis gastos fijos?",
        ]
        cols = st.columns(3)
        for i, s in enumerate(sugerencias):
            if cols[i % 3].button(s, key=f"sug_{i}", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": s})
                with st.spinner("Pensando..."):
                    resp = call_grok(s, ctx)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
                st.rerun()

        # Chat history
        if st.session_state.chat_history:
            st.markdown('<div class="sec-title">Conversacion</div>', unsafe_allow_html=True)
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    with st.chat_message("user"):
                        st.write(msg["content"])
                else:
                    with st.chat_message("assistant"):
                        st.write(msg["content"])

        # Input form
        st.markdown('<div class="sec-title">Tu pregunta</div>', unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_input = st.text_input("Escribi tu pregunta...", placeholder="ej: Como voy este mes?")
            send = st.form_submit_button("Enviar", use_container_width=False)
            if send and user_input.strip():
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                with st.spinner("Pensando..."):
                    resp = call_grok(user_input, ctx)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
                st.rerun()

        if st.session_state.chat_history:
            if st.button("Limpiar conversacion"):
                st.session_state.chat_history = []
                st.rerun()
