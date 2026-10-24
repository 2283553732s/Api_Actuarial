
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import pandas as pd

app = FastAPI()
mortalidad = pd.read_csv("tabla_mortalidad.csv")
polizas = {}

@app.get("/cartera")
def mostrar_cartera ():
    return polizas

def calcular(edad, sa, i, fumador=False, phi=0):
    datos = mortalidad[mortalidad.edad >= edad].sort_values("edad")
    if datos.empty or datos.iloc[0].edad != edad:
        raise HTTPException(404, "Edad no encontrada")

    q = datos["qx_fumador" if fumador else "qx_no_fumador"].tolist()
    v=1/(1+i)
    supervivencia=1
    A=0
    a=0

    for k, qx in enumerate(q):
        qx = min(qx * (1 + phi), 1)
        A += v ** (k + 1) * supervivencia * qx
        a += v ** k * supervivencia
        supervivencia *= 1 - qx

    return {"Ax": A, "ax": a, "prima": sa * A / a}


class Cotizacion(BaseModel):
    edad: int
    sexo: str
    suma_asegurada: float
    tasa_interes: float
    es_fumador: bool = False


class Actualizar(BaseModel):
    edad: int
    suma_asegurada: float
    tasa_interes: float
    años_transcurridos: int


class Ajustar(BaseModel):
    es_fumador: Optional[bool] = None
    phi: float = 0


@app.get("/", response_class=HTMLResponse)
def inicio():
    return '<h1>Práctica actuarial</h1><a href="/docs">Documentación</a>'


@app.post("/cotizaciones")
def cotizar(d: Cotizacion):
    r = calcular(d.edad, d.suma_asegurada, d.tasa_interes, d.es_fumador)
    id = len(polizas) + 1
    polizas[id] = {**d.model_dump(),
                    "prima": r["prima"],

                   "años_transcurridos": 0,
                    "estado": "ACTIVA"}
    return {"id_poliza": id, **r}


@app.put("/polizas/{id}")
def actualizar(id: int, d: Actualizar):         ## Si funciona
    if id not in polizas:
        raise HTTPException(404, "Póliza no encontrada")
    p = polizas[id]
    r = calcular(d.edad, d.suma_asegurada, d.tasa_interes, p["es_fumador"])
    reserva = d.suma_asegurada * r["Ax"] - p["prima"] * r["ax"]
    p.update(d.model_dump(), prima=r["prima"])
    return {"reserva": reserva, **r}


@app.patch("/asegurados/{id}")
def ajustar(id: int, d: Ajustar):
    if id not in polizas:
        raise HTTPException(404, "Asegurado no encontrado")

    a = polizas[id]
    fumador = d.es_fumador if d.es_fumador is not None else a["es_fumador"]
    a["es_fumador"] = fumador

    return calcular(
        int(a["edad"]),
        float(a["suma_asegurada"]),
        0.05,
        fumador,
        d.phi
    )

@app.delete("/polizas/{id}")
def cancelar(id: int):

    if id not in polizas:
        raise HTTPException(404, "Póliza no encontrada")
    
    p = polizas[id]
    r = calcular(p["edad"], p["suma_asegurada"], p["tasa_interes"], p["es_fumador"])
    t = p["años_transcurridos"]
    reserva = max(0, p["suma_asegurada"] * r["Ax"] - p["prima"] * r["ax"])
    penalizacion = max(0, 0.20 - 0.02 * t)
    p["estado"] = "CANCELADA"
    return {"reserva": reserva, "penalizacion": penalizacion,
            "valor_rescate": reserva * (1 - penalizacion)}
