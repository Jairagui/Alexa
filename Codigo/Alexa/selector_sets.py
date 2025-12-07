def elegir_set(data, nivel, tipo, sobrepeso):
    # normalizo entradas 
    nivel = (nivel or "FACIL").upper()
    tipo  = (tipo  or "UPPER").upper()
    # Aceptar MEDIO como INTERMEDIO 
    if nivel == "MEDIO":
        nivel = "INTERMEDIO"

    sets = data.get("sets", {})
    # Construyo la clave directamente por patrón
    clave = f"{tipo}_{nivel}_{'SOBREPESO' if sobrepeso else 'NO_SOBREPESO'}"
    pasos = sets.get(clave)
    if not pasos:
        # Fallback 
        pasos = sets.get(f"{tipo}_FACIL_NO_SOBREPESO") or sets.get("UPPER_FACIL_NO_SOBREPESO", [])
    return list(pasos)
