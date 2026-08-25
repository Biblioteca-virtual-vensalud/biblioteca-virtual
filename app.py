# ==============================================================================
# PROYECTO: SISTEMA DE BIBLIOTECA VIRTUAL VENSALUD
# AUTORA: Iraida Josefina Mijares Ramírez
# INSTITUCIÓN: VENSALUD, S.A.
# AÑO: 2026
# DESCRIPCIÓN: Plataforma de gestión documental, control de usuarios y QR
#              para la consulta de manuales de equipos electromédicos.
# ==============================================================================

import os
import uuid
import hashlib
import qrcode
from datetime import datetime
from flask import Flask, request, jsonify, render_template, render_template_string, Response, abort, redirect, url_for, session, send_from_directory

app = Flask(__name__)
app.secret_key = 'clave_secreta_biblioteca'  # Necesario para gestionar la sesión del usuario

# Contraseña del panel administrativo
ADMIN_PASSWORD = "admin123"

# Configuración de carpetas de almacenamiento
UPLOAD_FOLDER = 'biblioteca_storage'
QR_FOLDER = 'static/qr_codes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# Base de datos en memoria
DB = {
    "usuarios": {},     
    "documentos": {},   
    "metricas": []      
}

@app.route('/')
def inicio():
    return render_template('index.html')

# --- MÓDULO: AUTENTICACIÓN ADMIN ---

@app.route('/validar-admin', methods=['POST'])
def validar_admin():
    datos = request.get_json() or {}
    clave_ingresada = datos.get('clave') or datos.get('password')
    
    if clave_ingresada == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({"exito": True, "mensaje": "Acceso concedido"}), 200
    else:
        return jsonify({"exito": False, "error": "Contraseña incorrecta"}), 401

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password') or (request.json.get('clave') if request.is_json else None) or (request.json.get('password') if request.is_json else None)
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            if request.is_json:
                return jsonify({"exito": True, "mensaje": "Acceso concedido"}), 200
            return redirect(url_for('vista_admin'))
        else:
            if request.is_json:
                return jsonify({"exito": False, "error": "Contraseña incorrecta"}), 401
            return render_template_string('<h3>Contraseña incorrecta</h3><a href="/login">Intentar de nuevo</a>'), 401

    return '''
        <form method="post" style="margin: 50px; text-align: center; font-family: sans-serif;">
            <h2>Acceso Administrativo</h2>
            <input type="password" name="password" placeholder="Contraseña Admin" required style="padding: 8px;">
            <button type="submit" style="padding: 8px 15px;">Entrar</button>
        </form>
    '''

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

# --- MÓDULO: REGISTRO DE USUARIOS ---

@app.route('/api/usuarios/registrar', methods=['POST'])
def registrar_usuario():
    data = request.json or {}
    user_id = data.get('cedula')
    nombre = data.get('nombre')
    cargo = data.get('cargo')

    if not user_id or not nombre:
        return jsonify({"error": "Faltan datos requeridos"}), 400

    raw_info = f"{user_id}-{nombre}-{datetime.now().timestamp()}"
    token_qr = hashlib.sha256(raw_info.encode()).hexdigest()[:16]

    # Guardamos al usuario como 'Activo' por defecto
    DB["usuarios"][token_qr] = {
        "id": user_id,
        "nombre": nombre,
        "cargo": cargo,
        "visitas": 0,
        "estado": "Activo"
    }

    qr_img = qrcode.make(f"http://10.29.6.48:5000/usuario/{token_qr}")

    # Guardar en static/qr_codes
    qr_filename = f"{token_qr}.png"
    qr_folder = os.path.join(app.root_path, 'static', 'qr_codes')
    os.makedirs(qr_folder, exist_ok=True)

    qr_path = os.path.join(qr_folder, qr_filename)
    qr_img.save(qr_path)

    return jsonify({
        "mensaje": "Usuario registrado exitosamente",
        "user_id": user_id,
        "token_qr": token_qr,
        "qr_image_url": f"/static/qr_codes/{qr_filename}"
    }), 201

# --- MÓDULO: VERIFICAR USUARIO POR QR (ACCESO A BIBLIOTECA) ---

@app.route('/usuario/<token_qr>', methods=['GET'])
def obtener_usuario_qr(token_qr):
    usuario = DB.get("usuarios", {}).get(token_qr)
    
    if not usuario:
        return jsonify({"error": "Usuario o código QR no encontrado"}), 404

    if usuario.get("estado") != "Activo":
        return jsonify({
            "error": "Acceso denegado",
            "mensaje": "Este usuario ha sido desactivado por la Administración de la Biblioteca Virtual."
        }), 403

    usuario["visitas"] = usuario.get("visitas", 0) + 1

    return jsonify({
        "mensaje": "Consulta exitosa",
        "usuario": usuario
    }), 200

# --- MÓDULO ADMINISTRATIVO: CAMBIAR ESTADO / ELIMINAR (PROTEGIDO) ---

@app.route('/api/admin/usuarios/estado', methods=['POST'])
def cambiar_estado_usuario():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "No autorizado"}), 401

    data = request.json or {}
    token_qr = data.get('token_qr')
    nuevo_estado = data.get('estado')

    if token_qr in DB["usuarios"]:
        DB["usuarios"][token_qr]["estado"] = nuevo_estado
        return jsonify({
            "mensaje": f"Estado del usuario actualizado a '{nuevo_estado}' por la Administración.",
            "usuario": DB["usuarios"][token_qr]
        }), 200

    return jsonify({"error": "Usuario no encontrado"}), 404

@app.route('/api/admin/usuarios/eliminar/<token_qr>', methods=['DELETE'])
def eliminar_usuario_admin(token_qr):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "No autorizado"}), 401

    if token_qr in DB["usuarios"]:
        del DB["usuarios"][token_qr]
        
        qr_file = os.path.join(app.root_path, 'static', 'qr_codes', f"{token_qr}.png")
        if os.path.exists(qr_file):
            os.remove(qr_file)

        return jsonify({"mensaje": "Usuario y credenciales revocadas definitivamente por la Administración."}), 200

    return jsonify({"error": "Usuario no encontrado"}), 404

# RUTA WEB: VISTA DEL PANEL ADMINISTRATIVO (PROTEGIDA)
@app.route('/admin')
def vista_admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

# API: OBTENER TODOS LOS USUARIOS (PARA LA TABLA ADMIN)
@app.route('/api/admin/usuarios', methods=['GET'])
def obtener_todos_usuarios():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "No autorizado"}), 401

    lista_usuarios = []
    for token, datos in DB.get("usuarios", {}).items():
        usuario_info = datos.copy()
        usuario_info["token_qr"] = token
        lista_usuarios.append(usuario_info)
        
    return jsonify({"usuarios": lista_usuarios}), 200

# --- MÓDULO: CARGA DE DOCUMENTOS ---

@app.route('/api/documentos/cargar', methods=['POST'])
def cargar_documento():
    if 'archivo' not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400

    archivo = request.files['archivo']
    equipo = request.form.get('equipo', 'General')
    gama = request.form.get('gama', 'General')

    if archivo.filename == '':
        return jsonify({"error": "Nombre de archivo no válido"}), 400

    doc_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(archivo.filename)[1]
    nombre_archivo = f"{doc_id}_{archivo.filename}"
    ruta_guardado = os.path.join(UPLOAD_FOLDER, nombre_archivo)
    archivo.save(ruta_guardado)

    # Guarda en la BD
    DB["documentos"][doc_id] = {
        "nombre": archivo.filename,
        "equipo": equipo,
        "gama": gama,
        "ext": ext,
        "ruta": f"/archivos/{nombre_archivo}"
    }

    return jsonify({
        "mensaje": "Documento clasificado y guardado",
        "doc_id": doc_id,
        "equipo": equipo,
        "gama": gama,
        "ruta": f"/archivos/{nombre_archivo}"
    }), 201

@app.route('/api/documentos/listar', methods=['GET'])
def listar_documentos():
    lista = []
    for doc_id, datos in DB.get("documentos", {}).items():
        doc_info = datos.copy()
        doc_info["id"] = doc_id
        lista.append(doc_info)
    return jsonify({"documentos": lista}), 200

# RUTA FUNDAMENTAL PARA ABRIR Y VISUALIZAR LOS ARCHIVOS
@app.route('/archivos/<path:filename>')
def ver_archivo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# --- MÓDULO: REPORTES ---

@app.route('/api/reportes/metricas', methods=['GET'])
def obtener_metricas():
    return jsonify({
        "total_usuarios": len(DB["usuarios"]),
        "total_documentos": len(DB["documentos"]),
        "historial_consultas": DB["metricas"]
    })

if __name__ == '__main__':
    print("Iniciando Biblioteca Virtual...")
    app.run(host='0.0.0.0', port=5000, debug=True)
