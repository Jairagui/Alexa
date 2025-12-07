from selector_sets import elegir_set

def segundos_descanso(nivel, sobrepeso):
    nivel_texto = (nivel or "").upper()
    if nivel_texto == "FACIL":
        base = 15
    elif nivel_texto == "MEDIO":
        base = 20
    elif nivel_texto == "DIFICIL":
        base = 25
    else:
        base = 15

    # Si la persona tiene sobrepeso, se aumenta un poco el descanso
    if sobrepeso:
        base = base + 5

    return base

def insertar_descansos(pasos, descanso_s):
    out = []
    for i, p in enumerate(pasos):
        out.append(p)
        if i < len(pasos) - 1:
            out.append({
                "title": "Descanso",
                "segundos": int(descanso_s),
                "decir": "Hidrátate y respira."
            })
    return out

def crear_rutina_desde_data(data, nivel, tipo, sobrepeso):
    warmup = data.get("warmup", [])
    cooldown = data.get("cooldown", [])
    set_main = elegir_set(data, nivel=nivel, tipo=tipo, sobrepeso=sobrepeso)

    # Título sin exponer estado
    titulo = f"Rutina {tipo} {nivel}"

    pasos = list(warmup) + list(set_main) + list(cooldown)
    pasos = insertar_descansos(pasos, segundos_descanso(nivel, sobrepeso))

    return {"titulo": titulo, "pasos": pasos}
