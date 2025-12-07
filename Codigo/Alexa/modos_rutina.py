import random

class SetSelectionStrategy:
    def elegir(self, data, nivel, tipo, sobrepeso):
        raise NotImplementedError


class SimpleKeyStrategy(SetSelectionStrategy):
    # Modo "manual": usa directamente la función elegir_set
    def __init__(self, elegir_set_func):
        self._elegir_set = elegir_set_func

    def elegir(self, data, nivel, tipo, sobrepeso):
        return self._elegir_set(data, nivel=nivel, tipo=tipo, sobrepeso=sobrepeso)


class RandomizedStrategy(SetSelectionStrategy):
    # Modo "random": baraja la lista de pasos
    def __init__(self, elegir_set_func):
        self._elegir_set = elegir_set_func

    def elegir(self, data, nivel, tipo, sobrepeso):
        pasos = list(self._elegir_set(data, nivel=nivel, tipo=tipo, sobrepeso=sobrepeso))
        # Usamos shuffle directo para que se vea más sencillo
        random.shuffle(pasos)
        return pasos


def crear_strategy(modo, elegir_set_func, seed=None):
    # Según el modo, devolvemos una estrategia u otra.
    # El parámetro seed se ignora aquí, pero se deja en la firma
    modo_limpio = (modo or "").strip().lower()
    if modo_limpio == "manual":
        return SimpleKeyStrategy(elegir_set_func)
    # Por defecto, usamos la estrategia aleatoria
    return RandomizedStrategy(elegir_set_func)
