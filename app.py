from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
import os
import re
import qrcode


app = Flask(__name__)

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================

# En el computador usa esta clave.
# En Render puede usar una variable SECRET_KEY.
app.secret_key = os.environ.get("SECRET_KEY", "renova_verificacion_2026")

# En el computador usa SQLite: titulos.db
# En Render usará la base pagada con DATABASE_URL.
database_url = os.environ.get("DATABASE_URL", "sqlite:///titulos.db")

# Render puede entregar la URL como postgres://
# SQLAlchemy necesita postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =====================================================
# MODELO DE TÍTULOS
# =====================================================

class Titulo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    codigo = db.Column(db.String(120), unique=True, nullable=False)

    nombre_estudiante = db.Column(db.String(200), nullable=False)
    documento = db.Column(db.String(80), nullable=False)
    titulo_obtenido = db.Column(db.String(150), nullable=False)

    acta = db.Column(db.String(50), nullable=False)
    libro = db.Column(db.String(50), nullable=False)
    folio = db.Column(db.String(50), nullable=False)
    resolucion = db.Column(db.String(250), nullable=False)
    fecha_grado = db.Column(db.String(120), nullable=False)

    estado = db.Column(
        db.String(180),
        default="Registrado y válido en el archivo académico institucional"
    )

    fecha_registro = db.Column(db.DateTime, default=datetime.now)


# =====================================================
# FUNCIONES
# =====================================================

def extraer_anio(fecha_grado):
    texto = fecha_grado or ""
    encontrados = re.findall(r"\b(19\d{2}|20\d{2})\b", texto)

    if encontrados:
        return encontrados[-1]

    return str(datetime.now().year)


def abreviatura_titulo(titulo_obtenido):
    texto = (titulo_obtenido or "").lower()

    if "bachiller" in texto:
        return "BA"

    if "técnico" in texto or "tecnico" in texto:
        return "TL"

    return "AC"


def generar_codigo(titulo_obtenido, fecha_grado, acta, libro, folio):
    programa = abreviatura_titulo(titulo_obtenido)
    anio = extraer_anio(fecha_grado)

    acta_limpia = str(acta).strip().upper().replace(" ", "")
    libro_limpio = str(libro).strip().upper().replace(" ", "").zfill(2)
    folio_limpio = str(folio).strip().upper().replace(" ", "").zfill(2)

    return f"REN-{programa}-{anio}-{acta_limpia}-{libro_limpio}-{folio_limpio}"


def admin_requerido(funcion):
    @wraps(funcion)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))

        return funcion(*args, **kwargs)

    return wrapper


def crear_qr(codigo):
    carpeta_qr = os.path.join(app.root_path, "static", "qr")
    os.makedirs(carpeta_qr, exist_ok=True)

    nombre_archivo = f"{codigo}.png"
    ruta_archivo = os.path.join(carpeta_qr, nombre_archivo)

    enlace = request.host_url.rstrip("/") + url_for("verificar", codigo=codigo)

    qr = qrcode.make(enlace)
    qr.save(ruta_archivo)

    return nombre_archivo


# =====================================================
# RUTAS PÚBLICAS
# =====================================================

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()

        if not codigo:
            flash("Digite el código de verificación.", "error")
            return redirect(url_for("index"))

        return redirect(url_for("verificar", codigo=codigo))

    return render_template("index.html")


@app.route("/verificar/<codigo>")
def verificar(codigo):
    codigo = codigo.strip().upper()

    titulo = Titulo.query.filter_by(codigo=codigo).first()

    qr_archivo = None

    if titulo:
        qr_archivo = crear_qr(codigo)

    return render_template(
        "verificar.html",
        titulo=titulo,
        codigo=codigo,
        qr_archivo=qr_archivo
    )


# =====================================================
# PANEL PRIVADO
# =====================================================

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "").strip()

        if usuario == "admin" and clave == "Renova2026":
            session["admin"] = True
            return redirect(url_for("admin"))

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/admin")
@admin_requerido
def admin():
    titulos = Titulo.query.order_by(Titulo.id.desc()).all()

    return render_template(
        "admin.html",
        titulos=titulos
    )


@app.route("/admin/nuevo", methods=["POST"])
@admin_requerido
def nuevo_titulo():
    nombre_estudiante = request.form.get("nombre_estudiante", "").strip().upper()
    documento = request.form.get("documento", "").strip()
    titulo_obtenido = request.form.get("titulo_obtenido", "").strip()
    acta = request.form.get("acta", "").strip()
    libro = request.form.get("libro", "").strip()
    folio = request.form.get("folio", "").strip()
    resolucion = request.form.get("resolucion", "").strip()
    fecha_grado = request.form.get("fecha_grado", "").strip()
    estado = request.form.get("estado", "").strip()

    if not nombre_estudiante or not documento or not titulo_obtenido or not acta or not libro or not folio or not resolucion or not fecha_grado:
        flash("Debe completar todos los campos obligatorios.", "error")
        return redirect(url_for("admin"))

    codigo = generar_codigo(
        titulo_obtenido=titulo_obtenido,
        fecha_grado=fecha_grado,
        acta=acta,
        libro=libro,
        folio=folio
    )

    existe = Titulo.query.filter_by(codigo=codigo).first()

    if existe:
        flash(f"Ya existe un título registrado con el código {codigo}. Revise acta, libro y folio.", "error")
        return redirect(url_for("admin"))

    nuevo = Titulo(
        codigo=codigo,
        nombre_estudiante=nombre_estudiante,
        documento=documento,
        titulo_obtenido=titulo_obtenido,
        acta=acta,
        libro=libro,
        folio=folio,
        resolucion=resolucion,
        fecha_grado=fecha_grado,
        estado=estado or "Registrado y válido en el archivo académico institucional"
    )

    db.session.add(nuevo)
    db.session.commit()

    flash(f"Título registrado correctamente. Código generado: {codigo}", "ok")

    return redirect(url_for("admin"))


@app.route("/admin/eliminar/<int:id>", methods=["POST"])
@admin_requerido
def eliminar_titulo(id):
    titulo = Titulo.query.get_or_404(id)

    db.session.delete(titulo)
    db.session.commit()

    flash("Registro eliminado correctamente.", "ok")

    return redirect(url_for("admin"))


@app.route("/admin/salir")
def salir():
    session.clear()

    return redirect(url_for("index"))


# =====================================================
# CREAR TABLAS Y PRIMER REGISTRO
# =====================================================

with app.app_context():
    db.create_all()

    codigo_inicial = "REN-BA-2026-2312-03-18"

    existe_inicial = Titulo.query.filter_by(codigo=codigo_inicial).first()

    if not existe_inicial:
        titulo_inicial = Titulo(
            codigo=codigo_inicial,
            nombre_estudiante="CUERVO BARBOSA ANDRES FELIPE",
            documento="C.C. 1000773994",
            titulo_obtenido="Bachiller Académico",
            acta="2312",
            libro="03",
            folio="18",
            resolucion="548 de fecha 15 de junio del 2026",
            fecha_grado="15 de junio de 2026",
            estado="Registrado y válido en el archivo académico institucional"
        )

        db.session.add(titulo_inicial)
        db.session.commit()


# =====================================================
# INICIAR APLICACIÓN
# =====================================================

if __name__ == "__main__":
    app.run(debug=True)