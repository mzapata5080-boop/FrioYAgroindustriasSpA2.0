import re
from django.core.exceptions import ValidationError


def formatear_rut_chileno(value):
    rut = str(value).replace(".", "").replace("-", "").upper().strip()
    if not rut:
        return ""
    cuerpo, dv = rut[:-1], rut[-1]
    partes = []
    while cuerpo:
        partes.insert(0, cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    return ".".join(partes) + "-" + dv


def validar_rut_chileno(value):
    rut = str(value).upper().replace(".", "").replace("-", "").strip()
    if not re.match(r"^\d{7,8}[0-9K]$", rut):
        raise ValidationError("El RUT no tiene un formato válido (ej: 76132049-4).")
    
    cuerpo = rut[:-1]
    dv_ingresado = rut[-1]
    
    suma = 0
    multiplicador = 2
    
    for digit in reversed(cuerpo):
        suma += int(digit) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
        
    resto = suma % 11
    resultado = 11 - resto
    
    if resultado == 11:
        dv_esperado = "0"
    elif resultado == 10:
        dv_esperado = "K"
    else:
        dv_esperado = str(resultado)
        
    if str(dv_ingresado) != str(dv_esperado):
        raise ValidationError("El RUT ingresado no es válido.")