from imc import calc_imc_cm, es_sobrepeso
from rutina_creador import crear_rutina_desde_data

class RoutineFacade:
    def __init__(self, data, strategy=None):
        self.data = data
        self.strategy = strategy  # puede ser None

    def generar_rutina(self, nivel, tipo, peso, estatura_cm):
        imc = calc_imc_cm(peso, estatura_cm)
        sobre = es_sobrepeso(imc)  # solo para descansos 
        # Sin strategy
        if self.strategy is None:
            return crear_rutina_desde_data(self.data, nivel, tipo, sobre)

        #  elegir set y armar igual 
        warmup = self.data.get("warmup", [])
        cooldown = self.data.get("cooldown", [])
        set_main = self.strategy.elegir(self.data, nivel=nivel, tipo=tipo, sobrepeso=sobre)

        descanso = {"FACIL": 15, "INTERMEDIO": 20, "DIFICIL": 25}.get((nivel or "").upper(), 15)
        if sobre:
            descanso += 5

        pasos = list(warmup) + list(set_main) + list(cooldown)

        pasos_con_descanso = []
        for i, p in enumerate(pasos):
            pasos_con_descanso.append(p)
            if i < len(pasos) - 1:
                pasos_con_descanso.append({
                    "title": "Descanso",
                    "segundos": int(descanso),
                    "decir": "Hidrátate y respira."
                })

        return {"titulo": f"Rutina {tipo} {nivel}", "pasos": pasos_con_descanso}

    def duracion_estimada_seg(self, rutina):
        return sum(p.get("segundos", 0) for p in rutina.get("pasos", []))

    def formatear_resumen(self, rutina):
        total = self.duracion_estimada_seg(rutina)
        m, s = divmod(int(total), 60)
        return f"{rutina.get('titulo','Rutina')} — Pasos: {len(rutina.get('pasos', []))} — Duración aprox.: {m}m {s}s"
