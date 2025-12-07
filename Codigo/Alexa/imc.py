
def calc_imc_cm(peso_kg, estatura_cm):
    # IMC
    if peso_kg <= 0 or estatura_cm <= 0:
        return 0.0
    m = estatura_cm / 100.0
    return round(peso_kg / (m * m), 2)

def es_sobrepeso(imc):
    # regla para sobre peso
    return imc >= 25.0
