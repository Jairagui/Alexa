# Archivo Lambda principal de la skill Entrenador Fit

import os
import sys
import json
from pathlib import Path
import random
import logging

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None
    class ClientError(Exception):
        pass

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.ui import SimpleCard
from ask_sdk_model.dialog import ElicitSlotDirective
from ask_sdk_model import Intent as AIntent, Slot as ASlot


# --- Configuración S3 para guardar/ver rutinas ---
S3_REGION = os.environ.get("S3_PERSISTENCE_REGION")
S3_BUCKET = os.environ.get("S3_PERSISTENCE_BUCKET")


def _get_s3_client():
    # Crea el cliente de S3 si hay configuración; si no, regresa None
    if not boto3 or not S3_BUCKET:
        return None
    try:
        if S3_REGION:
            return boto3.client("s3", region_name=S3_REGION)
        return boto3.client("s3")
    except Exception as e:
        logging.error("Error creando cliente S3: %r", e)
        return None


def cargar_rutinas_guardadas(user_id):
   # Lee la lista de rutinas guardadas desde S3. Si falla o no existe, regresa []
    cli = _get_s3_client()
    if not cli:
        return []
    key = f"{user_id}/rutinas_guardadas.json" if user_id else "rutinas_guardadas.json"
    try:
        resp = cli.get_object(Bucket=S3_BUCKET, Key=key)
        body = resp["Body"].read().decode("utf-8")
        if not body.strip():
            return []
        data = json.loads(body)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        # Si algo falla leyendo, solo regresamos lista vacía
        return []


def guardar_rutinas_guardadas(user_id, data):
    """Guarda la lista de rutinas en S3."""
    cli = _get_s3_client()
    if not cli:
        return
    key = f"{user_id}/rutinas_guardadas.json" if user_id else "rutinas_guardadas.json"
    try:
        body = json.dumps(data, ensure_ascii=False, indent=2)
        cli.put_object(Bucket=S3_BUCKET, Key=key, Body=body.encode("utf-8"))
    except Exception:
        # Si falla, no se guarda pero no truena la skill
        pass


HERE = Path(__file__).parent
# Aseguramos que esta carpeta esté en sys.path para importar módulos locales
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# --- Import de módulos del proyecto ---
from rutina_servicio import RoutineFacade
from modos_rutina import crear_strategy
from selector_sets import elegir_set
import imc  # opcional
import rutina_creador as builder  # noqa: F401
import app  # noqa: F401

# --- Helpers para data y conversiones ---
def cargar_data():
    # Carga routines.json con las plantillas de rutinas
    ruta = HERE / "routines.json"
    if not ruta.exists():
        return {"rutinas": []}
    return json.loads(ruta.read_text(encoding="utf-8"))

def _safe_int(x, default=0):
    # Convierte a int de forma segura
    try:
        return int(float(x))
    except Exception:
        return default

def _safe_float(x, default=0.0):
    # Convierte a float de forma segura
    try:
        return float(x)
    except Exception:
        return default

def norm_modo(s):
    # Normaliza el modo a "random" o "manual"
    s = (s or "").strip().lower()
    if s in ("aleatorio", "al azar", "random", "sorpresa"):
        return "random"
    return "manual"

def norm_tipo(s):
    # Normaliza tipo de rutina a UPPER o LOWER
    s = (s or "").strip().lower()
    if s in ("upper", "uper", "up", "tren superior", "arriba", "superior", "pecho", "pecho y espalda", "brazos"):
        return "UPPER"
    if s in ("lower", "louer", "low", "tren inferior", "abajo", "inferior", "piernas", "gluteos", "glúteos"):
        return "LOWER"
    return ""

def norm_nivel(s):
    # Normaliza el nivel a FACIL / MEDIO / DIFICIL
    s = (s or "").strip().lower()
    if s in ("facil", "fácil", "basico", "básico", "principiante"):
        return "FACIL"
    if s in ("medio", "intermedio"):
        return "MEDIO"
    if s in ("dificil", "difícil", "avanzado", "intenso"):
        return "DIFICIL"
    return ""

def parse_estatura_cm(v):
    # Convierte la estatura a centímetros (acepta metros y cm)
    if v is None:
        return None
    try:
        f = float(v)
    except Exception:
        return None
    if f < 3.0:
        return int(round(f * 100))
    return int(round(f))

# ---------- IMC ----------
def _calc_imc_fallback(peso_kg, estatura_cm):
    # Cálculo directo de IMC por si no usamos la librería imc
    m = max(0.5, float(estatura_cm) / 100.0)
    return round(peso_kg / (m * m), 2)

def _clasificar_por_imc_valor(imc_val):
    # Convierte valor de IMC a categoría
    if imc_val < 18.5: return "BAJO_PESO"
    if imc_val < 25:   return "NORMAL"
    if imc_val < 30:   return "SOBREPESO"
    return "OBESIDAD"

def clasificar_imc(peso_kg, estatura_cm):
    # Intenta usar funciones del módulo imc, si no, usa cálculo local
    try:
        if hasattr(imc, "clasificar_imc"):
            return str(imc.clasificar_imc(peso_kg, estatura_cm))
        if hasattr(imc, "clase_imc"):
            return str(imc.clase_imc(peso_kg, estatura_cm))
        if hasattr(imc, "calcular_imc"):
            v = float(imc.calcular_imc(peso_kg, estatura_cm))
            return _clasificar_por_imc_valor(v)
        if hasattr(imc, "get_imc"):
            v = float(imc.get_imc(peso_kg, estatura_cm))
            return _clasificar_por_imc_valor(v)
    except Exception as e:
        print("WARN imc module:", repr(e))
    v = _calc_imc_fallback(peso_kg, estatura_cm)
    return _clasificar_por_imc_valor(v)

# ---------- Ajustes de rutina ----------
def ajustar_descansos_por_imc(rutina, categoria):
    # Ajusta segundos de descanso según categoría de IMC
    if not isinstance(rutina, dict): return rutina
    pasos = rutina.get("pasos")
    if not isinstance(pasos, list): return rutina
    cat = (categoria or "").upper()

    for p in pasos:
        t = str(p.get("title", "")).lower()
        if "descanso" in t or "rest" in t or "pausa" in t:
            s = _safe_int(p.get("segundos", 0), 0)
            if cat in ("SOBREPESO", "OBESIDAD"):
                s = max(30, s + 15)
            elif cat == "NORMAL":
                s = max(10, s - 5)
            p["segundos"] = int(s)
    return rutina

# Pool mínimo de ejercicios por tipo (para rellenar)
POOL_UPPER = [
    {"title":"Flexiones", "segundos":30, "decir":"Espalda recta."},
    {"title":"Remo invertido", "segundos":30, "decir":"Escápulas atrás."},
    {"title":"Fondos en banco", "segundos":30, "decir":"Codos hacia atrás."},
    {"title":"Pike push up", "segundos":30, "decir":"Cadera arriba."}
]
POOL_LOWER = [
    {"title":"Sentadillas", "segundos":30, "decir":"Talones al suelo."},
    {"title":"Zancadas", "segundos":30, "decir":"Alterna piernas."},
    {"title":"Puente de glúteo", "segundos":30, "decir":"Aprieta al subir."},
    {"title":"Elevación de talones", "segundos":30, "decir":"Sube y baja controlado."}
]

def es_descanso(p): 
    # Detecta si el paso es descanso
    t = str(p.get("title","")).lower()
    return ("descanso" in t) or ("pausa" in t) or ("rest" in t)

def es_calentamiento(p):
    # Detecta si el paso es calentamiento
    return "calent" in str(p.get("title","")).lower()

def normalizar_segundos_ejercicio(p, nivel):
    """Ajusta los segundos de ejercicios (no descanso) por nivel."""
    base = _safe_int(p.get("segundos", p.get("duracion", 30)), 30)
    if es_descanso(p): return p
    if nivel == "FACIL":  base = max(20, int(round(base * 0.8)))
    if nivel == "MEDIO":  base = max(25, int(round(base * 1.0)))
    if nivel == "DIFICIL":base = max(35, int(round(base * 1.2)))
    p["segundos"] = base
    return p

def ajustar_por_nivel_y_tipo(rutina, nivel, tipo):
    """Define número de ejercicios y ajusta tiempos según nivel y tipo."""
    if not isinstance(rutina, dict):
        return rutina
    pasos = list(rutina.get("pasos", []))
    if not pasos:
        return rutina

    # Separamos calentamiento, descansos y ejercicios
    calent = [p for p in pasos if es_calentamiento(p)]
    rests  = [p for p in pasos if es_descanso(p)]
    exs    = [p for p in pasos if (not es_descanso(p) and not es_calentamiento(p))]

    # Cantidad objetivo de ejercicios según nivel
    objetivo = {"FACIL":4, "MEDIO":6, "DIFICIL":8}.get(nivel, 6)

    # Recortar o rellenar ejercicios para llegar al objetivo
    if len(exs) > objetivo:
        exs = exs[:objetivo]
    elif len(exs) < objetivo:
        pool = POOL_UPPER if tipo == "UPPER" else POOL_LOWER
        i = 0
        while len(exs) < objetivo and i < len(pool)*2:
            exs.append(dict(pool[i % len(pool)]))  # copia
            i += 1

    # Ajustar segundos de cada ejercicio
    exs = [normalizar_segundos_ejercicio(dict(p), nivel) for p in exs]

    # Reconstruimos la rutina: calentamiento (si hay) + [ejercicio, descanso]...
    rest_template = next((r for r in rests), {"title":"Descanso", "segundos":20, "decir":""})
    nueva = []
    if calent:
        for c in calent[:1]:
            nueva.append(dict(c))
    for idx, e in enumerate(exs, 1):
        nueva.append(e)
        if idx < len(exs):
            nueva.append(dict(rest_template))
    rutina["pasos"] = nueva
    if "titulo" not in rutina:
        rutina["titulo"] = f"Rutina {tipo.title()} - {nivel.title()}"
    return rutina

# ---------- Texto para Alexa ----------
def resumen_y_texto(rutina):
    """Convierte la rutina a texto entendible para Alexa."""
    pasos = []
    resumen = "Rutina generada."
    if isinstance(rutina, dict):
        pasos = rutina.get("pasos", []) or rutina.get("rutina", [])
        resumen = rutina.get("titulo") or rutina.get("resumen") or resumen
    elif isinstance(rutina, list):
        pasos = rutina

    partes = [str(resumen).strip()]
    # Máximo 12 pasos para no hacer una respuesta muy larga
    for i, p in enumerate(pasos, 1):
        if isinstance(p, dict):
            t = str(p.get("title", p.get("nombre", "Paso"))).strip()
            s = int(p.get("segundos", p.get("duracion", 0)) or 0)
            d = str(p.get("decir", p.get("descripcion", "")) or "").strip()
        else:
            t = str(p).strip()
            s = 0
            d = ""
        linea = f"Paso {i}: {t}" + (f", {s} segundos." if s else ".")
        if d:
            linea += f" {d}"
        partes.append(linea)
        if i >= 12:
            break
    return " ".join(partes)

def intentar_generar(facade, peso, est, nivel, tipo):
    """Llama al facade para generar una rutina con los parámetros dados."""
    intentos = [
        dict(peso_kg=peso, estatura_cm=est, nivel=nivel, tipo=tipo),
    ]
    errores = []
    for kwargs in intentos:
        try:
            rutina = facade.generar_rutina(kwargs.get("nivel"), kwargs.get("tipo"), kwargs.get("peso_kg"), kwargs.get("estatura_cm"))
            return rutina, errores
        except Exception as e:
            errores.append(str(e))
    return None, errores

def rutina_fallback(tipo, nivel):
    # Rutina de respaldo por si algo falla al generar
    objetivo = {"FACIL":4, "MEDIO":6, "DIFICIL":8}.get(nivel, 6)
    base = [{"title":"Calentamiento", "segundos":60, "decir":"Movilidad articular suave."}]
    pool = POOL_UPPER if tipo == "UPPER" else POOL_LOWER
    exs = [dict(pool[i % len(pool)]) for i in range(objetivo)]
    rest = {"title":"Descanso", "segundos":20, "decir":""}
    pasos = []
    pasos += base
    for i, e in enumerate(exs, 1):
        e = normalizar_segundos_ejercicio(e, nivel)
        pasos.append(e)
        if i < len(exs):
            pasos.append(dict(rest))
    return {"titulo": f"Rutina {tipo.title()} - {nivel.title()}", "pasos": pasos}

# === Alexa Handlers ===
class LaunchRequestHandler(AbstractRequestHandler):
    # Maneja cuando el usuario solo abre la skill
    def can_handle(self, handler_input):
        return handler_input.request_envelope.request.object_type == "LaunchRequest"

    def handle(self, handler_input):
        speak = ("¡Bienvenido a Entrenador Fit! "
                 "Puedo ayudarte a crear una rutina nueva o ver tus rutinas. "
                 "Di: crear rutinas o ver rutinas.")
        reprompt = "¿Qué eliges? Puedes decir crear rutinas o ver rutinas."
        return handler_input.response_builder.speak(speak).ask(reprompt).response

class GenerarRutinaIntentHandler(AbstractRequestHandler):
    # Intent principal para crear una rutina (manual o aleatoria)
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "GenerarRutinaIntent"

    def _slot(self, intent, name):
        # Helper sencillo para leer un slot
        s = (intent.slots or {}).get(name)
        return (s.value if s else None) or None

    def _ask_slot(self, handler_input, intent, slot_name, prompt):
        # Pregunta un slot específico y mantiene el intent
        return (handler_input.response_builder
                .speak(prompt).ask(prompt)
                .add_directive(ElicitSlotDirective(
                    slot_to_elicit=slot_name,
                    updated_intent=AIntent(name=intent.name, slots=intent.slots)))
                .response)

    def _generar_combinado(self, modo, peso, est, nivel, tipo):
        # Genera la rutina usando data, strategy y facade; luego ajusta por nivel/IMC
        data = cargar_data()
        strategy = crear_strategy(modo, elegir_set_func=elegir_set)
        facade = RoutineFacade(data, strategy=strategy)
        rutina, errs = intentar_generar(facade, peso, est, nivel, tipo)
        if rutina is None:
            rutina = rutina_fallback(tipo or "UPPER", nivel)
        rutina = ajustar_por_nivel_y_tipo(rutina, nivel, tipo or "UPPER")
        cat = clasificar_imc(peso, est)
        print("IMC categoria:", cat)
        rutina = ajustar_descansos_por_imc(rutina, cat)
        return resumen_y_texto(rutina)

    def handle(self, handler_input):
        intent = handler_input.request_envelope.request.intent

        peso_kg     = self._slot(intent, "peso_kg")
        estatura_cm = self._slot(intent, "estatura_cm")
        modo_raw    = self._slot(intent, "modo")
        tipo_raw    = self._slot(intent, "tipo")
        nivel_raw   = self._slot(intent, "nivel")

        # Pedimos peso y estatura si faltan
        if not peso_kg:
            return self._ask_slot(handler_input, intent, "peso_kg",
                "¿Cuál es tu peso en kilogramos? Puedes decir setenta o setenta kilos.")
        if not estatura_cm:
            return self._ask_slot(handler_input, intent, "estatura_cm",
                "¿Cuál es tu estatura? Puedes decir ciento setenta y dos centímetros o uno punto setenta y dos metros.")
        if not modo_raw:
            return self._ask_slot(handler_input, intent, "modo",
                "¿Quieres modo manual o aleatorio?")

        peso = _safe_float(peso_kg, 70.0)
        est  = parse_estatura_cm(estatura_cm) or 170
        modo = norm_modo(modo_raw)

        # Modo aleatorio: la skill decide tipo y nivel
        if modo == "random":
            tipo  = random.choice(["UPPER","LOWER"])
            nivel = "MEDIO"
            texto = self._generar_combinado("random", peso, est, nivel, tipo)
            sess = handler_input.attributes_manager.session_attributes
            sess['awaiting'] = 'like_routine'
            sess['params'] = {'modo':'random','peso':peso,'estatura':est,'nivel':nivel,'tipo':tipo}
            sess['last_routine'] = texto
            pregunta = texto + ' ¿Te gusta la rutina? Puedes decir sí o no.'
            return handler_input.response_builder.speak(pregunta).ask('¿Te gusta la rutina?').response

        # Modo manual: el usuario elige tipo y nivel
        tipo  = norm_tipo(tipo_raw)
        if not tipo:
            return self._ask_slot(handler_input, intent, "tipo",
                "¿Quieres rutina de tren superior o tren inferior? También puedes decir upper o lower.")
        nivel = norm_nivel(nivel_raw)
        if not nivel:
            return self._ask_slot(handler_input, intent, "nivel",
                "¿Qué nivel quieres? fácil, medio o difícil?")

        texto = self._generar_combinado("manual", peso, est, nivel, tipo)
        sess = handler_input.attributes_manager.session_attributes
        sess['awaiting'] = 'like_routine'
        sess['params'] = {'modo':'manual','peso':peso,'estatura':est,'nivel':nivel,'tipo':tipo}
        sess['last_routine'] = texto
        pregunta = texto + ' ¿Te gusta la rutina? Puedes decir sí o no.'
        return handler_input.response_builder.speak(pregunta).ask('¿Te gusta la rutina?').response


class YesIntentHandler(AbstractRequestHandler):
    # Maneja cuando el usuario responde "sí"
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "AMAZON.YesIntent"

    def handle(self, handler_input):
        sess = handler_input.attributes_manager.session_attributes
        if sess is None:
            sess = {}
            handler_input.attributes_manager.session_attributes = sess
        awaiting = sess.get('awaiting')
        if awaiting == 'like_routine':
            # Le gustó la rutina, preguntamos si la quiere guardar
            sess['awaiting'] = 'confirm_save'
            return handler_input.response_builder.speak("¿Quieres guardar la rutina? Puedes decir sí o no.").ask("¿Quieres guardarla?").response
        if awaiting == 'confirm_save':
            # Confirmó guardar, ahora pedimos nombre
            sess['awaiting'] = 'ask_name'
            return handler_input.response_builder.speak("¿Cómo quieres llamar esta rutina?").ask("¿Cómo la quieres llamar?").response
        # Si no hay flujo activo, regresamos al menú
        return handler_input.response_builder.speak("De acuerdo. ¿Qué deseas hacer, crear rutinas o ver rutinas?").ask("¿Crear rutinas o ver rutinas?").response

class NoIntentHandler(AbstractRequestHandler):
    # Maneja cuando el usuario responde "no"
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "AMAZON.NoIntent"

    def handle(self, handler_input):
        sess = handler_input.attributes_manager.session_attributes
        if sess is None:
            sess = {}
            handler_input.attributes_manager.session_attributes = sess
        awaiting = sess.get('awaiting')
        if awaiting == 'like_routine':
            # No le gustó la rutina, intentamos generar otra distinta
            params = sess.get('params', {})
            modo = params.get('modo')
            peso = params.get('peso')
            est  = params.get('estatura')
            nivel= params.get('nivel')
            tipo = params.get('tipo')
            gen = GenerarRutinaIntentHandler()
            prev = sess.get('last_routine') or ''
            intento = 0
            texto = prev
            while intento < 5 and (texto.strip() == prev.strip()):
                if modo == 'manual':
                    texto = gen._generar_combinado('random', peso, est, nivel, tipo)
                else:
                    tipo = random.choice(['UPPER','LOWER'])
                    nivel = random.choice(['FACIL','MEDIO','DIFICIL']) if 'nivel' in locals() else 'MEDIO'
                    texto = gen._generar_combinado('random', peso, est, nivel, tipo)
                intento += 1
            sess['last_routine'] = texto
            sess['awaiting'] = 'like_routine'
            return handler_input.response_builder.speak(texto + " ¿Te gusta esta nueva rutina? Puedes decir sí o no.").ask("¿Te gusta esta nueva rutina?").response
        if awaiting == 'confirm_save':
            # No quiere guardar, terminamos la sesión
            return handler_input.response_builder.speak("Listo. ¡Hasta luego!").set_should_end_session(True).response
        return handler_input.response_builder.speak("Entendido.").set_should_end_session(True).response

class AsignarNombreRutinaIntentHandler(AbstractRequestHandler):
    # Asigna y guarda el nombre de la rutina actual
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "AsignarNombreRutinaIntent"

    def handle(self, handler_input):
        sess = handler_input.attributes_manager.session_attributes
        if sess is None:
            sess = {}
            handler_input.attributes_manager.session_attributes = sess
        awaiting = sess.get('awaiting')
        intent = handler_input.request_envelope.request.intent
        slot = (intent.slots or {}).get('nombre')
        nombre = slot.value if slot else None
        if awaiting != 'ask_name' or not nombre:
            # Si no estamos en el estado de pedir nombre, lo pedimos otra vez
            return handler_input.response_builder.speak("Dime el nombre para la rutina.").ask("¿Cómo quieres llamarla?").response
        try:
            # Id de usuario para separar rutinas por cuenta
            try:
                user_id = handler_input.request_envelope.session.user.user_id
            except Exception:
                user_id = None

            # Cargar rutinas existentes
            data = cargar_rutinas_guardadas(user_id)
            if not isinstance(data, list):
                data = []

            # Agregar la nueva rutina con su texto
            data.append({"nombre": nombre, "texto": sess.get('last_routine', '')})

            # Guardar en S3
            guardar_rutinas_guardadas(user_id, data)
        except Exception as e:
            print("Error guardando rutina:", repr(e))
        sess['awaiting'] = None
        speech = f"Rutina guardada como {nombre}. ¡Listo! Si quieres ver tus rutinas guardadas, di: ver rutinas."
        reprompt = "¿Quieres ver tus rutinas o crear otra rutina?"
        return handler_input.response_builder.speak(speech).ask(reprompt).response

class PesoSoloIntentHandler(AbstractRequestHandler):
    # Maneja cuando el usuario solo dice el peso primero
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "PesoSoloIntent"

    def handle(self, handler_input):
        intent = handler_input.request_envelope.request.intent
        peso = (intent.slots or {}).get("peso_kg")
        peso_val = peso.value if peso else None
        # Preparamos los slots para seguir en GenerarRutinaIntent
        slots = {
            "peso_kg": ASlot(name="peso_kg", value=peso_val),
            "estatura_cm": ASlot(name="estatura_cm"),
            "modo": ASlot(name="modo"),
            "tipo": ASlot(name="tipo"),
            "nivel": ASlot(name="nivel")
        }
        prompt = "¿Cuál es tu estatura? Puedes decir uno punto setenta y dos metros o ciento setenta y dos centímetros."
        return (handler_input.response_builder
                .speak(prompt).ask(prompt)
                .add_directive(ElicitSlotDirective(
                    slot_to_elicit="estatura_cm",
                    updated_intent=AIntent(name="GenerarRutinaIntent", slots=slots)))
                .response)

class EstaturaSoloIntentHandler(AbstractRequestHandler):
    # Maneja cuando el usuario da solo la estatura primero
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "EstaturaSoloIntent"

    def handle(self, handler_input):
        intent = handler_input.request_envelope.request.intent
        est = (intent.slots or {}).get("estatura_cm")
        est_val = est.value if est else None
        slots = {
            "peso_kg": ASlot(name="peso_kg"),
            "estatura_cm": ASlot(name="estatura_cm", value=est_val),
            "modo": ASlot(name="modo"),
            "tipo": ASlot(name="tipo"),
            "nivel": ASlot(name="nivel")
        }
        prompt = "¿Quieres modo manual o aleatorio?"
        return (handler_input.response_builder
                .speak(prompt).ask(prompt)
                .add_directive(ElicitSlotDirective(
                    slot_to_elicit="modo",
                    updated_intent=AIntent(name="GenerarRutinaIntent", slots=slots)))
                .response)


class VerRutinasIntentHandler(AbstractRequestHandler):
    # Lista las rutinas guardadas y dice sus nombres
    def can_handle(self, handler_input):
        return (handler_input.request_envelope.request.object_type == "IntentRequest"
                and handler_input.request_envelope.request.intent.name == "VerRutinasIntent")

    def handle(self, handler_input):
        try:
            try:
                user_id = handler_input.request_envelope.session.user.user_id
            except Exception:
                user_id = None
            rutinas = cargar_rutinas_guardadas(user_id)
        except Exception as e:
            print("Error leyendo rutinas en VerRutinasIntent:", repr(e))
            rutinas = []

        if not rutinas:
            speak = ("Todavía no tengo rutinas guardadas para mostrar. "
                     "Primero crea una diciendo: crear rutinas.")
            return handler_input.response_builder.speak(speak).ask("¿Quieres crear una rutina nueva?").response

        # Construimos la lista de nombres para decirla en voz
        nombres = []
        for r in rutinas:
            nom = ""
            try:
                nom = (r or {}).get("nombre")
            except Exception:
                nom = None
            if not nom:
                nom = "sin nombre"
            nombres.append(nom)

        total = len(nombres)
        if total == 1:
            lista_texto = nombres[0]
        else:
            if total == 2:
                lista_texto = " y ".join(nombres)
            else:
                lista_texto = ", ".join(nombres[:-1]) + " y " + nombres[-1]

        speak = (f"Tienes {total} rutinas guardadas. "
                 f"Sus nombres son: {lista_texto}. "
                 "Si quieres escuchar una rutina, di: ver rutina y el nombre, por ejemplo, ver rutina y el nombre. "
                 "También puedes crear otra rutina diciendo: crear rutinas. "
                 "Si quieres borrar una rutina, di: borrar rutina y el nombre, por ejemplo, borrar rutina hola.")

        return handler_input.response_builder.speak(speak).ask("¿Quieres crear otra rutina o salir?").response


class ElegirRutinaIntentHandler(AbstractRequestHandler):
    # Lee el contenido de una rutina guardada por nombre
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return (req.object_type == "IntentRequest"
                and req.intent.name == "ElegirRutinaIntent")

    def handle(self, handler_input):
        intent = handler_input.request_envelope.request.intent
        slot = (intent.slots or {}).get("nombre")
        nombre_buscar = (slot.value or "").strip() if slot and slot.value else ""
        if not nombre_buscar:
            speak = ("No escuché el nombre de la rutina. "
                     "Dime, por ejemplo: quiero la rutina y el nombre.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Qué rutina quieres escuchar?")
                    .response)

        try:
            user_id = handler_input.request_envelope.session.user.user_id
        except Exception:
            user_id = None

        try:
            rutinas = cargar_rutinas_guardadas(user_id)
        except Exception as e:
            print("Error leyendo rutinas en ElegirRutinaIntent:", repr(e))
            rutinas = []

        if not rutinas:
            speak = ("Por ahora no tienes rutinas guardadas. "
                     "Primero crea una diciendo: crear rutinas.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Quieres crear una rutina nueva?")
                    .response)

        # Buscamos la rutina por nombre 
        nombre_buscar_low = nombre_buscar.lower()
        elegida = None
        for r in rutinas:
            try:
                nom = (r or {}).get("nombre", "")
                if not isinstance(nom, str):
                    continue
                nom_low = nom.lower()
                if nombre_buscar_low in nom_low or nom_low in nombre_buscar_low:
                    elegida = r
                    break
            except Exception:
                continue

        if not elegida:
            speak = (f"No encontré ninguna rutina cuyo nombre se parezca a {nombre_buscar}. "
                     "Intenta de nuevo diciendo, por ejemplo: quiero la rutina y el nombre.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Qué rutina quieres escuchar?")
                    .response)

        nom_elegido = elegida.get("nombre") or nombre_buscar
        texto = elegida.get("texto") or "No tengo texto guardado para esta rutina."
        speak = f"Esta es la rutina {nom_elegido}: {texto}"
        return handler_input.response_builder.speak(speak).ask(
            "Si quieres, puedes escuchar otra rutina o crear una nueva."
        ).response




class BorrarRutinaIntentHandler(AbstractRequestHandler):
    # Borra una rutina guardada por nombre
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return (req.object_type == "IntentRequest"
                and req.intent.name == "BorrarRutinaIntent")

    def handle(self, handler_input):
        intent = handler_input.request_envelope.request.intent
        slot = (intent.slots or {}).get("nombre")
        nombre_buscar = (slot.value or "").strip() if slot and slot.value else ""
        if not nombre_buscar:
            speak = ("No escuché el nombre de la rutina que quieres borrar. "
                     "Dime, por ejemplo: borrar rutina y el nombre .")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Qué rutina quieres borrar?")
                    .response)

        # Leer rutinas desde S3
        try:
            try:
                user_id = handler_input.request_envelope.session.user.user_id
            except Exception:
                user_id = None
            rutinas = cargar_rutinas_guardadas(user_id)
        except Exception as e:
            print("Error leyendo rutinas en BorrarRutinaIntent:", repr(e))
            rutinas = []

        if not rutinas:
            speak = ("No tienes rutinas guardadas todavía. "
                     "Primero crea una diciendo: crear rutinas.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Quieres crear una rutina nueva?")
                    .response)

        # Buscamos la rutina que se va a borrar
        nombre_buscar_low = nombre_buscar.lower()
        indice_borrar = None
        nom_encontrado = None
        for idx, r in enumerate(rutinas):
            try:
                nom = (r or {}).get("nombre", "")
                if not isinstance(nom, str):
                    continue
                nom_low = nom.lower()
                if nombre_buscar_low in nom_low or nom_low in nombre_buscar_low:
                    indice_borrar = idx
                    nom_encontrado = nom
                    break
            except Exception:
                continue

        if indice_borrar is None:
            speak = (f"No encontré ninguna rutina cuyo nombre se parezca a {nombre_buscar}. "
                     "Intenta de nuevo diciendo, por ejemplo: borrar rutina y el nombre.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Qué rutina quieres borrar?")
                    .response)

        # Quitamos la rutina de la lista y guardamos cambios
        try:
            del rutinas[indice_borrar]
            guardar_rutinas_guardadas(user_id, rutinas)
        except Exception as e:
            print("Error borrando rutina en BorrarRutinaIntent:", repr(e))
            speak = ("Hubo un problema al borrar la rutina. "
                     "Intenta de nuevo más tarde.")
            return (handler_input.response_builder
                    .speak(speak)
                    .ask("¿Quieres hacer otra cosa, como ver o crear rutinas?")
                    .response)

        nom_final = nom_encontrado or nombre_buscar
        speak = (f"La rutina {nom_final} ha sido borrada. "
                 "Si quieres, puedes decir: ver rutinas, o crear una nueva rutina.")
        return (handler_input.response_builder
                .speak(speak)
                .ask("¿Quieres hacer algo más?")
                .response)


class HelpIntentHandler(AbstractRequestHandler):
    # Mensaje de ayuda general
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "AMAZON.HelpIntent"

    def handle(self, handler_input):
        speak = ("Te guío paso a paso. Di tu peso, estatura, luego elige modo manual o aleatorio.")
        return handler_input.response_builder.speak(speak).ask(speak).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    # Cancel/Stop, pero regresando al menú principal
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return (
            req.object_type == "IntentRequest"
            and req.intent.name in ("AMAZON.CancelIntent", "AMAZON.StopIntent")
        )

    def handle(self, handler_input):
        sess = handler_input.attributes_manager.session_attributes
        if sess is None:
            sess = {}
            handler_input.attributes_manager.session_attributes = sess
        # Limpiamos estado pendiente
        sess["awaiting"] = None

        speak = (
            "De acuerdo. Seguimos en Entrenador Fit. "
            "Puedes decir: crear rutinas, ver rutinas o ver rutina y el nombre, "
            "por ejemplo, ver rutina y el nombre."
        )
        reprompt = "¿Qué quieres hacer ahora? Puedes decir crear rutinas o ver rutinas."
        return handler_input.response_builder.speak(speak).ask(reprompt).response

class FallbackIntentHandler(AbstractRequestHandler):
    # Maneja frases que la skill no reconoce
    def can_handle(self, handler_input):
        req = handler_input.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == "AMAZON.FallbackIntent"

    def handle(self, handler_input):
        speak = "No entendí eso. Vamos paso a paso. ¿Cuál es tu peso en kilogramos?"
        return handler_input.response_builder.speak(speak).ask(speak).response

class SessionEndedRequestHandler(AbstractRequestHandler):
    # Cierra la sesión cuando Alexa manda SessionEndedRequest
    def can_handle(self, handler_input):
        return handler_input.request_envelope.request.object_type == "SessionEndedRequest"

    def handle(self, handler_input):
        return handler_input.response_builder.response

class CatchAllExceptionHandler(AbstractExceptionHandler):
    # Cubre cualquier excepción que no se haya manejado
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        print("Unhandled exception:", repr(exception))
        speak = "Ocurrió un problema. ¿Puedes repetir?"
        return handler_input.response_builder.speak(speak).ask(speak).response

# Registramos los handlers en el SkillBuilder
sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(GenerarRutinaIntentHandler())
sb.add_request_handler(VerRutinasIntentHandler())
sb.add_request_handler(BorrarRutinaIntentHandler())
sb.add_request_handler(ElegirRutinaIntentHandler())
sb.add_request_handler(PesoSoloIntentHandler())
sb.add_request_handler(EstaturaSoloIntentHandler())
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(NoIntentHandler())
sb.add_request_handler(AsignarNombreRutinaIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

# Punto de entrada para AWS Lambda
lambda_handler = sb.lambda_handler()
