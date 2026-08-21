import os
import hashlib
import qrcode
from datetime import datetime
from flask import Flask, request, jsonify, render_template, render_template_string, Response, abort

app = Flask(__name__)

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

# MÓDULO: REGISTRO DE USUARIOS
@app.route('/api/usuarios/registrar', methods=['POST'])
def registrar_usuario():
    data = request.json
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


# MÓDULO: VERIFICAR USUARIO POR QR (ACCESO A BIBLIOTECA)
@app.route('/usuario/<token_qr>', methods=['GET'])
def obtener_usuario_qr(token_qr):
    usuario = DB.get("usuarios", {}).get(token_qr)
    
    if not usuario:
        return jsonify({"error": "Usuario o código QR no encontrado"}), 404

    # Verificar si Iraida desactivó a este trabajador
    if usuario.get("estado") != "Activo":
        return jsonify({
            "error": "Acceso denegado",
            "mensaje": "Este usuario ha sido desactivado por la Administración de la Biblioteca Virtual."
        }), 403

    # Incrementar el contador de visitas al escanear
    usuario["visitas"] = usuario.get("visitas", 0) + 1

    return jsonify({
        "mensaje": "Consulta exitosa",
        "usuario": usuario
    }), 200


# MÓDULO ADMINISTRATIVO: CAMBIAR ESTADO / ELIMINAR (EXCLUSIVO IRAIDA MIJARES)
@app.route('/api/admin/usuarios/estado', methods=['POST'])
def cambiar_estado_usuario():
    data = request.json
    token_qr = data.get('token_qr')
    nuevo_estado = data.get('estado') # 'Activo' o 'Inactivo'

    if token_qr in DB["usuarios"]:
        DB["usuarios"][token_qr]["estado"] = nuevo_estado
        return jsonify({
            "mensaje": f"Estado del usuario actualizado a '{nuevo_estado}' por la Administración.",
            "usuario": DB["usuarios"][token_qr]
        }), 200

    return jsonify({"error": "Usuario no encontrado"}), 404


@app.route('/api/admin/usuarios/eliminar/<token_qr>', methods=['DELETE'])
def eliminar_usuario_admin(token_qr):
    if token_qr in DB["usuarios"]:
        # Borrar datos de la BD local
        del DB["usuarios"][token_qr]
        
        # Eliminar archivo QR físico
        qr_file = os.path.join(app.root_path, 'static', 'qr_codes', f"{token_qr}.png")
        if os.path.exists(qr_file):
            os.remove(qr_file)

        return jsonify({"mensaje": "Usuario y credenciales revocadas definitivamente por la Administración."}), 200

    return jsonify({"error": "Usuario no encontrado"}), 404

# RUTA WEB: VISTA DEL PANEL ADMINISTRATIVO
@app.route('/admin')
def vista_admin():
    return render_template('admin.html')

# API: OBTENER TODOS LOS USUARIOS (PARA LA TABLA ADMIN)
@app.route('/api/admin/usuarios', methods=['GET'])
def obtener_todos_usuarios():
    lista_usuarios = []
    for token, datos in DB.get("usuarios", {}).items():
        usuario_info = datos.copy()
        usuario_info["token_qr"] = token
        lista_usuarios.append(usuario_info)
        
    return jsonify({"usuarios": lista_usuarios}), 200

# MÓDULO: CARGA DE DOCUMENTOS
@app.route('/api/documentos/cargar', methods=['POST'])
def cargar_documento():
    if 'archivo' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    archivo = request.files['archivo']
    equipo = request.form.get('equipo', 'General')
    gama = request.form.get('gama', 'Estándar')

    nombre_archivo = archivo.filename
    ext = nombre_archivo.split('.')[-1].lower()

    if ext not in ['html', 'pdf', 'doc', 'docx']:
        return jsonify({"error": "Formato de archivo no permitido"}), 400

    doc_id = str(len(DB["documentos"]) + 1)
    subfolder = os.path.join(UPLOAD_FOLDER, equipo, gama)
    os.makedirs(subfolder, exist_ok=True)
    
    file_path = os.path.join(subfolder, f"{doc_id}_{nombre_archivo}")
    archivo.save(file_path)

    DB["documentos"][doc_id] = {
        "nombre": nombre_archivo,
        "equipo": equipo,
        "gama": gama,
        "ext": ext,
        "ruta": file_path
    }

    return jsonify({
        "mensaje": "Documento clasificado y guardado",
        "doc_id": doc_id,
        "equipo": equipo,
        "gama": gama
    }), 201

# MÓDULO: REPORTES
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
