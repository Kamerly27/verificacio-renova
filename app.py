from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
import os
import re
import qrcode
import secrets


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "renova_verificacion_2026")

database_url = os.environ.get("DATABASE_URL", "sqlite:///titulos.db")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

ESTADO_VALIDO = "Registrado y válido en el archivo académico institucional"


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

    estado = db.Column(db.String(180), default=ESTADO_VALIDO)

    fecha_registro = db.Column(db.DateTime, default=datetime.now)


def limpiar_documento(documento):
    return re.sub(r"\D", "", documento or "")


def extraer_anio(fecha):
    encontrados = re.findall(r"\b(19\d{2}|20\d{2})\b", fecha or "")

    if encontrados:
        return encontrados[-1]

    return str(datetime.now().year)


def abreviatura_titulo(titulo):
    texto = (titulo or "").lower()

    if "bachiller" in texto:
        return "BA"

    if "técnico" in texto or "tecnico" in texto:
        return "TL"

    if "diplomado" in texto:
        return "DP"

    if "curso" in texto:
        return "CU"

    if "icfes" in texto:
        return "IC"

    if "cnsc" in texto:
        return "CN"

    if "certificado" in texto:
        return "CE"

    return "RN"


def generar_codigo(titulo_obtenido, fecha_grado, acta, libro, folio, documento):
    tipo = abreviatura_titulo(titulo_obtenido)
    anio = extraer_anio(fecha_grado)

    acta = (acta or "").strip().upper().replace(" ", "")
    libro = (libro or "").strip().upper().replace(" ", "")
    folio = (folio or "").strip().upper().replace(" ", "")

    if acta and libro and folio:
        return f"REN-{tipo}-{anio}-{acta}-{libro.zfill(2)}-{folio.zfill(2)}"

    documento_limpio = limpiar_documento(documento)
    final_documento = documento_limpio[-6:] if documento_limpio else "000000"
    aleatorio = secrets.token_hex(2).upper()

    return f"REN-{tipo}-{anio}-{final_documento}-{aleatorio}"


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


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        busqueda = request.form.get("codigo", "").strip()

        if not busqueda:
            flash("Digite el código de verificación o documento.", "error")
            return redirect(url_for("index"))

        codigo = busqueda.upper()

        titulo = Titulo.query.filter_by(codigo=codigo).first()

        if titulo:
            return redirect(url_for("verificar", codigo=titulo.codigo))

        documento_busqueda = limpiar_documento(busqueda)

        if documento_busqueda:
            titulos = Titulo.query.order_by(Titulo.id.desc()).all()

            for registro in titulos:
                if limpiar_documento(registro.documento) == documento_busqueda:
                    return redirect(url_for("verificar", codigo=registro.codigo))

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
    return render_template("admin.html", titulos=titulos)


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

    if not nombre_estudiante or not documento or not titulo_obtenido or not fecha_grado:
        flash("Debe completar nombre, documento, certificado o programa y fecha.", "error")
        return redirect(url_for("admin"))

    codigo = generar_codigo(
        titulo_obtenido,
        fecha_grado,
        acta,
        libro,
        folio,
        documento
    )

    existe = Titulo.query.filter_by(codigo=codigo).first()

    if existe:
        flash(f"Ya existe un registro con el código {codigo}.", "error")
        return redirect(url_for("admin"))

    nuevo = Titulo(
        codigo=codigo,
        nombre_estudiante=nombre_estudiante,
        documento=documento,
        titulo_obtenido=titulo_obtenido,
        acta=acta or "No aplica",
        libro=libro or "No aplica",
        folio=folio or "No aplica",
        resolucion=resolucion or "No aplica",
        fecha_grado=fecha_grado,
        estado=estado or ESTADO_VALIDO
    )

    db.session.add(nuevo)
    db.session.commit()

    flash(f"Certificado registrado correctamente. Código generado: {codigo}", "ok")

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
            estado=ESTADO_VALIDO
        )

        db.session.add(titulo_inicial)
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)