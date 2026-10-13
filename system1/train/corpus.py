"""The S4 training corpus: generic synthetic examples for every System 1 set (system1.md §17).

    python corpus.py OUT.jsonl [--seed N] [--questions DIR] [--drafts DIR]

Each line is a `laya.train` row, `{state, questions, expected}`, with the set's own questions,
so the checkpoint learns the menus it serves. A `null` answer in an evaluation file becomes the
set's first no-answer key here (`unknown`, `other`, `pump`): training on a key the consumers
ignore teaches "no answer" without a separate objective.

Every evaluation file is held out. A generated state is dropped when it equals an evaluation
state of its set or shares at least `OVERLAP` of its words (Jaccard), so the gates that judge
the checkpoint never see a near-copy of what it trained on. The corpus is deterministic for a
seed; `train.py` records its sha256.
"""
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE.parent.parent / "config" / "system1" / "questions"
DRAFTS = HERE.parent / "drafts"
OVERLAP = 0.7
SEED = 20261013

# set: (folder, state field, per-option target count)
SETS = {
    "incident-triage": ("questions", "alert", 70),
    "operator-intake": ("questions", "text", None),
    "device-class": ("drafts", "readings", 60),
    "log-triage": ("drafts", "line", 60),
    "system2-router": ("drafts", "text", 80),
    "anomaly-screen": ("drafts", "window", 150),
}


def pick(rng, items):
    return items[rng.randrange(len(items))]


def num(rng, lo, hi, digits=1):
    return round(rng.uniform(lo, hi), digits)


# ------------------------------------------------------------------- incident-triage (U1)

ASSETS = ["conveyor drive 3", "compressor-2", "chiller 1", "boiler B", "mixer 4", "kiln 2", "extruder 1",
          "hydraulic press 2", "freezer room 2", "packaging line 5", "fan coil unit 7", "CNC spindle 3",
          "blower 2", "palletiser 1", "dryer 3", "cooling tower 1", "AHU-4", "pump station 2", "grinder 6",
          "oven line 2", "filler 3", "gearbox G2", "heat exchanger HX-3", "vacuum pump 1", "rotary valve 5"]
UNITS = ["gw-07", "plc-12", "rtu-3", "edge-node-4", "modbus gateway 2", "sensor hub 9", "tracker-21",
         "meter M-14", "logger-6", "camera-3", "lora gateway 1", "hmi-2"]


def incident(rng):
    a, u = pick(rng, ASSETS), pick(rng, UNITS)
    t = num(rng, 60, 140, 0)
    lim = t - num(rng, 3, 25, 0)
    by_cause = {
        "thermal": [
            f"{a}: motor temperature {t:.0f} °C, limit {lim:.0f} °C",
            f"Bearing temperature on {a} at {t:.0f} °C and still climbing",
            f"Overtemperature trip on {a}",
            f"{a} enclosure at {num(rng, 45, 70, 0):.0f} °C, cabinet cooling fan stopped",
            f"High discharge temperature on {a}: {t:.0f} °C against a {lim:.0f} °C limit",
            f"Oil temperature on {a} {t:.0f} °C, {t - lim:.0f} °C over the alarm level",
            f"{a}: coolant return {num(rng, 30, 45, 0):.0f} °C, cooling capacity not keeping up",
            f"Freezer temperature {num(rng, -12, -5, 1)} °C, setpoint -20 °C, warming for {rng.randint(15, 90)} min",
            f"Thermal overload: winding temperature {t:.0f} °C on {a}",
            f"{a} running hot, surface temperature {t:.0f} °C",
            f"Heat exchanger outlet {num(rng, 70, 95, 0):.0f} °C on {a}, cooling water flow lost",
        ],
        "mechanical": [
            f"Vibration on {a} at {num(rng, 6, 15)} mm/s RMS, alarm {num(rng, 4, 6)} mm/s",
            f"{a}: belt slipping, speed mismatch between drive and driven pulley",
            f"Oil leak under {a}, level falling",
            f"Seal leak on {a}, fluid on the floor",
            f"{a}: bearing noise and rising vibration on the drive end",
            f"Filter blocked on {a}, differential pressure {num(rng, 1, 3)} bar",
            f"Shaft misalignment detected on {a}",
            f"{a}: jam detected, product stuck at the transfer point",
            f"Cracked weld found on the frame of {a}",
            f"Coupling failure on {a}, motor runs but the load does not turn",
            f"Cavitation noise on {a}, suction strainer clogged",
            f"{a}: gearbox knocking, metal particles in the oil",
            f"Worn chain on {a}, elongation over 3 %",
        ],
        "electrical": [
            f"Phase loss on {a}, L{rng.randint(1, 3)} missing",
            f"Undervoltage on {a}: {rng.randint(170, 200)} V on a 230 V supply",
            f"Overcurrent trip on {a}, {num(rng, 30, 90, 0):.0f} A",
            f"Breaker Q{rng.randint(1, 30)} tripped, {a} without power",
            f"Fuse F{rng.randint(1, 20)} blown on the {a} control circuit",
            f"VFD fault on {a}: overcurrent during acceleration",
            f"Earth fault detected on {a} motor circuit",
            f"Mains failure, UPS for {a} running on battery",
            f"{a}: contactor K{rng.randint(1, 9)} failed to close",
            f"Motor drive overload on {a}, drive stopped",
            f"Voltage dip to {rng.randint(150, 190)} V, {a} restarted",
            f"Power supply 24 V DC failed in the {a} panel",
            f"Relay chatter on {a}, supply unstable",
        ],
        "connectivity": [
            f"{u} offline for {rng.randint(5, 120)} minutes",
            f"{u}: MQTT broker unreachable, connection timed out",
            f"Modbus timeout reading {a} through {u}",
            f"{u} missed {rng.randint(3, 12)} heartbeats",
            f"Lost LTE connection on {u}",
            f"{u}: TCP connection refused by 10.{rng.randint(0, 9)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}",
            f"Packet loss {rng.randint(20, 90)} % on the link to {u}",
            f"{u} cannot resolve the broker hostname",
            f"No data from {u} since {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
            f"Network switch port for {u} went down",
            f"OPC UA session to {u} closed by the server",
            f"{u}: Wi-Fi signal lost, device disconnected",
        ],
        "sensor_fault": [
            f"Temperature on {a} stuck at {num(rng, 10, 30)} °C for {rng.randint(3, 48)} hours",
            f"Implausible reading from {u}: {pick(rng, ['-40.0 °C', '6553.5 bar', '-999', '850 °C in a cold room'])}",
            f"{u}: probe disconnected, open circuit on input {rng.randint(1, 8)}",
            f"Low battery on {u}: {rng.randint(3, 15)} %",
            f"Pressure transmitter on {a} drifting {num(rng, 3, 12)} % from the reference gauge",
            f"{u} reports NaN for {pick(rng, ['humidity', 'flow', 'level', 'pressure', 'temperature'])}",
            f"Level sensor on {a} jumps between 0 and 100 %",
            f"Missing readings from {u}: {rng.randint(20, 80)} % of samples empty",
            f"{u}: calibration overdue, readings out of tolerance",
            f"Two thermocouples on {a} disagree by {rng.randint(15, 60)} °C",
            f"Flow meter on {a} reads zero while the pump runs",
            f"Humidity sensor on {u} pegged at 100 %RH",
        ],
        "process": [
            f"Setpoint on {a} changed from {rng.randint(60, 90)} to {rng.randint(91, 130)} by an operator",
            f"Recipe mismatch on {a}: batch {rng.randint(100, 999)} loaded with the wrong recipe",
            f"Wrong raw material batch at {a}, moisture {rng.randint(15, 30)} %",
            f"Product out of spec on {a}: weight {rng.randint(480, 495)} g, target 500 g",
            f"Line speed on {a} changed manually to {rng.randint(10, 40)} m/min",
            f"Operator override active on {a}",
            f"Batch cycle time on {a} {rng.randint(20, 60)} % over target",
            f"{a} running without material, hopper empty",
            f"Cleaning cycle skipped on {a} before batch start",
            f"Dosing ratio on {a} off target: {rng.randint(105, 130)} %",
            f"Manual mode left on at {a} after the shift change",
            f"Fill level setpoint on {a} entered as {rng.randint(150, 300)} %",
        ],
        "unknown": [
            f"Alarm {rng.randint(100, 9999)}",
            f"Status code {rng.randint(1, 255)} from {u}",
            f"Event 0x{rng.randint(0, 0xFFFF):04X} on {u}",
            f"Check {a}",
            "Notification",
            f"Operator acknowledged alarm {rng.randint(1, 500)}",
            f"Daily report for {a} is ready",
            f"Backup of {u} completed",
            "This is a test message",
            f"Guard door opened on {a}",
            f"Visitor badge used at gate {rng.randint(1, 6)}",
            f"Planned shutdown of {a} at {rng.randint(18, 23)}:00",
            f"Software update scheduled for {u}",
            f"{u} restarted",
            f"Fire drill at {rng.randint(9, 16)}:00, no action needed",
            "Info",
            f"Ticket {rng.randint(1000, 9999)} updated",
            f"Light curtain interrupted on {a}",
            "Alert",
            f"Reminder: inspection of {a} next week",
        ],
    }
    return by_cause


# ------------------------------------------------------------------- operator-intake (U2)

ASSET_EN = {
    "pump-1": ["pump 1", "pump #1", "pump number 1", "pump one", "Pump 1", "P-1 pump"],
    "pump-2": ["pump 2", "pump #2", "pump number 2", "pump two", "Pump 2", "P-2 pump"],
    "pump-3": ["pump 3", "pump #3", "pump number 3", "pump three", "Pump 3", "P-3 pump"],
    "compressor-1": ["the compressor", "the air compressor", "compressor", "the main compressor"],
    "pump": ["the pump", "one of the pumps", "a pump", "that pump"],
}
ASSET_ES = {
    "pump-1": ["la bomba 1", "bomba 1", "la bomba número 1", "la bomba uno", "la bomba #1"],
    "pump-2": ["la bomba 2", "bomba 2", "la bomba número 2", "la bomba dos", "la bomba #2"],
    "pump-3": ["la bomba 3", "bomba 3", "la bomba número 3", "la bomba tres", "la bomba #3"],
    "compressor-1": ["el compresor", "el compresor de aire", "compresor", "el compresor principal"],
    "pump": ["la bomba", "una de las bombas", "una bomba", "esa bomba"],
}
FAULT_EN = ["{a} is leaking water", "{a} makes a loud rattling noise", "{a} keeps tripping",
            "{a} won't start", "{a} is overheating", "there's smoke coming from {a}",
            "{a} is shaking badly", "the pressure on {a} is way too low", "{a} stopped by itself",
            "{a} is dripping oil", "{a} smells burnt", "{a} is squealing", "{a} has a cracked housing",
            "{a} is running but not pumping", "{a} hums and does nothing"]
FAULT_ES = ["{a} está perdiendo agua", "{a} hace un ruido fuerte", "{a} se dispara a cada rato",
            "{a} no arranca", "{a} se está calentando mucho", "sale humo de {a}",
            "{a} vibra muchísimo", "{a} tiene muy poca presión", "{a} se paró sola",
            "{a} gotea aceite", "{a} huele a quemado", "{a} chirría", "{a} tiene la carcasa rota",
            "{a} funciona pero no bombea", "{a} zumba y no hace nada"]
STATUS_EN = ["is {a} running?", "what's the pressure on {a}?", "how is {a} doing?", "is {a} on right now?",
             "what's the temperature of {a}?", "can you tell me the status of {a}?", "is {a} back online?",
             "what is {a} reading at the moment?", "any alarms on {a}?", "how many hours has {a} run today?"]
STATUS_ES = ["¿{a} está funcionando?", "¿qué presión tiene {a}?", "¿cómo está {a}?", "¿{a} está prendida ahora?",
             "¿qué temperatura tiene {a}?", "¿me dices el estado de {a}?", "¿{a} ya volvió a funcionar?",
             "¿cuánto marca {a} ahora?", "¿hay alarmas en {a}?", "¿cuántas horas lleva {a} hoy?"]
MAINT_EN = ["please send someone to look at {a}", "we need a new seal for {a}", "schedule a service for {a}",
            "can a technician check {a} tomorrow?", "order a spare impeller for {a}", "{a} is due for its oil change",
            "book maintenance for {a} next week", "we need spare filters for {a}", "please grease {a}",
            "request a visit to replace the bearings on {a}"]
MAINT_ES = ["manden a alguien a revisar {a}", "necesitamos un sello nuevo para {a}", "programen un servicio para {a}",
            "¿puede venir un técnico a ver {a} mañana?", "pidan un impulsor de repuesto para {a}",
            "a {a} le toca el cambio de aceite", "agenden mantenimiento para {a} la próxima semana",
            "necesitamos filtros de repuesto para {a}", "por favor engrasen {a}",
            "soliciten una visita para cambiar los rodamientos de {a}"]
# Messages with no asset of the menu
NO_ASSET = {
    ("report_fault", "en"): ["the lights in the workshop keep flickering", "the roof is leaking near the entrance",
                             "the forklift charger is broken", "the main gate is stuck", "the break-room fridge died",
                             "the floor drain by line 2 is overflowing"],
    ("report_fault", "es"): ["las luces del taller parpadean", "hay una gotera en el techo de la entrada",
                             "se rompió el cargador del montacargas", "el portón principal está atascado",
                             "se murió el refrigerador del comedor", "el drenaje junto a la línea 2 se desborda"],
    ("status_request", "en"): ["is everything running normally?", "which machines are stopped right now?",
                               "what's the plant power use today?", "any active alarms?", "is the site online?",
                               "how is the night shift going?"],
    ("status_request", "es"): ["¿todo funciona normal?", "¿qué máquinas están paradas ahora?",
                               "¿cuánta energía lleva la planta hoy?", "¿hay alarmas activas?",
                               "¿el sitio está en línea?", "¿cómo va el turno de noche?"],
    ("maintenance_request", "en"): ["we need more cleaning supplies for the workshop",
                                    "please schedule the yearly fire extinguisher check",
                                    "can someone fix the door of the tool room?", "order new gloves for the team",
                                    "book the electrician for the panel inspection", "we need a ladder in hall B"],
    ("maintenance_request", "es"): ["necesitamos más artículos de limpieza para el taller",
                                    "programen la revisión anual de extintores",
                                    "¿alguien puede arreglar la puerta del pañol?", "pidan guantes nuevos para el equipo",
                                    "agenden al electricista para revisar el tablero", "necesitamos una escalera en la nave B"],
    ("other", "en"): ["thanks a lot!", "good night everyone", "see you on monday", "great job today team",
                      "haha true", "who parked in my spot?", "coffee is ready", "nice weekend all",
                      "anyone up for football later?", "sorry, wrong chat", "hello", "cheers"],
    ("other", "es"): ["¡muchas gracias!", "buenas noches a todos", "nos vemos el lunes", "buen trabajo hoy equipo",
                      "jaja cierto", "¿quién se estacionó en mi lugar?", "ya está el café", "buen fin de semana",
                      "¿alguien juega fútbol más tarde?", "perdón, chat equivocado", "hola", "salud"],
}
THANKS_EN = ["thanks for fixing {a}!", "{a} works great now, thanks", "nice work on {a} yesterday"]
THANKS_ES = ["¡gracias por arreglar {a}!", "{a} anda perfecto ahora, gracias", "buen trabajo con {a} ayer"]
# Near misses (ft2): they name a machine, or ask something, and still ask nothing of the menu
NEAR_EN = ["{a} was repaired last week, just so you know", "fun fact: {a} is older than me",
           "I took a photo of {a} for the newsletter", "the new guy asked what {a} does, I explained",
           "{a} looks really clean after the painting", "remember when {a} flooded the hall? good times",
           "the visitors liked the tour of {a}", "{a} got a new label sticker, looks nice"]
NEAR_ES = ["{a} se reparó la semana pasada, para que sepan", "dato curioso: {a} es más vieja que yo",
           "le saqué una foto a {a} para el boletín", "el nuevo preguntó para qué sirve {a}, ya le expliqué",
           "{a} quedó muy limpia después de la pintura", "¿se acuerdan cuando {a} inundó la nave? qué tiempos",
           "a las visitas les gustó el recorrido por {a}", "{a} tiene una etiqueta nueva, se ve bien"]
NEAR_OTHER = {
    "en": ["does anyone have a phone charger?", "where do we sign the holiday sheet?",
           "is the parking lot open on sunday?", "can someone lend me a pen?", "what's the wifi password for guests?",
           "did anyone see my jacket?", "how do I change my shift with someone?", "is the canteen card working for you?",
           "noted", "got it", "roger that", "sure thing", "will do", "on my way", "lol", "?"],
    "es": ["¿alguien tiene un cargador de teléfono?", "¿dónde se firma la hoja de vacaciones?",
           "¿el estacionamiento abre el domingo?", "¿alguien me presta una lapicera?",
           "¿cuál es la clave del wifi de invitados?", "¿alguien vio mi chaqueta?",
           "¿cómo cambio mi turno con alguien?", "¿a ustedes les funciona la tarjeta del comedor?",
           "anotado", "entendido", "recibido", "dale", "de una", "voy en camino", "jajaja", "¿?"],
}
OPEN_EN = ["", "hi, ", "hey team, ", "morning, ", "quick one: ", "urgent: "]
OPEN_ES = ["", "hola, ", "buenas, ", "buen día, ", "una consulta: ", "urgente: "]


def cap(text):
    return text[:1].upper() + text[1:]


def intake(rng):
    """(state text, expected, lang) rows, with the menus' asset keys and intents crossed."""
    rows = []
    for lang, assets, opens, by_intent, thanks, near in (
            ("en", ASSET_EN, OPEN_EN, {"report_fault": FAULT_EN, "status_request": STATUS_EN,
                                       "maintenance_request": MAINT_EN}, THANKS_EN, NEAR_EN),
            ("es", ASSET_ES, OPEN_ES, {"report_fault": FAULT_ES, "status_request": STATUS_ES,
                                       "maintenance_request": MAINT_ES}, THANKS_ES, NEAR_ES)):
        for intent, templates in by_intent.items():
            for key, names in assets.items():
                for _ in range(14 if key != "pump" else 10):
                    text = pick(rng, opens) + pick(rng, templates).format(a=pick(rng, names))
                    rows.append((cap(text), {"intent": intent, "asset": key}, lang))
            for _ in range(12):
                rows.append((cap(pick(rng, opens) + pick(rng, NO_ASSET[(intent, lang)])),
                             {"intent": intent, "asset": "none"}, lang))
        for _ in range(60):
            text = pick(rng, NO_ASSET[("other", lang)]) + pick(rng, ["", "", "!", " 😀", " 👍", " :)", "!!"])
            rows.append((cap(text), {"intent": "other", "asset": "none"}, lang))
        for key in ("pump-1", "pump-2", "pump-3", "compressor-1"):
            for _ in range(3):
                rows.append((cap(pick(rng, thanks).format(a=pick(rng, assets[key]))),
                             {"intent": "other", "asset": key}, lang))
            for _ in range(6):
                rows.append((cap(pick(rng, opens[:4]) + pick(rng, near).format(a=pick(rng, assets[key]))),
                             {"intent": "other", "asset": key}, lang))
        for _ in range(40):
            rows.append((cap(pick(rng, opens[:4]) + pick(rng, NEAR_OTHER[lang])),
                         {"intent": "other", "asset": "none"}, lang))
    return rows


# ------------------------------------------------------------------- device-class (U4)

FIELDS = {
    "environment": ["temperature °C", "temp_c", "air_temp °C", "humidity %RH", "rh %", "hum", "co2 ppm",
                    "eco2 ppm", "voc ppb", "tvoc ppb", "pm2_5 µg/m³", "pm10 µg/m³", "light lux", "lux",
                    "soil_moisture %", "soil_temp °C", "pressure hPa", "baro_hpa", "dew_point °C", "uv_index",
                    "wind_speed m/s", "rain mm"],
    "energy": ["voltage V", "v_l1 V", "v_l2 V", "v_l3 V", "current A", "i_a A", "active_power W", "power kW",
               "energy kWh", "kwh_total", "power_factor", "pf", "frequency Hz", "reactive_power var",
               "apparent_power VA", "thd_v %", "demand kW"],
    "vibration": ["accel_x g", "accel_y g", "accel_z g", "vel_rms mm/s", "velocity mm/s", "peak_g", "rpm",
                  "crest_factor", "kurtosis", "fft_bins", "spectrum", "displacement µm", "vib_rms g",
                  "bearing_temp °C"],
    "flow_pressure": ["flow l/min", "flow_rate m³/h", "flow gpm", "pressure bar", "pressure psi",
                      "inlet_pressure bar", "outlet_pressure bar", "dp kPa", "totaliser m³", "line_pressure psi",
                      "volume_flow l/s"],
    "level": ["level %", "fill %", "distance mm", "distance_cm", "tank_level m", "water_level m",
              "silo_fill %", "ullage mm", "volume l", "height_mm"],
    "location": ["lat", "lon", "latitude", "longitude", "sats", "satellites", "speed km/h", "heading °",
                 "hdop", "altitude m", "gps_fix", "course °"],
    "vision": ["label", "detections", "bbox", "confidence", "score", "frame_id", "fps", "class",
               "person_count", "track_id", "objects", "inference_ms"],
}
GENERIC = ["value", "val", "status", "data", "uptime s", "rssi dBm", "snr dB", "firmware", "fw_version",
           "counter", "ts", "timestamp", "battery %", "heartbeat", "payload", "state", "reading", "id",
           "seq", "msg", "raw", "ch1", "ch2", "input_1"]


def device(rng):
    by = {}
    for kind, pool in FIELDS.items():
        rows = []
        for _ in range(200):
            fields = rng.sample(pool, rng.randint(1, min(4, len(pool))))
            if rng.random() < 0.3:
                fields.append(pick(rng, ["battery %", "rssi dBm", "uptime s", "ts"]))
            rng.shuffle(fields)
            rows.append(", ".join(fields))
        by[kind] = rows
    by["unknown"] = [", ".join(rng.sample(GENERIC, rng.randint(1, 3))) for _ in range(200)]
    return by


# ------------------------------------------------------------------- log-triage (U5)

HOSTS = ["influxdb", "mqtt", "p4n4-n8n", "grafana", "letta", "api.example.net", "ntp.pool.org", "gw-07.local"]
PREFIX = ["", "", "{d}T{t}Z ERROR ", "{d} {t} [error] ", "app[{p}]: ", "systemd[1]: ", "node-red[{p}]: ",
          "kernel: ", "level=error ", "E{md} {t}.{ms} {p} main.go:{ln}] "]


def ip(rng):
    return "%d.%d.%d.%d" % (pick(rng, [10, 172, 192]), rng.randint(0, 255), rng.randint(0, 255), rng.randint(2, 254))


def logs(rng):
    h, p = pick(rng, HOSTS), rng.randint(100, 32000)
    port = pick(rng, [1883, 8086, 5678, 3000, 443, 502, 8000])
    path = pick(rng, ["/data/flows.json", "/var/lib/app/state.db", "/etc/app/app.yaml", "/srv/export.csv"])
    return {
        "network": [f"connect ETIMEDOUT {ip(rng)}:{port}", f"getaddrinfo ENOTFOUND {h}",
                    "read ECONNRESET: connection reset by peer", f"dial tcp {ip(rng)}:{port}: connect: no route to host",
                    f"lookup {h} on 127.0.0.11:53: server misbehaving", "net/http: TLS handshake timeout",
                    "Error: socket hang up", f"eth{rng.randint(0, 1)}: carrier lost, link down",
                    f"failed to connect to {h}:{port}: Connection refused",
                    f"request to http://{h}:{port}/ failed, reason: connect EHOSTUNREACH"],
        "auth": [f"401 Unauthorized: invalid API key for {h}", "403 Forbidden: insufficient permissions",
                 "Permission denied (publickey).", f"password authentication failed for user \"{pick(rng, ['admin', 'p4n4', 'grafana', 'postgres'])}\"",
                 "error: access token expired", f"EACCES: permission denied, open '{path}'",
                 f"Access denied for user 'app'@'{ip(rng)}'", "mqtt: connection refused, not authorized",
                 "login failed: wrong username or password", "jwt: signature is invalid"],
        "disk": [f"ENOSPC: no space left on device, write '{path}'", f"I/O error, dev mmcblk0, sector {rng.randint(10000, 9999999)}",
                 f"cannot write {path}: Read-only file system", "EXT4-fs error (device sda1): ext4_find_entry: reading directory lblock 0",
                 "Disk quota exceeded", "SMART error: reallocated sector count above threshold",
                 f"Buffer I/O error on dev sdb{rng.randint(1, 3)}, logical block {rng.randint(100, 99999)}",
                 f"database disk image is malformed: {path}", "filesystem /var is 100% full",
                 "blk_update_request: critical medium error"],
        "memory": [f"Out of memory: Killed process {p} (node)", "Container exited: OOMKilled",
                   "fork: Cannot allocate memory", "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory",
                   "MemoryError: unable to allocate array", "java.lang.OutOfMemoryError: Java heap space",
                   "oom-kill: constraint=CONSTRAINT_MEMCG, task=python3", "malloc(): failed to allocate 268435456 bytes",
                   f"influxd invoked oom-killer: gfp_mask=0x100cca, order=0", "runtime: out of memory: cannot allocate 1048576-byte block"],
        "crash": ["Segmentation fault (core dumped)", "panic: runtime error: index out of range [3] with length 3",
                  "Unhandled exception: TypeError: Cannot read properties of undefined (reading 'payload')",
                  f"app.service: Main process exited, code=dumped, status=11/SEGV",
                  "terminate called after throwing an instance of 'std::runtime_error'", "fatal error: concurrent map writes",
                  f"Process {p} exited with code 134 (SIGABRT)", "Traceback (most recent call last): ZeroDivisionError: division by zero",
                  "uncaughtException: RangeError: Maximum call stack size exceeded", "*** stack smashing detected ***: terminated"],
        "config": [f"invalid configuration: unknown key \"{pick(rng, ['listner', 'retention_hours', 'tls_mode', 'brokr'])}\"",
                   f"yaml: line {rng.randint(2, 80)}: mapping values are not allowed in this context",
                   f"missing required setting {pick(rng, ['INFLUXDB_TOKEN', 'MQTT_HOST', 'N8N_ENCRYPTION_KEY', 'DATABASE_URL'])}",
                   f"failed to parse {path}: unexpected token at line {rng.randint(1, 50)}",
                   f"invalid value \"{pick(rng, ['yes please', '-5', 'abc', '99999'])}\" for option --{pick(rng, ['port', 'interval', 'workers'])}",
                   "mosquitto: Error: Unknown configuration variable \"listner\"", "nginx: [emerg] unknown directive \"proxy_pas\"",
                   "config error: port must be a number between 1 and 65535",
                   f"environment variable {pick(rng, ['GF_SECURITY_ADMIN_PASSWORD', 'LETTA_PG_URI', 'TZ'])} is not set",
                   "settings.js: SyntaxError: Unexpected identifier"],
        "unknown": ["Error", "failed", "exit status 1", "something unexpected happened", f"ERROR code {rng.randint(2, 999)}",
                    "operation failed", f"job {p} failed", "unexpected error, see logs", f"E{rng.randint(1000, 9999)}",
                    "fatal: aborting", "an error was reported", f"step {rng.randint(1, 9)} failed"],
        "info": [f"Started {pick(rng, ['flows', 'app.service', 'the scheduler'])}", f"Connected to {h}:{port}",
                 f"Listening on 0.0.0.0:{port}", "Time synchronised with NTP server", "Backup finished in 12 s",
                 "Reloaded configuration"],
    }


def log_line(rng, msg):
    d = "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28))
    t = "%02d:%02d:%02d" % (rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))
    prefix = pick(rng, PREFIX).format(d=d, t=t, p=rng.randint(100, 32000), md=d[5:].replace("-", ""),
                                      ms=rng.randint(100000, 999999), ln=rng.randint(10, 900))
    return prefix + msg


# ------------------------------------------------------------------- system2-router (U3)

PLACES = ["the cold room", "zone 3", "line 2", "the greenhouse", "the boiler room", "warehouse B", "tank 4",
          "the north field", "the server room", "hall C"]
THINGS = ["the chiller", "pump 4", "the conveyor", "the generator", "the air handler", "boiler 2", "the dryer",
          "the CNC mill", "the fans", "the main panel"]


def router(rng):
    pl, th = pick(rng, PLACES), pick(rng, THINGS)
    return {
        "none": [f"What's the humidity in {pl} now?", f"Is {th} switched on?", f"Current power draw of {th}?",
                 f"Show the live temperature of {pl}.", "List the devices that are online.",
                 f"What does the level sensor in {pl} read?", f"Which alarms are active in {pl}?",
                 f"Give me the current speed of {th}.", f"Is {th} in alarm?", f"How full is {pl} right now?",
                 f"Status of {th}?", f"What's the CO2 in {pl} at the moment?"],
        "ollama": [f"Explain what a high crest factor on {th} means.", f"Summarise this shift note: {th} stopped twice, restarted fine.",
                   f"Translate to Spanish: {th} is out of order until Monday.", f"Draft a message to the supplier about a broken part on {th}.",
                   f"How should I clean the filters of {th}?", f"Write a short safety reminder for {pl}.",
                   f"What could cause {th} to vibrate more than usual?", "Explain the difference between RMS and peak vibration.",
                   f"Give me tips to cut the energy use of {th}.", f"Write a checklist for starting up {th}.",
                   "Summarise the main risks of running a pump dry.", f"Advise me on how to store spare parts for {th}."],
        "letta": [f"What did we decide last week about {th}?", f"Remind me to check {th} on Friday.",
                  f"Remember that {th} was serviced today.", f"Last time {th} tripped, what fixed it?",
                  f"Follow up on what I asked you yesterday about {pl}.", f"Did anyone report problems with {th} last month?",
                  f"Note for later: {pl} needs new lighting.", f"What did I tell you about the setpoint in {pl}?",
                  f"Keep in mind that {th} is under warranty until March.", f"How often has {th} failed this year?",
                  f"Any updates on the issue we discussed this morning about {th}?", f"When did we last replace the belts on {th}?"],
        "unknown": [noise(rng) for _ in range(12)],
    }


def noise(rng):
    """Nothing to answer: chat fillers, emoji, keyboard mash."""
    kind = rng.randrange(4)
    if kind == 0:
        return pick(rng, ["lol", "ok thx", "hmm ok", "zzz", "yo", "nvm", "yes", "no", "sure", "k thx", "brb",
                          "omg", "haha", "ups", "lmao", "kk", "sí", "vale", "ajá", "fine"])
    if kind == 1:
        return "".join(pick(rng, ["👍", "🙂", "😂", "🔥", "✅", "🙏", "👀", "🤔"]) for _ in range(rng.randint(1, 3)))
    if kind == 2:
        return "".join(rng.choice("asdfghjklqwertyuiopzxcvbnm") for _ in range(rng.randint(3, 9)))
    return pick(rng, ["test", "testing", "abc", "123", "xyz", "foo bar", "ping"]) + pick(rng, ["", " 1", " 2", "!!", " ..."])


# ------------------------------------------------------------------- anomaly-screen (U6)

METRICS = [("temperature", "°C", 2, 40), ("pressure", "bar", 1, 10), ("vibration RMS", "mm/s", 0.5, 8),
           ("current", "A", 2, 60), ("humidity", "%", 20, 90), ("flow", "l/min", 5, 200), ("level", "%", 5, 95),
           ("power", "kW", 1, 80), ("CO2", "ppm", 400, 1500)]
WHERE = ["freezer 3", "pump 4", "line 2", "tank 1", "the greenhouse", "boiler B", "compressor 2", "hall C",
         "the server room", "fan 6"]


def anomaly(rng):
    m, unit, lo, hi = pick(rng, METRICS)
    w = pick(rng, WHERE)
    a = num(rng, lo, (lo + hi) / 2)
    b = num(rng, (lo + hi) / 2, hi * 1.5)
    head = f"{m}, {w}: "
    return {
        "explain": [head + f"jumped from {a} to {b} {unit} in {rng.randint(1, 10)} minutes and stayed there",
                    head + f"drifting up from {a} to {b} {unit} over {rng.randint(2, 14)} days, no sign of levelling off",
                    head + f"flat at exactly {a} {unit} for {rng.randint(6, 72)} hours",
                    head + f"reads {pick(rng, ['-273', '-999', '9999', '0.0 while running', 'negative'])} {unit}",
                    head + f"two sensors disagree by {round(abs(b - a), 1)} {unit} for the last {rng.randint(1, 12)} hours",
                    head + f"dropped to {a} {unit} while the related readings stayed normal",
                    head + f"daily cycle gone: no change between day and night for {rng.randint(2, 7)} days",
                    head + f"step change from {a} to {b} {unit} after a restart, not back since",
                    head + f"oscillating between {a} and {b} {unit} every {rng.randint(5, 60)} seconds since this morning",
                    head + f"slow decline from {b} to {a} {unit} over {rng.randint(3, 20)} days",
                    head + f"{rng.randint(4, 15)} spikes to {b} {unit} in the last hour, none before"],
        "routine": [head + f"follows its usual daily cycle between {a} and {b} {unit}",
                    head + f"one spike to {b} {unit} for {rng.randint(5, 50)} seconds, then back to {a}",
                    head + f"small noise of ±{round((hi - lo) / 50, 2)} {unit} around {a} {unit}",
                    head + f"rose to {b} {unit} during the planned {pick(rng, ['defrost', 'cleaning cycle', 'start-up', 'test run', 'shutdown'])}, back to {a} after",
                    head + f"steady at {a} {unit} ± {round((hi - lo) / 40, 2)} for the whole week, as usual",
                    head + f"higher on weekdays than at weekends, {a} to {b} {unit}, like every week",
                    head + f"dipped to {a} {unit} during the scheduled maintenance window",
                    head + f"same pattern as the last {rng.randint(3, 10)} days, peaks at {b} {unit} at noon",
                    head + f"brief drop during the {rng.randint(1, 5)} s power switch-over, normal since",
                    head + f"gradual seasonal change of {round((hi - lo) / 20, 1)} {unit} over a month"],
    }


# ---------------------------------------------------------------------------------- build

def words(text):
    return set(re.findall(r"\w+", text.lower()))


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def load_set(name, questions_dir, drafts_dir):
    folder = questions_dir if SETS[name][0] == "questions" else drafts_dir
    spec = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
    evals = [json.loads(line) for line in (folder / f"{name}.eval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return spec, evals


def generated(name, rng):
    """(text, expected, lang) rows for one set, before the overlap filter."""
    count = SETS[name][2]
    if name == "operator-intake":
        return intake(rng)
    make = {"incident-triage": incident, "device-class": device, "log-triage": logs,
            "system2-router": router, "anomaly-screen": anomaly}[name]
    qid = {"incident-triage": "cause", "device-class": "device_type", "log-triage": "category",
           "system2-router": "route", "anomaly-screen": "worth"}[name]
    rows = []
    keys = list(make(rng))
    for key in keys:
        n = count if key != "info" else count // 4
        for _ in range(n * 3):
            if sum(1 for r in rows if r[1][qid] == key) >= n:
                break
            text = pick(rng, make(rng)[key])
            if name == "log-triage":
                text = log_line(rng, text)
            rows.append((text, {qid: key}, "en"))
    return rows


def build(questions_dir=QUESTIONS, drafts_dir=DRAFTS, seed=SEED):
    """`(rows, report)`: the corpus rows and, per set, what was generated, kept and dropped."""
    rng = random.Random(seed)
    out, report = [], {}
    for name, (_, field, _) in SETS.items():
        spec, evals = load_set(name, questions_dir, drafts_dir)
        held = [words(json.dumps(e["state"], ensure_ascii=False)) for e in evals]
        held_text = {e["state"].get(field, "").strip().lower() for e in evals}
        seen, kept, dropped, dupes = set(), 0, 0, 0
        for text, expected, lang in generated(name, rng):
            norm = text.strip().lower()
            if norm in seen:
                dupes += 1
                continue
            seen.add(norm)
            w = words(json.dumps({field: text}, ensure_ascii=False))
            if norm in held_text or any(jaccard(w, h) >= OVERLAP for h in held):
                dropped += 1
                continue
            for q, key in expected.items():
                if key not in spec["questions"][q]["criteria"]:
                    raise ValueError("%s: %r is not an option of %s" % (name, key, q))
            out.append({"state": {field: text}, "questions": spec["questions"], "expected": expected,
                        "set": name, "lang": lang})
            kept += 1
        report[name] = {"kept": kept, "dropped_near_eval": dropped, "duplicates": dupes,
                        "items": kept * len(spec["questions"])}
    rng.shuffle(out)
    return out, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--questions", type=Path, default=QUESTIONS)
    ap.add_argument("--drafts", type=Path, default=DRAFTS)
    args = ap.parse_args(argv)
    rows, report = build(args.questions, args.drafts, args.seed)
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    Path(args.out).write_text(text, encoding="utf-8")
    for name, r in report.items():
        print("%-16s %4d rows, %4d items, %3d dropped as near an eval example" % (name, r["kept"], r["items"], r["dropped_near_eval"]))
    print("%d rows, sha256 %s" % (len(rows), hashlib.sha256(text.encode()).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
