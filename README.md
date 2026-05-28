# 💰 Finanzas Personales

App de gestión de finanzas personales construida con **Streamlit**. Soporta múltiples usuarios con datos completamente aislados.

## Funcionalidades

- 🔐 **Login / Registro** — Cada usuario tiene su cuenta privada. Contraseñas almacenadas con hash SHA-256.
- 💵 **Ingresos** — Registrá tu ingreso mensual. La app calcula automáticamente el presupuesto diario.
- 🧾 **Gastos** — Cargá gastos con categoría, monto y descripción. Categorías personalizables. Botón de eliminación en cada ítem.
- 📌 **Gastos Fijos** — Alquiler, suscripciones, etc. Se aplican automáticamente el 1° de cada mes.
- 📊 **Gráficos** — Torta de distribución, torta de % sobre ingresos, y gráfico de barras diario vs presupuesto.
- 🔔 **Alertas dinámicas** — Muestra si vas ahorrando o si debés ajustar, con el presupuesto diario reajustado.
- ⓘ **Tooltips** — Cada métrica del Resumen explica qué es y cómo se calcula.

## Instalación y ejecución local

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/finanzas-personales.git
cd finanzas-personales
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar la aplicación

```bash
streamlit run app.py
```

La app se abre en `http://localhost:8501`

---

## Estructura del proyecto

```
finanzas-personales/
├── app.py              ← Aplicación principal
├── requirements.txt    ← Dependencias Python
├── .gitignore          ← Excluye datos y cachés
└── README.md           ← Este archivo
```

Los archivos de datos se generan automáticamente al usar la app:
```
users.json          ← usuarios y contraseñas (hasheadas)
data_juan.json      ← datos de "juan"
data_maria.json     ← datos de "maria"
```
> ⚠️ Estos archivos están en `.gitignore` — no se suben al repo.

---

## Deploy en Streamlit Cloud

1. Subí el repo a GitHub (debe ser público o privado con acceso).
2. Entrá a [share.streamlit.io](https://share.streamlit.io).
3. Conectá tu cuenta de GitHub.
4. Seleccioná el repositorio y el archivo `app.py`.
5. ¡Listo!

> **Nota sobre persistencia**: En Streamlit Cloud los archivos `.json` se resetean al redeploy. Para persistencia real usá una base de datos externa (Supabase, Firebase, etc.).

---

## Subir a GitHub desde VS Code

```bash
git init
git add .
git commit -m "Initial commit: app de finanzas personales"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/finanzas-personales.git
git push -u origin main
```
