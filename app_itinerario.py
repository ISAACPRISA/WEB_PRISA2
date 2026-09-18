import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
import folium
import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
import calendar
import re
import os
import urllib.parse 

# =============================================================================
# 0. CONFIGURACIÓN DE APIS Y EXTRACCIÓN DE GASOLINA (CACHÉ 24 HORAS)
# =============================================================================
MAPBOX_TOKEN = "pk.eyJ1Ijoia2FyZW5tYWNpYXMxIiwiYSI6ImNtcWlma2pzODA2bW4ycG9hdjI0MjBiZ20ifQ.7NURZ9JkaPZ49hWRhfSDOg" 
MAPBOX_STYLE = "streets-v12" 

VENDEDORES_AUTORIZADOS = [
    "MEDINA VAZQUEZ ERIKA", "CUADRAS CANO CARLOS ARMANDO", "MASCORRO ZAPATA EDGAR",
    "ONTIVEROS ARAUJO IRAM ELEAZAR", "SIDA RAYGOZA IRIS SARAHI", "RAMOS RUIZ YAZMIN GUADALUPE",
    "CABRERA GUTIERREZ ANGEL", "MOJICA CORTES FRANCISCO JAVIER", "PONCE LOMELI PEDRO ALEJANDRO",
    "ORDOÑEZ GUIZAR JOSE GUADALUPE", "BUENO MITRE JUAN CARLOS", "RAMIREZ GAMBOA JOSUE",
    "MORENO HERNANDEZ FRANCISCO JAVIER", "OCHOA MORA ALEJANDRO JAVIER", "RODRIGUEZ AGUIRRE JOSE",
    "MEZA LEON JUAN", "FERNANDEZ SORIANO VICTOR ISIDRO", "RODRIGUEZ MARTINEZ MIGUEL ANGEL MOISES",
    "ESCOBAR AGUIRRE JUAN FRANCISCO", "GARCIA SOTO HEIDI GRACIELA", "JIMENEZ CARRILLO CHRISTIAN EDUARDO",
    "VACANTE CHIHUAHUA", "LOYA ROBLEDO ANTONIO", "FIERRO MARTINEZ JOSE", "SANCHEZ MOJICA PAMELA",
    "VACANTE LAGUNA", "ESPIRITU TLATEMPA JAVIER", "GOMEZ GONZALEZ MARVIN GEOVANNY",
    "HERNANDEZ CARMONA EDGAR GABRIEL", "CISNEROS HERNANDEZ JOSE ANDRES", "IZAGUIRRE ECHAVARRIA ERI GUADALUPE",
    "MOSTRADOR TIJUANA", "SALDAÑA GONZALEZ MOISES", "PARRA MUÑOZ PEDRO EMANUEL",
    "INACTIVOS FERRETEROS OCCIDENTE", "ORTEGA CHAROLA MARCOS DE JESUS"
]

@st.cache_data(ttl=86400)  

#_____________________________________________________________________________________________________________
#GOOGLE MAPS
def generar_link_google_maps(lista_coordenadas):
    if not lista_coordenadas or len(lista_coordenadas) == 0:
        return "#"
    
    # Tomamos el primer punto como origen y el último como destino
    origen = f"{lista_coordenadas[0][0]},{lista_coordenadas[0][1]}"
    destino = f"{lista_coordenadas[-1][0]},{lista_coordenadas[-1][1]}"
    
    # Si hay paradas intermedias, las unimos con una barra "|"
    if len(lista_coordenadas) > 2:
        intermedios = [f"{lat},{lon}" for lat, lon in lista_coordenadas[1:-1]]
        waypoints = "|".join(intermedios)
        url = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}&waypoints={urllib.parse.quote(waypoints)}&travelmode=driving"
    else:
        url = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}&travelmode=driving"
        
    return url

#_________________________________________________________________________________________________________________________

def extraer_precio_gasolina_real():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get("https://petrointelligence.com/precios-de-la-gasolina-y-diesel-hoy.php", headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        jalisco_element = soup.find(string=re.compile(r"Precios promedio reportados de.*Jalisco", re.IGNORECASE))
        if jalisco_element:
            parent_table = jalisco_element.find_parent('table')
            if parent_table:
                tds = parent_table.find_all('td')
                for td in tds:
                    texto = td.text.strip()
                    if "$" in texto and "." in texto:
                        precio_limpio = texto.replace('$', '').strip()
                        return float(precio_limpio)
    except Exception:
        pass
    return 24.25  

def desduplicar_columnas(df):
    if df is None or df.empty:
        return df
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

def cargar_dataframe_flexible(file_input, nombre_defecto="", sheet_name=0):
    if file_input is None:
        return None
    try:
        if isinstance(file_input, str):
            if os.path.exists(file_input):
                df = pd.read_excel(file_input, sheet_name=sheet_name)
            else:
                return None
        else:
            df = pd.read_excel(file_input, sheet_name=sheet_name)
        df.columns = df.columns.astype(str).str.strip()
        return desduplicar_columnas(df)
    except Exception:
        return None

def homologar_columna_cliente(df):
    if df is None:
        return None
    for col in df.columns:
        if re.search(r"c[oó]digo[_\s]*de[_\s]*cliente|cod[_\s]*cliente|id[_\s]*cliente", col, re.IGNORECASE):
            df.rename(columns={col: "ID_Cliente"}, inplace=True)
            break
    if "ID_Cliente" in df.columns:
        df["ID_Cliente"] = df["ID_Cliente"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return df

# =============================================================================
# 1. PROCESAMIENTO DE DATOS MAESTROS
# =============================================================================
def procesar_datos_maestros(file_clientes, file_vendedores):
    df_clientes = pd.read_excel(file_clientes)
    df_vendedores = pd.read_excel(file_vendedores)
    
    df_clientes.columns = df_clientes.columns.str.strip().str.replace('\n', ' ')
    df_vendedores.columns = df_vendedores.columns.str.strip().str.replace('\n', ' ')
    
    if 'Nombre' in df_vendedores.columns:
        df_vendedores = df_vendedores[df_vendedores['Nombre'].str.upper().str.strip().isin([v.upper() for v in VENDEDORES_AUTORIZADOS])].reset_index(drop=True)
    
    if 'Domicilio' in df_clientes.columns:
        df_clientes['Domicilio'] = df_clientes['Domicilio'].fillna('Sin Domicilio Registrado').astype(str).str.strip()
    else:
        if len(df_clientes.columns) >= 11:
            df_clientes.rename(columns={df_clientes.columns[10]: 'Domicilio'}, inplace=True)
            df_clientes['Domicilio'] = df_clientes['Domicilio'].fillna('Sin Domicilio Registrado').astype(str).str.strip()
        else:
            df_clientes['Domicilio'] = 'Columna K No Encontrada'

    for col in ['ID_Vendedor', 'ID_Cliente']:
        if col in df_clientes.columns:
            df_clientes[col] = df_clientes[col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            
    if 'ID_Vendedor' in df_vendedores.columns:
        df_vendedores['ID_Vendedor'] = df_vendedores['ID_Vendedor'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    col_meses_nombre = None
    for c in df_clientes.columns:
        if 'Meses de venta' in c:
            col_meses_nombre = c
            break
            
    if col_meses_nombre and 'Ventas_anuales' in df_clientes.columns:
        df_clientes['Venta_Mensual_Calculada'] = df_clientes['Ventas_anuales'] / df_clientes[col_meses_nombre].replace(0, 1)
    elif len(df_clientes.columns) >= 10 and 'Ventas_anuales' in df_clientes.columns:
        df_clientes['Venta_Mensual_Calculada'] = df_clientes['Ventas_anuales'] / df_clientes[df_clientes.columns[9]].replace(0, 1)
    elif 'Ventas_anuales' in df_clientes.columns:
        df_clientes['Venta_Mensual_Calculada'] = df_clientes['Ventas_anuales'] / 12
    else:
        df_clientes['Venta_Mensual_Calculada'] = 0.0
    
    if 'Ventas_anuales' in df_clientes.columns:
        df_clientes = df_clientes.sort_values(by='Ventas_anuales', ascending=False).reset_index(drop=True)
        df_clientes['Venta_Acumulada_Pct'] = df_clientes['Ventas_anuales'].cumsum() / df_clientes['Ventas_anuales'].sum()
    else:
        df_clientes['Venta_Acumulada_Pct'] = 1.0

    def asignar_abc(pct):
        if pct <= 0.50: return 'A'
        elif pct <= 0.80: return 'B'
        else: return 'C'
        
    df_clientes['Clasificacion'] = df_clientes['Venta_Acumulada_Pct'].apply(asignar_abc)
    return df_clientes, df_vendedores

def procesar_base_prospectos(file_prospectos):
    try:
        df_p = pd.read_excel(file_prospectos)
        df_p.columns = df_p.columns.str.strip()
        
        columnas_esperadas = ["Nombre de la Unidad Económica", "Clase de actividad SCIAN", "Latitud", "Longitud", "Domicilio"]
        for col in columnas_esperadas:
            if col not in df_p.columns:
                df_p[col] = np.nan
                
        df_p['Latitud'] = pd.to_numeric(df_p['Latitud'], errors='coerce')
        df_p['Longitud'] = pd.to_numeric(df_p['Longitud'], errors='coerce')
        df_p = df_p.dropna(subset=['Latitud', 'Longitud']).reset_index(drop=True)
        return df_p
    except Exception:
        return pd.DataFrame()

def generar_rutas_por_densidad(df_clientes, df_vendedores):
    if not df_clientes.empty and 'Latitud' in df_clientes.columns and 'Longitud' in df_clientes.columns:
        coords = np.radians(df_clientes[['Latitud', 'Longitud']])
        dbscan = DBSCAN(eps=0.003, min_samples=2, metric='haversine')
        df_clientes['Cluster_Densidad'] = dbscan.fit_predict(coords)
    else:
        df_clientes['Cluster_Densidad'] = -1
        
    df_clientes['ID_Vendedor_Asignado'] = df_clientes['ID_Vendedor']
    return df_clientes

def calcular_distancia_km(lat1, lon1, lat2, lon2):
    R = 6371.0 
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda/2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1-a))

# =============================================================================
# 2. MOTOR LOGÍSTICO Y AGENDA
# =============================================================================
def generar_agenda_dinamica(vendedor_id, df_clientes, df_vendedores, anio, mes):
    seller_id_limpio = str(vendedor_id).strip().split(".")[0]
    vendedor_rows = df_vendedores[df_vendedores['ID_Vendedor'] == seller_id_limpio]
    
    if vendedor_rows.empty:
        return pd.DataFrame(), (20.63599, -103.35747), pd.DataFrame()
        
    vendedor = vendedor_rows.iloc[0]
    base_coords = (vendedor['Latitud_Ruta_Inicio'], vendedor['Longitud_Ruta_Inicio'])
    
    clientes_vendedor = df_clientes[df_clientes['ID_Vendedor_Asignado'] == seller_id_limpio].copy()
    if clientes_vendedor.empty:
        return pd.DataFrame(), base_coords, pd.DataFrame()
        
    pool_visitas = []
    for idx, cl in clientes_vendedor.iterrows():
        d = cl.to_dict()
        frecuencia_val = d.get('Frecuencia de visita', 1)
        frecuencia = int(frecuencia_val) if pd.notna(frecuencia_val) else 1
        domicilio_original = d.get('Domicilio', 'Sin Domicilio Registrado')
        
        for f in range(1, frecuencia + 1):
            semana_objetivo = None
            if frecuencia == 2:
                semana_objetivo = 1 if f == 1 else 3  
            elif frecuencia == 4:
                semana_objetivo = f  
                
            pool_visitas.append({
                **d, 
                "Domicilio": str(domicilio_original).strip(), 
                "UID_Visita": f"{d['ID_Cliente']}_F{f}_{frecuencia}", 
                "Semana_Restriccion": semana_objetivo
            })
            
    df_pool = pd.DataFrame(pool_visitas)
    agenda_mensual = []
    historial_visitas = {}  
    
    num_dias_mes = calendar.monthrange(anio, mes)[1]
    nombre_mes_str = calendar.month_name[mes].capitalize()
    
    for dia_idx in range(1, num_dias_mes + 1):
        try:
            fecha_actual_dt = date(anio, mes, dia_idx)
            num_semana_mes = min(((dia_idx - 1) // 7 + 1), 4)
            if fecha_actual_dt.weekday() in [5, 6]:
                continue  
        except ValueError:
            break

        if df_pool.empty:
            continue
            
        hora_salida_anterior = datetime(anio, mes, dia_idx, 8, 30) 
        hora_limite = datetime(anio, mes, dia_idx, 18, 00) 
        comida_tomada = False
        bloque_hoy = []
        uids_agendados_hoy = set()
        lat_eje, lon_eje = base_coords 
        orden_visita = 1
        
        while hora_salida_anterior < hora_limite:
            if len([x for x in bloque_hoy if x['ID_Cliente'] != '-']) >= 8:
                break
                
            candidatos_validos = []
            for _, cand in df_pool.iterrows():
                id_cl = cand['ID_Cliente']
                sem_restriccion = cand['Semana_Restriccion']
                
                if sem_restriccion is not None and sem_restriccion != num_semana_mes:
                    conteo_semana_actual = len(df_pool[df_pool['Semana_Restriccion'] == num_semana_mes])
                    if conteo_semana_actual > 0:
                        continue
                        
                if id_cl in [x['ID_Cliente'] for x in bloque_hoy]: 
                    continue 
                if id_cl in historial_visitas and (dia_idx - historial_visitas[id_cl]) < 3: 
                    continue 
                candidatos_validos.append(cand.to_dict())
                
            if not candidatos_validos:
                for _, cand in df_pool.iterrows():
                    id_cl = cand['ID_Cliente']
                    if id_cl not in [x['ID_Cliente'] for x in bloque_hoy]:
                        candidatos_validos.append(cand.to_dict())
                if not candidatos_validos:
                    break
                
            def evaluar_cercania(v):
                return calcular_distancia_km(lat_eje, lon_eje, v['Latitud'], v['Longitud'])
                
            proximo_cliente = min(candidatos_validos, key=evaluar_cercania)
            dist_tramo = evaluar_cercania(proximo_cliente)
            
            tiempo_traslado_base = (dist_tramo / 35.0) * 60.0
            tiempo_trayecto_total = int(tiempo_traslado_base + 10)
            
            hora_llegada_punto = hora_salida_anterior + timedelta(minutes=tiempo_trayecto_total)
            hora_fin_visita = hora_llegada_punto + timedelta(minutes=30)
            
            if hora_llegada_punto > hora_limite:
                break 
                
            agenda_mensual.append({
                "Fecha_Raw": fecha_actual_dt,
                "Día del Mes": f"{nombre_mes_str} Día {dia_idx}",
                "Orden Visita": orden_visita,
                "ID_Cliente": str(proximo_cliente['ID_Cliente']).strip(),
                "Cliente": proximo_cliente['Cliente'],
                "Domicilio": proximo_cliente.get('Domicilio', 'Sin Domicilio Encontrado'), 
                "Clasificación ABC": proximo_cliente.get('Clasificacion', 'C'),
                "Secuencia Frecuencia": "",  
                "Venta_Mensual_Calculada": proximo_cliente.get('Venta_Mensual_Calculada', 0.0),
                "Hora de llegada al punto": hora_llegada_punto.strftime("%I:%M %p"),
                "Tiempo de visita": "30 MIN",
                "Hora de Salida": hora_fin_visita.strftime("%I:%M %p"),
                "Tiempo de trayecto a próximo cliente": f"{tiempo_trayecto_total} MIN",
                "Kilómetros a próximo cliente": f"{dist_tramo:.2f} KM",
                "Latitud": proximo_cliente['Latitud'],
                "Longitud": proximo_cliente['Longitud'],
                "Métrica_Km_Día": 0.0, "Métrica_Min_Día": 0.0, "Es_Mapa": True
            })
            
            bloque_hoy.append(proximo_cliente)
            uids_agendados_hoy.add(proximo_cliente['UID_Visita'])
            historial_visitas[proximo_cliente['ID_Cliente']] = dia_idx
            orden_visita += 1
            
            if not comida_tomada and hora_fin_visita.time() >= datetime(anio, mes, dia_idx, 13, 00).time():
                hora_inicio_comida = hora_fin_visita
                hora_fin_comida = hora_inicio_comida + timedelta(hours=1)
                
                agenda_mensual.append({
                    "Fecha_Raw": fecha_actual_dt, "Día del Mes": f"{nombre_mes_str} Día {dia_idx}", "Orden Visita": orden_visita,
                    "ID_Cliente": "-", "Cliente": "☕ HORA DE COMIDA (JORNADA)", "Domicilio": "-", "Clasificación ABC": "-", "Secuencia Frecuencia": "-",
                    "Venta_Mensual_Calculada": 0.0, "Hora de llegada al punto": hora_inicio_comida.strftime("%I:%M %p"), "Tiempo de visita": "1 HORA",
                    "Hora de Salida": hora_fin_comida.strftime("%I:%M %p"), "Tiempo de trayecto a próximo cliente": "10 MIN", "Kilómetros a próximo cliente": "-",
                    "Latitud": proximo_cliente['Latitud'], "Longitud": proximo_cliente['Longitud'], "Métrica_Km_Día": 0.0, "Métrica_Min_Día": 0.0, "Es_Mapa": False
                })
                orden_visita += 1
                comida_tomada = True
                hora_salida_anterior = hora_fin_comida
            else:
                hora_salida_anterior = hora_fin_visita
                
            lat_eje, lon_eje = proximo_cliente['Latitud'], proximo_cliente['Longitud']
            
        if bloque_hoy:
            ultima_parada = bloque_hoy[-1]
            dist_retorno = calcular_distancia_km(ultima_parada['Latitud'], ultima_parada['Longitud'], base_coords[0], base_coords[1])
            total_km_dia = sum(calcular_distancia_km(base_coords[0], base_coords[1], bloque_hoy[0]['Latitud'], bloque_hoy[0]['Longitud']) if i==0 else calcular_distancia_km(bloque_hoy[i-1]['Latitud'], bloque_hoy[i-1]['Longitud'], x['Latitud'], x['Longitud']) for i, x in enumerate(bloque_hoy)) + dist_retorno
            
            for item in agenda_mensual:
                if item["Día del Mes"] == f"{nombre_mes_str} Día {dia_idx}":
                    item["Métrica_Km_Día"] = total_km_dia
                    item["Métrica_Min_Día"] = (total_km_dia / 35.0) * 60.0 + (len(bloque_hoy)*30) + (60 if comida_tomada else 0) + (len(bloque_hoy)*10)
                    
            df_pool = df_pool[~df_pool['UID_Visita'].isin(uids_agendados_hoy)].reset_index(drop=True)
        
    df_resultado = pd.DataFrame(agenda_mensual)
    if not df_resultado.empty:
        df_resultado = df_resultado.sort_values(by=['Fecha_Raw', 'Orden Visita']).reset_index(drop=True)
        conteo_total_visitas = df_resultado[df_resultado['ID_Cliente'] != '-']['ID_Cliente'].value_counts().to_dict()
        contador_visitas_cliente = {}
        for idx, row in df_resultado.iterrows():
            id_cl = row['ID_Cliente']
            if id_cl != '-':
                contador_visitas_cliente[id_cl] = contador_visitas_cliente.get(id_cl, 0) + 1
                total_mes = conteo_total_visitas[id_cl]
                df_resultado.at[idx, 'Secuencia Frecuencia'] = f"Visita {contador_visitas_cliente[id_cl]}/{total_mes}"
                
    return df_resultado, base_coords, clientes_vendedor

# =============================================================================
# 3. PROCESAMIENTO DEL PEDIDO SUGERIDO Y ANÁLISIS DE COBERTURAS
# =============================================================================
def procesar_pedido_sugerido(
    id_vendedor,
    fecha_evaluada,
    df_agenda_vendedor,
    f_ranking,
    f_ventas,
    f_demanda,
    f_master,
    cliente_id_seleccionado=None,
):
    try:
        df_master = cargar_dataframe_flexible(f_master, "MASTER DE CLIENTES.xlsx")
        df_ranking = cargar_dataframe_flexible(f_ranking, "RANKING FERRETEROS.xlsx")
        df_ventas = cargar_dataframe_flexible(f_ventas, "VENTAS FERRETEROS.xlsx")
        df_demanda = cargar_dataframe_flexible(f_demanda, "Demanda.xlsx")

        missing = [
            f for f, obj in zip(
                ["MASTER DE CLIENTES.xlsx", "RANKING FERRETEROS.xlsx", "VENTAS FERRETEROS.xlsx", "Demanda.xlsx"],
                [df_master, df_ranking, df_ventas, df_demanda],
            ) if obj is None
        ]
        if missing:
            return None, f"Faltan los siguientes archivos necesarios: {', '.join(missing)}", None

        # Carga del catálogo de marcas
        ruta_marcas = r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\CATALOGO DE MARCAS POR PRODUCTO.xlsx"
        if os.path.exists(ruta_marcas):
            df_marcas = pd.read_excel(ruta_marcas)
            df_marcas.columns = df_marcas.columns.astype(str).str.strip()
            
            col_cod_m = next((c for c in df_marcas.columns if re.search(r"c[oó]digo[_\s]*de[_\s]*producto|cod[_\s]*prod|producto", c, re.IGNORECASE)), None)
            col_marca_m = next((c for c in df_marcas.columns if re.search(r"marca", c, re.IGNORECASE)), None)
            
            if col_cod_m and col_marca_m:
                df_marcas = df_marcas[[col_cod_m, col_marca_m]].rename(columns={col_cod_m: "Codigo de Producto", col_marca_m: "Marca"})
                df_marcas["Codigo de Producto"] = df_marcas["Codigo de Producto"].astype(str).str.strip()
                df_marcas = df_marcas.drop_duplicates(subset=["Codigo de Producto"])
            else:
                df_marcas = pd.DataFrame(columns=["Codigo de Producto", "Marca"])
        else:
            df_marcas = pd.DataFrame(columns=["Codigo de Producto", "Marca"])

        if "TOTAL" not in df_ventas.columns:
            return None, "La columna 'TOTAL' no se encuentra en el archivo VENTAS FERRETEROS.xlsx.", None

        df_master = homologar_columna_cliente(df_master)
        df_ventas = homologar_columna_cliente(df_ventas)
        df_demanda = homologar_columna_cliente(df_demanda)

        if "Document Date" in df_demanda.columns and "Fecha" not in df_demanda.columns:
            df_demanda.rename(columns={"Document Date": "Fecha"}, inplace=True)

        if "Fecha" in df_ventas.columns:
            df_ventas["Fecha_dt"] = pd.to_datetime(df_ventas["Fecha"], errors="coerce")
            df_ventas["Año"] = df_ventas["Fecha_dt"].dt.year
            df_ventas["Mes"] = df_ventas["Fecha_dt"].dt.month

        if "Fecha" in df_demanda.columns:
            df_demanda["Fecha_dt"] = pd.to_datetime(df_demanda["Fecha"], errors="coerce")
            df_demanda["Año"] = df_demanda["Fecha_dt"].dt.year
            df_demanda["Mes"] = df_demanda["Fecha_dt"].dt.month

        fecha_eval_str = (
            fecha_evaluada.strftime("%Y-%m-%d")
            if hasattr(fecha_evaluada, "strftime")
            else str(fecha_evaluada)
        )
        df_agenda_dia = df_agenda_vendedor[
            df_agenda_vendedor["Fecha_Raw"].astype(str) == fecha_eval_str
        ].copy()
        df_agenda_dia = df_agenda_dia[df_agenda_dia["ID_Cliente"] != "-"]

        if df_agenda_dia.empty:
            return None, "No hay clientes agendados para la fecha seleccionada.", None

        if cliente_id_seleccionado and str(cliente_id_seleccionado).strip() != "-":
            id_sel_clean = str(cliente_id_seleccionado).split("-")[0].strip()
            df_agenda_dia["ID_Cliente_Clean"] = (
                df_agenda_dia["ID_Cliente"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            )
            df_agenda_dia = df_agenda_dia[df_agenda_dia["ID_Cliente_Clean"] == id_sel_clean]
            if df_agenda_dia.empty:
                return None, f"El cliente seleccionado ({cliente_id_seleccionado}) no está agendado hoy.", None

        clientes_dia = df_agenda_dia[["ID_Cliente", "Cliente"]].drop_duplicates()
        clientes_dia["ID_Cliente"] = clientes_dia["ID_Cliente"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

        df_ranking.columns = df_ranking.columns.astype(str).str.strip()
        df_ranking = desduplicar_columnas(df_ranking)
        mapa_cols_rk = {}
        for col in df_ranking.columns:
            if re.search(r"codigo[_\s]*producto|cod[_\s]*prod|producto", col, re.IGNORECASE):
                mapa_cols_rk[col] = "Codigo de Producto"
            elif re.search(r"descripci[oó]n", col, re.IGNORECASE):
                mapa_cols_rk[col] = "Descripción"
            elif re.search(r"ferretero", col, re.IGNORECASE):
                mapa_cols_rk[col] = "Ferreteros"
        df_ranking.rename(columns=mapa_cols_rk, inplace=True)
        df_ranking = desduplicar_columnas(df_ranking)
        if "Codigo de Producto" in df_ranking.columns:
            df_ranking["Codigo de Producto"] = df_ranking["Codigo de Producto"].astype(str).str.strip()

        df_ventas = desduplicar_columnas(df_ventas)
        mapa_cols_v = {}
        for col in df_ventas.columns:
            if re.search(r"c[oó]digo[_\s]*de[_\s]*producto|cod[_\s]*prod|producto", col, re.IGNORECASE):
                mapa_cols_v[col] = "Codigo de Producto"
            elif re.search(r"descripci[oó]n", col, re.IGNORECASE):
                mapa_cols_v[col] = "DESCRIPCIÓN"
        df_ventas.rename(columns=mapa_cols_v, inplace=True)
        df_ventas = desduplicar_columnas(df_ventas)
        if "Codigo de Producto" in df_ventas.columns:
            df_ventas["Codigo de Producto"] = df_ventas["Codigo de Producto"].astype(str).str.strip()

        df_demanda = desduplicar_columnas(df_demanda)
        mapa_cols_d = {}
        for col in df_demanda.columns:
            if re.search(r"c[oó]digo[_\s]*de[_\s]*producto|cod[_\s]*prod|producto", col, re.IGNORECASE):
                mapa_cols_d[col] = "Codigo de Producto"
                break
        df_demanda.rename(columns=mapa_cols_d, inplace=True)
        df_demanda = desduplicar_columnas(df_demanda)
        if "Codigo de Producto" in df_demanda.columns:
            df_demanda["Codigo de Producto"] = df_demanda["Codigo de Producto"].astype(str).str.strip()

        dt_eval = pd.to_datetime(fecha_evaluada)
        mes_actual, anio_actual = dt_eval.month, dt_eval.year

        def restar_meses(m, a, n):
            m_res, a_res = m - n, a
            while m_res <= 0:
                m_res += 12
                a_res -= 1
            return m_res, a_res

        m_m3, a_m3 = restar_meses(mes_actual, anio_actual, 3)
        m_m2, a_m2 = restar_meses(mes_actual, anio_actual, 2)
        m_m1, a_m1 = restar_meses(mes_actual, anio_actual, 1)

        registros_sugerido_8020 = []
        registros_intermitente = []
        registros_recuperar_20 = []
        registros_oportunidades = []

        col_cant_v = "Piezas_DF" if "Piezas_DF" in df_ventas.columns else ("Piezas" if "Piezas" in df_ventas.columns else "TOTAL")

        for _, cl_row in clientes_dia.iterrows():
            id_cl, nombre_cl = cl_row["ID_Cliente"], cl_row["Cliente"]

            df_v_cl = df_ventas[df_ventas["ID_Cliente"] == id_cl].copy()
            if df_v_cl.empty:
                continue

            df_v_2026 = df_v_cl[df_v_cl["Año"] == anio_actual].copy()
            if not df_v_2026.empty:
                df_v_2026["TOTAL"] = pd.to_numeric(df_v_2026["TOTAL"], errors="coerce").fillna(0)
                df_grp_2026 = (
                    df_v_2026.groupby("Codigo de Producto")["TOTAL"]
                    .sum()
                    .reset_index()
                    .sort_values(by="TOTAL", ascending=False)
                    .reset_index(drop=True)
                )
                total_acumulado_2026 = df_grp_2026["TOTAL"].sum()
                if total_acumulado_2026 > 0:
                    df_grp_2026["Pct_Part"] = df_grp_2026["TOTAL"] / total_acumulado_2026
                    df_grp_2026["Pct_Acum"] = df_grp_2026["Pct_Part"].cumsum()
                else:
                    df_grp_2026["Pct_Part"] = 0.0
                    df_grp_2026["Pct_Acum"] = 0.0
            else:
                df_grp_2026 = pd.DataFrame(columns=["Codigo de Producto", "TOTAL", "Pct_Part", "Pct_Acum"])

            prods_2026_ordenados = df_grp_2026["Codigo de Producto"].tolist()
            prods_resto = [p for p in df_v_cl["Codigo de Producto"].unique() if p not in prods_2026_ordenados]
            prods_hist = prods_2026_ordenados + prods_resto

            for idx, cod_prod in enumerate(prods_hist, 1):
                v_prod_match = df_v_cl[df_v_cl["Codigo de Producto"] == cod_prod]
                desc_prod = v_prod_match.iloc[0]["DESCRIPCIÓN"] if not v_prod_match.empty and "DESCRIPCIÓN" in v_prod_match.columns and pd.notna(v_prod_match.iloc[0]["DESCRIPCIÓN"]) else ""

                m_match = df_marcas[df_marcas["Codigo de Producto"] == cod_prod]
                marca_prod = m_match.iloc[0]["Marca"] if not m_match.empty and pd.notna(m_match.iloc[0]["Marca"]) else "SIN MARCA"

                m_2026 = df_grp_2026[df_grp_2026["Codigo de Producto"] == cod_prod]
                if not m_2026.empty:
                    pct_acum = m_2026.iloc[0]["Pct_Acum"]
                    es_80_20 = (pct_acum <= 0.80001) or (m_2026.index[0] == 0)
                else:
                    es_80_20 = False

                total_meses_eval = max(1, mes_actual)
                df_v_ene_fecha = df_v_cl[
                    (df_v_cl["Codigo de Producto"] == cod_prod) & 
                    (df_v_cl["Año"] == anio_actual) & 
                    (df_v_cl["Mes"] >= 1) & 
                    (df_v_cl["Mes"] <= mes_actual)
                ].copy()
                
                if not df_v_ene_fecha.empty:
                    df_v_ene_fecha[col_cant_v] = pd.to_numeric(df_v_ene_fecha[col_cant_v], errors="coerce").fillna(0)
                    meses_con_venta = df_v_ene_fecha[df_v_ene_fecha[col_cant_v] > 0]["Mes"].nunique()
                else:
                    meses_con_venta = 0
                
                cumple_60_pct = (meses_con_venta / total_meses_eval) >= 0.60

                v_aa = pd.to_numeric(df_ventas[(df_ventas["ID_Cliente"] == id_cl) & (df_ventas["Codigo de Producto"] == cod_prod) & (df_ventas["Año"] == (anio_actual - 1)) & (df_ventas["Mes"] == mes_actual)][col_cant_v], errors="coerce").fillna(0).sum()
                v_m3 = pd.to_numeric(df_ventas[(df_ventas["ID_Cliente"] == id_cl) & (df_ventas["Codigo de Producto"] == cod_prod) & (df_ventas["Año"] == a_m3) & (df_ventas["Mes"] == m_m3)][col_cant_v], errors="coerce").fillna(0).sum()
                v_m2 = pd.to_numeric(df_ventas[(df_ventas["ID_Cliente"] == id_cl) & (df_ventas["Codigo de Producto"] == cod_prod) & (df_ventas["Año"] == a_m2) & (df_ventas["Mes"] == m_m2)][col_cant_v], errors="coerce").fillna(0).sum()
                v_m1 = pd.to_numeric(df_ventas[(df_ventas["ID_Cliente"] == id_cl) & (df_ventas["Codigo de Producto"] == cod_prod) & (df_ventas["Año"] == a_m1) & (df_ventas["Mes"] == m_m1)][col_cant_v], errors="coerce").fillna(0).sum()

                col_dem_qty = "Incoming Orders Qty" if "Incoming Orders Qty" in df_demanda.columns else ("TOTAL" if "TOTAL" in df_demanda.columns else None)
                dem_fecha = pd.to_numeric(df_demanda[(df_demanda["ID_Cliente"] == id_cl) & (df_demanda["Codigo de Producto"] == cod_prod) & (df_demanda["Año"] == anio_actual) & (df_demanda["Mes"] == mes_actual)][col_dem_qty], errors="coerce").fillna(0).sum() if col_dem_qty else 0

                sugerido_base = (v_aa * 0.40) + (v_m1 * 0.30) + (v_m2 * 0.20) + (v_m3 * 0.10)
                sugerido_final = max(0, int(round(sugerido_base)))

                avance = dem_fecha - sugerido_final

                pct_avance = (dem_fecha / sugerido_final * 100) if sugerido_final > 0 else (100.0 if dem_fecha > 0 else 0.0)
                indicador = "🔴 😢" if pct_avance < 50 else ("🟡 😐" if pct_avance < 95 else "🟢 😊")

                v_historico = df_ventas[(df_ventas["ID_Cliente"] == id_cl) & (df_ventas["Codigo de Producto"] == cod_prod) & (pd.to_numeric(df_ventas[col_cant_v], errors="coerce") >= 1)]
                if not v_historico.empty and "Fecha_dt" in v_historico.columns:
                    v_historico_validas = v_historico.dropna(subset=["Fecha_dt"])
                    if not v_historico_validas.empty:
                        max_fecha = v_historico_validas["Fecha_dt"].max()
                        u_mes_anio_str = max_fecha.strftime("%m/%Y")
                    else:
                        u_mes_anio_str = "-"
                else:
                    u_mes_anio_str = "-"

                item_pedido = {
                    "Marca": marca_prod,
                    "Código de Producto": cod_prod,
                    "DESCRIPCIÓN": desc_prod,
                    "Sugerido": sugerido_final,
                    "Avance": int(round(avance)),
                    "Indicador": indicador,
                    "Ultimo mes de Venta": u_mes_anio_str,
                }

                if es_80_20:
                    if cumple_60_pct:
                        registros_sugerido_8020.append(item_pedido)
                    else:
                        registros_intermitente.append(item_pedido)
                else:
                    registros_recuperar_20.append(item_pedido)

            prods_comprados = set(prods_hist)
            prods_top = set()
            if "Codigo de Producto" in df_ranking.columns and not df_ranking.empty:
                prods_top = set(df_ranking["Codigo de Producto"].dropna().head(50).unique())

            for p_op in prods_top - prods_comprados:
                rk_op_match = df_ranking[df_ranking["Codigo de Producto"] == p_op]
                desc_op = rk_op_match.iloc[0]["Descripción"] if not rk_op_match.empty and "Descripción" in rk_op_match.columns else ""
                
                m_op_match = df_marcas[df_marcas["Codigo de Producto"] == p_op]
                marca_op = m_op_match.iloc[0]["Marca"] if not m_op_match.empty and pd.notna(m_op_match.iloc[0]["Marca"]) else "SIN MARCA"

                registros_oportunidades.append({
                    "Marca": marca_op,
                    "Código de Producto": p_op,
                    "DESCRIPCIÓN": desc_op,
                    "Sugerido": 0,
                    "Avance": 0,
                    "Indicador": "🔴 😢",
                    "Ultimo mes de Venta": "-",
                })

        cols_visibles = [
            "Marca", "Código de Producto", "DESCRIPCIÓN",
            "Sugerido", "Avance", "Indicador", "Ultimo mes de Venta"
        ]

        def preparar_df_agrupado(lista_registros):
            if not lista_registros:
                return pd.DataFrame(columns=cols_visibles)
            df = pd.DataFrame(lista_registros).reindex(columns=cols_visibles)
            return df.sort_values(by=["Marca", "Código de Producto"]).reset_index(drop=True)

        df_8020 = preparar_df_agrupado(registros_sugerido_8020)
        df_intermitente = preparar_df_agrupado(registros_intermitente)
        df_recuperar_20 = preparar_df_agrupado(registros_recuperar_20)
        df_oportunidades = preparar_df_agrupado(registros_oportunidades)

        return {
            "pedido": df_8020,
            "intermitente": df_intermitente,
            "recuperar_20": df_recuperar_20,
            "oportunidades": df_oportunidades
        }, None, anio_actual

    except Exception as e:
        return None, f"Error en procesamiento del Pedido Sugerido: {str(e)}", None

# =============================================================================
# 4. ENRUTADOR VIAL (OSRM)
# =============================================================================
def obtener_ruta_calles_osrm(puntos):
    try:
        string_coords = ";".join([f"{lon},{lat}" for lat, lon in puntos])
        url = f"https://router.project-osrm.org/route/v1/driving/{string_coords}?overview=full&geometries=geojson"
        response = requests.get(url, timeout=5)
        res_data = response.json()
        if res_data.get('code') == 'Ok':
            coords_geometria = res_data['routes'][0]['geometry']['coordinates']
            return [[lat, lon] for lon, lat in coords_geometria], True
    except Exception:
        pass
    return puntos, False

# =============================================================================
# 5. PANEL DE CONTROL INTERACTIVO DE STREAMLIT
# =============================================================================
st.set_page_config(layout="wide")

st.markdown("""
    <style>
    th[role="columnheader"] div {
        white-space: normal !important;
        text-overflow: clip !important;
        overflow: visible !important;
        word-wrap: break-word !important;
        line-height: 1.2 !important;
    }
    th[role="columnheader"] {
        vertical-align: bottom !important;
    }
    </style>
""", unsafe_allow_html=True)

col_titulo, col_logo = st.columns([0.8, 0.2])
with col_titulo:
    st.title("FERREPLANNER PRISA")
with col_logo:
    try:
        st.image(r"C:\Users\lmacias\Desktop\RUTAS LÓGICAS\Logo_PRISA.png", width=640)
    except:
        st.markdown("<p style='text-align: right; color: gray; font-size: 12px;'>[ Logo Empresa ]</p>", unsafe_allow_html=True)

precio_regular_jalisco = extraer_precio_gasolina_real()

# --- PANEL SIDEBAR ---
st.sidebar.header("📥 Entrada de Archivos Rutas")
file_clientes = st.sidebar.file_uploader("Base de Clientes (.xlsx)", type=["xlsx"])
file_vendedores = st.sidebar.file_uploader("Base de Vendedores (.xlsx)", type=["xlsx"])
file_prospectos = st.sidebar.file_uploader("Base de Prospectos (.xlsx)", type=["xlsx"])

st.sidebar.markdown("---")
st.sidebar.header("📂 Archivos Módulo Pedido Sugerido")
f_ranking = st.sidebar.file_uploader("RANKING FERRETEROS (.xlsx)", type=["xlsx"], key="f_rk")
f_ventas = st.sidebar.file_uploader("VENTAS FERRETEROS (.xlsx)", type=["xlsx"], key="f_vt")
f_demanda = st.sidebar.file_uploader("Demanda (.xlsx)", type=["xlsx"], key="f_dm")
f_master = st.sidebar.file_uploader("MASTER DE CLIENTES (.xlsx)", type=["xlsx"], key="f_ms")
f_sug_prospectos = st.sidebar.file_uploader("PEDIDO SUGERIDO PROSPECTOS (.xlsx)", type=["xlsx"], key="f_sp")

st.sidebar.markdown("---")
st.sidebar.header("📅 Calendario")
lista_anios = [2026, 2027, 2028, 2029, 2030]
anio_seleccionado = st.sidebar.selectbox("Seleccione el Año Operativo:", lista_anios, index=0)

lista_meses = [("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4), ("Mayo", 5), ("Junio", 6), 
                ("Julio", 7), ("Agosto", 8), ("Septiembre", 9), ("Octubre", 10), ("Noviembre", 11), ("Diciembre", 12)]
mes_nombre, mes_numerico = st.sidebar.selectbox("Seleccione el Mes de Distribución:", lista_meses, index=6, format_func=lambda x: x[0])

df_prospectos_raw = pd.DataFrame()
if file_prospectos:
    df_prospectos_raw = procesar_base_prospectos(file_prospectos)

if file_clientes and file_vendedores:
    df_cl, df_vn = procesar_datos_maestros(file_clientes, file_vendedores)
    df_cl = generar_rutas_por_densidad(df_cl, df_vn)
    st.sidebar.success("Bases maestras vinculadas correctamente.")
    
    vendedor_opciones = df_vn['ID_Vendedor'].astype(str) + " - " + df_vn['Nombre'].astype(str)
    vendedor_seleccionado = st.selectbox("Seleccione el Vendedor para Desplegar Agenda Mensual:", vendedor_opciones)
    
    id_vendedor = vendedor_seleccionado.split(" - ")[0].strip().split(".")[0]
    df_agenda_mes, inicio_coords, df_universo = generar_agenda_dinamica(id_vendedor, df_cl, df_vn, anio_seleccionado, mes_numerico)
    
    # Pestañas principales
    tab_rutas, tab_sugerido, tab_prospectos_sug = st.tabs([
        "🗺️ Rutas y Logística", 
        "📊 Pedido Sugerido y Análisis", 
        "✨ Pedido Sugerido Clientes Nuevos"
    ])
    
    with tab_rutas:
        if df_agenda_mes is not None and not df_agenda_mes.empty:
            st.markdown("---")
            clases_seleccionadas = []
            if not df_prospectos_raw.empty:
                actividades_disponibles = sorted(df_prospectos_raw["Clase de actividad SCIAN"].dropna().unique().tolist())
                clases_seleccionadas = st.multiselect(
                    "🎯 FILTRO SUPERIOR: Seleccionar Clase de actividad SCIAN para Prospección:", 
                    options=actividades_disponibles,
                    default=[]
                )
                st.markdown("---")
                
            cb1, cb2 = st.columns(2)
            with cb1:
                st.markdown("#### 🔍 Buscador de Fechas por ID")
                id_buscado = st.text_input("Ingrese el ID del Cliente a verificar:", key="search_id_input", placeholder="Ej. 10243").strip()
            with cb2:
                st.markdown(f"#### 📅 Control del Calendario ({mes_nombre} {anio_seleccionado})")
                fecha_seleccionada = st.date_input(
                    "Seleccione fecha para evaluar ruta:",
                    value=date(anio_seleccionado, mes_numerico, 1),
                    min_value=date(anio_seleccionado, mes_numerico, 1),
                    max_value=date(anio_seleccionado, mes_numerico, calendar.monthrange(anio_seleccionado, mes_numerico)[1])
                )
                
            if id_buscado:
                df_resumen_cliente = df_agenda_mes[df_agenda_mes['ID_Cliente'] == id_buscado]
                if not df_resumen_cliente.empty:
                    st.success(f"🗓️ Visitas programadas encontradas para el ID: {id_buscado}")
                    df_resumen_formato = df_resumen_cliente.copy()
                    df_resumen_formato['Venta_Mensual_Calculada'] = df_resumen_formato['Venta_Mensual_Calculada'].map("${:,.2f}".format)
                    st.dataframe(
                        df_resumen_formato[['Día del Mes', 'Orden Visita', 'ID_Cliente', 'Cliente', 'Domicilio', 'Clasificación ABC', 'Secuencia Frecuencia', 'Hora de llegada al punto', 'Tiempo de visita', 'Hora de Salida', 'Tiempo de trayecto a próximo cliente', 'Kilómetros a próximo cliente', 'Venta_Mensual_Calculada']], 
                        use_container_width=True, hide_index=True
                    )
                    
            df_dia_filtrado = df_agenda_mes[df_agenda_mes['Fecha_Raw'] == fecha_seleccionada].reset_index(drop=True)
            
            if df_dia_filtrado.empty:
                st.info(f"📆 El día {fecha_seleccionada.strftime('%d/%m/%Y')} corresponde a un Fin de Semana (Fuera de la jornada laboral).")
            else:
                dia_seleccionado_str = df_dia_filtrado.iloc[0]['Día del Mes']
                st.markdown(f"### 📍 Desplegando datos operativos para: **{dia_seleccionado_str}**")
                st.markdown("---")
                
                es_dia_vacio = (df_dia_filtrado.shape[0] == 1 and df_dia_filtrado.iloc[0]['ID_Cliente'] == "-")
                km_totales_ruta = 0.0 if es_dia_vacio else float(df_dia_filtrado.iloc[0]['Métrica_Km_Día'])
                tiempo_total_minutos = 0.0 if es_dia_vacio else float(df_dia_filtrado.iloc[0]['Métrica_Min_Día'])
                venta_mensual_total_ruta = 0.0 if es_dia_vacio else float(df_dia_filtrado['Venta_Mensual_Calculada'].sum())
                
                litros_consumidos = km_totales_ruta / 14.0
                gasto_combustible_pesos = litros_consumidos * precio_regular_jalisco
                
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("💰 Venta Promedio", f"${venta_mensual_total_ruta:,.2f}")
                m2.metric("🛣️ Distancia Total", f"{km_totales_ruta:.2f} Km")
                m3.metric("⏱️ Horas de Jornada", f"{int(tiempo_total_minutos // 60)}h {int(tiempo_total_minutos % 60)}min" if tiempo_total_minutos > 0 else "0h 0min")
                m4.metric("⛽ Gasolina Regular", f"${precio_regular_jalisco:.2f}/L")
                m5.metric("💳 Inversión Combustible", f"${gasto_combustible_pesos:,.2f}")
                
                st.markdown("---")
                
                df_prospectos_radio_2km = pd.DataFrame()
                if not df_prospectos_raw.empty and not es_dia_vacio:
                    df_p_temp = df_prospectos_raw.copy()
                    if clases_seleccionadas:
                        df_p_temp = df_p_temp[df_p_temp["Clase de actividad SCIAN"].isin(clases_seleccionadas)].reset_index(drop=True)
                    
                    indices_prospectos_validos = []
                    puntos_ruta_hoy = [(inicio_coords[0], inicio_coords[1])] + list(df_dia_filtrado[df_dia_filtrado['Es_Mapa']==True][['Latitud', 'Longitud']].itertuples(index=False, name=None))
                    
                    for pr_idx, pr_row in df_p_temp.iterrows():
                        distancia_minima = min(calcular_distancia_km(pr_row['Latitud'], pr_row['Longitud'], r_lat, r_lon) for r_lat, r_lon in puntos_ruta_hoy)
                        if distancia_minima <= 2.0:  
                            indices_prospectos_validos.append(pr_idx)
                            
                    df_prospectos_radio_2km = df_p_temp.iloc[indices_prospectos_validos].reset_index(drop=True)

                fila_inicio = pd.DataFrame([{
                    "Orden Visita": 0, "ID_Cliente": "-", "Cliente": "Salida de Base Logística", "Domicilio": "-",
                    "Clasificación ABC": "-", "Secuencia Frecuencia": "-", "Venta_Mensual_Calculada": 0.0, 
                    "Hora de llegada al punto": "08:30 AM", "Tiempo de visita": "-", "Hora de Salida": "08:30 AM",
                    "Tiempo de trayecto a próximo cliente": "-", "Kilómetros a próximo cliente": "-"
                }])
                fila_regreso = pd.DataFrame([{
                    "Orden Visita": 99, "ID_Cliente": "-", "Cliente": "Regreso a Base Logística", "Domicilio": "-",
                    "Clasificación ABC": "-", "Secuencia Frecuencia": "-", "Venta_Mensual_Calculada": 0.0, 
                    "Hora de llegada al punto": "05:30 PM", "Tiempo de visita": "-", "Hora de Salida": "05:30 PM",
                    "Tiempo de trayecto a próximo cliente": "-", "Kilómetros a próximo cliente": "-"
                }])
                
                if es_dia_vacio:
                    df_tabla_mostrar = pd.concat([fila_inicio, fila_regreso], ignore_index=True)
                else:
                    df_format_tabla = df_dia_filtrado[['Orden Visita', 'ID_Cliente', 'Cliente', 'Domicilio', 'Clasificación ABC', 'Secuencia Frecuencia', 'Venta_Mensual_Calculada', 'Hora de llegada al punto', 'Tiempo de visita', 'Hora de Salida', 'Tiempo de trayecto a próximo cliente', 'Kilómetros a próximo cliente']]
                    df_tabla_mostrar = pd.concat([fila_inicio, df_format_tabla, fila_regreso], ignore_index=True)
                
                df_tabla_mostrar['Venta_Mensual_Calculada'] = df_tabla_mostrar['Venta_Mensual_Calculada'].map("${:,.2f}".format)
                
                col1, col2 = st.columns([0.5, 0.5])
                with col1:
                    st.subheader(f"📋 Agenda Diaria: {dia_seleccionado_str}")
                    seleccion_tabla = st.dataframe(
                        df_tabla_mostrar[['Orden Visita', 'ID_Cliente', 'Cliente', 'Domicilio', 'Clasificación ABC', 'Secuencia Frecuencia', 'Hora de llegada al punto', 'Tiempo de visita', 'Hora de Salida', 'Tiempo de trayecto a próximo cliente', 'Kilómetros a próximo cliente', 'Venta_Mensual_Calculada']], 
                        height=540, use_container_width=True, hide_index=True,
                        on_select="rerun", selection_mode="single-row"
                    )
                    
                    cliente_seleccionado_nombre = None
                    if seleccion_tabla and "rows" in seleccion_tabla.get("selection", {}):
                        indices_sel = seleccion_tabla["selection"]["rows"]
                        if indices_sel:
                            cliente_seleccionado_nombre = df_tabla_mostrar.iloc[indices_sel[0]]['Cliente']
                    
                with col2:
                    st.subheader("🗺️ Cartografía Vía Rombo Rosa (Filtro 2 Km)")
                    mapbox_tiles_url = f"https://api.mapbox.com/styles/v1/mapbox/{MAPBOX_STYLE}/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}"
                    m = folium.Map(location=[inicio_coords[0], inicio_coords[1]], zoom_start=13, width='100%', height='100%', tiles=None)
                    
                    folium.TileLayer(
                        tiles=mapbox_tiles_url, attr='© Mapbox © OpenStreetMap contributors',
                        name="Mapbox Premium", max_zoom=19, overlay=False, control=True
                    ).add_to(m)
                    
                    if df_universo is not None and not df_universo.empty:
                        for _, cl_total in df_universo.iterrows():
                            folium.CircleMarker(
                                location=[cl_total['Latitud'], cl_total['Longitud']], radius=4, color='gray', fill=True, fill_color='lightgray', fill_opacity=0.6,
                                popup=f"<b>{cl_total['Cliente']}</b><br>ID: {cl_total['ID_Cliente']}",
                                tooltip="Cliente de la Zona"
                            ).add_to(m)
                    
                    if not df_prospectos_radio_2km.empty:
                        for pr_idx, pr_row in df_prospectos_radio_2km.iterrows():
                            folium.RegularPolygonMarker(
                                location=[pr_row['Latitud'], pr_row['Longitud']],
                                number_of_sides=4, 
                                radius=7,
                                color='#FF69B4', 
                                fill_color='#FFC0CB', 
                                fill_opacity=0.9,
                                popup=f"<b>💼 {pr_row['Nombre de la Unidad Económica']}</b><br>{pr_row['Clase de actividad SCIAN']}<br>{pr_row['Domicilio']}",
                                tooltip="Prospecto Comercial (≤ 2km)"
                            ).add_to(m)
                    
                    folium.Marker(location=inicio_coords, tooltip="Base Logística", icon=folium.Icon(color='red', icon='home')).add_to(m)
                    puntos_circuito = [inicio_coords]
                    colores_puntos = {'A': 'darkblue', 'B': 'blue', 'C': 'purple'}
                    
                    if not es_dia_vacio:
                        for _, row in df_dia_filtrado.iterrows():
                            if not row['Es_Mapa']:
                                continue
                            puntos_circuito.append((row['Latitud'], row['Longitud']))
                            
                            if cliente_seleccionado_nombre and str(row['Cliente']).strip() == str(cliente_seleccionado_nombre).strip():
                                folium.Marker(
                                    location=[row['Latitud'], row['Longitud']], popup=f"<b>⭐ {row['Cliente']} ⭐</b><br>ID: {row['ID_Cliente']}",
                                    tooltip="🎯 SELECCIONADO", icon=folium.Icon(color='orange', icon_color='yellow', icon='star')
                                ).add_to(m)
                            else:
                                color_marcador = colores_puntos.get(row['Clasificación ABC'], 'orange')
                                folium.Marker(
                                    location=[row['Latitud'], row['Longitud']], popup=f"<b>{row['Cliente']}</b>",
                                    tooltip=f"Parada {row['Orden Visita']}", icon=folium.Icon(color=color_marcador, icon='play')
                                ).add_to(m)
                            
                        puntos_circuito.append(inicio_coords)
                        camino_vial, _ = obtener_ruta_calles_osrm(puntos_circuito)
                        folium.PolyLine(camino_vial, color="#1A73E8", weight=6, opacity=0.85).add_to(m)
                    
                    st.components.v1.html(m._repr_html_(), height=540, scrolling=False)
                    
                st.markdown("---")
                st.subheader(f"💼 Tabla de Prospectos Comerciales dentro de la zona de cobertura (≤ 2 Km de la Ruta)")
                
                if file_prospectos is None:
                    st.info("Por favor, suba el archivo de Prospectos en el panel izquierdo para visualizar este módulo.")
                elif df_prospectos_radio_2km.empty:
                    st.info("No se localizan prospectos de esta actividad económica en un radio de 2 Km para la ruta de este día.")
                else:
                    seleccion_prospecto = st.dataframe(
                        df_prospectos_radio_2km[["Nombre de la Unidad Económica", "Clase de actividad SCIAN", "Domicilio", "Latitud", "Longitud"]],
                        height=280, use_container_width=True, hide_index=False,
                        on_select="rerun", selection_mode="single-row"
                    )
                    
                    if seleccion_prospecto and "rows" in seleccion_prospecto.get("selection", {}):
                        idx_pros_sel = seleccion_prospecto["selection"]["rows"]
                        if idx_pros_sel:
                            idx_real = idx_pros_sel[0]
                            st.markdown(f"<div style='background-color: #FFC0CB; padding: 12px; border-radius: 6px; border-left: 5px solid #FF69B4; color: black;'>"
                                        f"<b>🎯 DETALLES DEL PROSPECTO SELECCIONADO:</b><br>"
                                        f"• <b>Unidad Económica:</b> {df_prospectos_radio_2km.iloc[idx_real]['Nombre de la Unidad Económica']}<br>"
                                        f"• <b>Actividad SCIAN:</b> {df_prospectos_radio_2km.iloc[idx_real]['Clase de actividad SCIAN']}<br>"
                                        f"• <b>Domicilio:</b> {df_prospectos_radio_2km.iloc[idx_real]['Domicilio']}<br>"
                                        f"• <b>Coordenadas:</b> Lat: {df_prospectos_radio_2km.iloc[idx_real]['Latitud']}, Lon: {df_prospectos_radio_2km.iloc[idx_real]['Longitud']}"
                                        f"</div>", unsafe_allow_html=True)
                
            st.markdown("---")
            st.subheader(f"📅 Plan Mensual Consolidado Unificado ({mes_nombre} {anio_seleccionado})")
            df_mensual_formato = df_agenda_mes.copy()
            df_mensual_formato['Venta_Mensual_Calculada'] = df_mensual_formato['Venta_Mensual_Calculada'].map("${:,.2f}".format)
            st.dataframe(
                df_mensual_formato[['Día del Mes', 'Orden Visita', 'ID_Cliente', 'Cliente', 'Domicilio', 'Clasificación ABC', 'Secuencia Frecuencia', 'Hora de llegada al punto', 'Tiempo de visita', 'Hora de Salida', 'Tiempo de trayecto a próximo cliente', 'Kilómetros a próximo cliente', 'Venta_Mensual_Calculada']], 
                height=400, use_container_width=True, hide_index=True
            )

    if not es_dia_vacio and len(puntos_circuito) > 1:
                    # Generamos el link enviándole la lista 'puntos_circuito'
                     link_maps = generar_link_google_maps(puntos_circuito)
                    
                    # Desplegamos el botón interactivo justo debajo del mapa
    st.link_button(
                        label="🗺️ Abrir ruta completa en Google Maps",
                        url=link_maps,
                        use_container_width=True
                    )

    # --- PESTAÑA: PEDIDO SUGERIDO Y ANÁLISIS ---
    with tab_sugerido:
        st.header("📊 Módulo de Pedido Sugerido por Marca")

        fecha_eval_sug = st.date_input(
            "Seleccione Fecha para evaluar Pedido Sugerido del cliente:",
            value=date(anio_seleccionado, mes_numerico, 1),
            key="fecha_sug_input"
        )

        df_ag_dia = df_agenda_mes[df_agenda_mes['Fecha_Raw'] == fecha_eval_sug] if df_agenda_mes is not None and not df_agenda_mes.empty else pd.DataFrame()
        
        opciones_clientes = []
        if not df_ag_dia.empty:
            cls_unicos = df_ag_dia[df_ag_dia['ID_Cliente'] != '-'][['ID_Cliente', 'Cliente']].drop_duplicates()
            for _, r_cl in cls_unicos.iterrows():
                opciones_clientes.append(f"{r_cl['ID_Cliente']} - {r_cl['Cliente']}")

        cliente_sel_sug = st.selectbox("Filtrar Pedido por Cliente Agendado Hoy:", ["TODOS"] + opciones_clientes)

        if st.button("🚀 Generar Análisis y Pedido Sugerido"):
            if not (f_ranking or os.path.exists(r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\RANKING FERRETEROS.xlsx")):
                st.error("Falta el archivo de RANKING FERRETEROS.")
            else:
                input_rk = f_ranking or r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\RANKING FERRETEROS.xlsx"
                input_vt = f_ventas or r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\VENTAS FERRETEROS.xlsx"
                input_dm = f_demanda or r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\Demanda.xlsx"
                input_ms = f_master or r"C:\Users\lmacias\Desktop\PROYECCIÓN DE VENTA 2027\MASTER DE CLIENTES.xlsx"

                cl_id_pass = None if cliente_sel_sug == "TODOS" else cliente_sel_sug.split(" - ")[0]

                res_dict, err_msg, anio_extraido = procesar_pedido_sugerido(
                    id_vendedor=id_vendedor,
                    fecha_evaluada=fecha_eval_sug,
                    df_agenda_vendedor=df_agenda_mes,
                    f_ranking=input_rk,
                    f_ventas=input_vt,
                    f_demanda=input_dm,
                    f_master=input_ms,
                    cliente_id_seleccionado=cl_id_pass
                )

                if err_msg:
                    st.error(err_msg)
                else:
                    st.success("Cálculo finalizado exitosamente.")

                    config_cols_sugerido = {
                        "Marca": st.column_config.TextColumn("Marca", width="medium"),
                        "Código de Producto": st.column_config.TextColumn("Código de Producto", width="small"),
                        "DESCRIPCIÓN": st.column_config.TextColumn("DESCRIPCIÓN", width="large"),
                        "Sugerido": st.column_config.NumberColumn("Sugerido", width="small", format="%d"),
                        "Avance": st.column_config.NumberColumn("Avance", width="small", format="%d"),
                        "Indicador": st.column_config.TextColumn("Indicador", width="small"),
                        "Ultimo mes de Venta": st.column_config.TextColumn("Ultimo mes de Venta", width="small"),
                    }

                    cols_visibles = [
                        "Marca", "Código de Producto", "DESCRIPCIÓN", 
                        "Sugerido", "Avance", "Indicador", "Ultimo mes de Venta"
                    ]

                    # 1. Función para mostrar la tabla completa DESAGRUPADA por marca
                    def desplegar_tabla_desagrupada(df_datos, titulo_seccion):
                        st.subheader(titulo_seccion)
                        if df_datos.empty:
                            st.info("No hay registros disponibles para esta categoría.")
                            return
                        
                        cols_a_mostrar = [c for c in cols_visibles if c in df_datos.columns]
                        st.dataframe(
                            df_datos[cols_a_mostrar], 
                            use_container_width=True, 
                            hide_index=True, 
                            column_config=config_cols_sugerido
                        )

                    # 2. Función para mostrar la tabla AGRUPADA por marca (exclusiva para Oportunidades)
                    def desplegar_tabla_agrupada_por_marca(df_datos, titulo_seccion):
                        st.subheader(titulo_seccion)
                        if df_datos.empty:
                            st.info("No hay registros disponibles para esta categoría.")
                            return
                        
                        marcas = df_datos["Marca"].unique()
                        for m in marcas:
                            df_m = df_datos[df_datos["Marca"] == m]
                            cols_a_mostrar = [c for c in cols_visibles if c in df_m.columns]
                            
                            with st.expander(f"📌 **Marca: {m}** ({len(df_m)} productos)"):
                                st.dataframe(
                                    df_m[cols_a_mostrar], 
                                    use_container_width=True, 
                                    hide_index=True, 
                                    column_config=config_cols_sugerido
                                )

                    # --- RENDERIZADO DE TABLAS ---
                    # Las primeras 3 tablas se muestran en vista continua (DESAGRUPADAS)
                    desplegar_tabla_desagrupada(res_dict["pedido"], "PEDIDO SUGERIDO (TUS PRODUCTOS MÁS VENDIDOS 80/20)")
                    desplegar_tabla_desagrupada(res_dict["intermitente"], "PRODUCTOS CON VENTA INTERMITENTE")
                    desplegar_tabla_desagrupada(res_dict["recuperar_20"], "PRODUCTOS A RECUPERAR 20%")
                    
                    # Únicamente OPORTUNIDADES se mantiene con acordeones agrupados por Marca
                    desplegar_tabla_agrupada_por_marca(res_dict["oportunidades"], "OPORTUNIDADES (PRODUCTOS DE CANAL)")

    # --- PESTAÑA: PEDIDO SUGERIDO CLIENTES NUEVOS ---
    with tab_prospectos_sug:
        st.header("✨ Pedido Sugerido Clientes Nuevos")
        
        input_sug_pros = f_sug_prospectos or r"C:\Users\lmacias\Desktop\PEDIDOS SUGERIDOS\CLIENTES NUEVOS\PEDIDO SUGERIDO PROSPECTOS.xlsx"
        df_prospectos_sug = cargar_dataframe_flexible(input_sug_pros, nombre_defecto="PEDIDO SUGERIDO PROSPECTOS.xlsx", sheet_name="SUGERIDO FINAL")
        
        if df_prospectos_sug is not None and not df_prospectos_sug.empty:
            try:
                col_propuesta = None
                for col in df_prospectos_sug.columns:
                    if col.upper() == "PROPUESTA":
                        col_propuesta = col
                        break

                if col_propuesta:
                    suma_propuesta = pd.to_numeric(df_prospectos_sug[col_propuesta], errors="coerce").fillna(0).sum()
                    st.metric("📦 Suma Total de Propuesta", f"{int(round(suma_propuesta)):,} piezas")
                else:
                    st.warning("No se encontró una columna llamada 'PROPUESTA' en la hoja 'SUGERIDO FINAL'.")

                st.subheader("Pedido Sugerido Clientes Nuevos (Detalle)")

                def aplicar_resaltado_verde_celda(val):
                    try:
                        if float(val) > 0:
                            return 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                    except:
                        pass
                    return ''

                cols_numericas = df_prospectos_sug.select_dtypes(include=[np.number]).columns.tolist()
                df_pros_styled = df_prospectos_sug.style.applymap(aplicar_resaltado_verde_celda, subset=cols_numericas) if cols_numericas else df_prospectos_sug

                st.dataframe(df_pros_styled, use_container_width=True, hide_index=True)

            except Exception as e:
                st.error(f"Error al procesar la hoja 'SUGERIDO FINAL': {str(e)}")
        else:
            st.error("No se pudo cargar el archivo Excel. Asegúrese de subirlo desde el panel lateral o verificar la ruta predeterminada.")

else:
    st.info("Por favor, cargue las bases maestras en el panel lateral para iniciar la suite.")
