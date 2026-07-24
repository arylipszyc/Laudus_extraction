# Guion — Demo a los contadores (firma Laudus)

**Fecha reunión:** 2026-07-21 · **Presenta:** Ary
**Objetivo:** mostrar que lo construido **cuadra peso-a-peso con el trabajo de ellos** y acordar los **próximos pasos / handoff**.
**Tono:** colaborativo. No es "les vengo a auditar". Es "construimos un sistema que refleja fiel su contabilidad y ahora queremos cerrar juntos las brechas que ni Laudus ni ustedes pueden cerrar sin las cartolas del custodio".

---

## 0. Pre-flight (10 min ANTES de que lleguen)

Chequear que la demo en vivo no se caiga:

- [ ] **Login como contador/admin** — casi todas las pantallas de reportes están gated a rol `contador`/`admin`. Con un login de solo-familia NO aparecen en el sidebar.
- [ ] **Sync fresco** — en `/reportes`, botón "Sincronizar ahora" y revisar la línea "Datos de Laudus al: <fecha>". Que diga hoy/ayer, no una fecha vieja. (El backend clona el ledger al arrancar; si estuvo dormido, un cold-start puede tardar.)
- [ ] **Fava abierto en una pestaña aparte** — es un servicio separado (`laudus-fava`), con basic-auth, fuera de esta app. Tener la URL + credenciales a mano. Que cargue ANTES.
- [ ] **Un xlsx de ellos a la vista** — tener abierto el workbook "Gastos EAG" de ellos (ene–may) para poner al lado del que genera la app. Ese lado-a-lado ES la demo.
- [ ] **Una cartola PDF real a mano** para la carga en vivo (paso 6). Si preferís no arriesgar la extracción en vivo, salteá la carga y mostrá solo el resultado ya cargado.
- [ ] Dry-run completo una vez, solo. Que cada pantalla que vas a tocar cargue sin error.

---

## 1. Encuadre (2 min, sin pantalla)

Una sola idea antes de abrir nada:

> "Construimos un sistema que toma lo que ustedes cargan en Laudus y lo mantiene como un **libro contable propio, reconciliado al peso**. No reemplaza su trabajo: lo **refleja fiel y lo verifica**. Hoy les quiero mostrar tres cosas: (1) que cuadra exactamente con lo que ustedes producen, (2) qué cosas ya podemos ver que antes no se veían, y (3) dónde los necesitamos a ustedes para cerrar las brechas que ni Laudus ni nadie puede cerrar sin las cartolas de los custodios."

**Por qué este encuadre:** más adelante vas a mostrar hallazgos que técnicamente son limitaciones de cómo Laudus registra (flujos en CLP, sin revalorizar). Si desde el minuto uno el marco es "sistema espejo que verifica + colaboración", esos hallazgos aterrizan como *trabajo conjunto pendiente*, no como *"ustedes se equivocaron"*.

---

## 2. El corazón: "cuadra al peso" — Reporte de Gastos

**Pantalla:** `Reporte de Gastos` (`/reportes`)

**Mostrar:**
1. Libro = **EAG**, rango **2025-01-01 → 2025-05-31**. "Generar y descargar" → se baja un **xlsx**.
2. Abrir ese xlsx **al lado del workbook de ellos** ("Gastos EAG 05-2026.xlsx").
3. Recorrer 2-3 cuentas y mostrar que el número es **idéntico**.

**Decir:**
> "Esto no lo tipeamos: sale del mismo Laudus que ustedes cargan, leído por nuestro motor. Cuenta por cuenta, mes por mes, da lo mismo que su planilla. Itemiza además cada sociedad hija por separado."

**Respaldo (por si preguntan la base):** el reporte se lee de Beancount (nuestro libro), no de una copia de la planilla. Cuadra peso-a-peso con el workbook "Gastos EAG" de ellos para ene–may. Descubrimos de paso que las diferencias que ANTES aparecían venían de que la versión vieja (Google Sheets) contaba "saldo anterior" (saldos de apertura) como gasto — nuestro motor lee Laudus vivo y no arrastra ese error.

**Ojo / lo que NO hay que prometer:** el reporte descarga un xlsx (no es una tabla en pantalla). Las celdas en blanco (desglose de TC, clasificación manual) las llena el contador; los subtotales son fórmulas. Decilo: "está pensado para que ustedes lo completen, no para reemplazarlos".

---

## 3. Patrimonio de un vistazo — Balance (Activos / Pasivos)

**Pantalla:** `Activos / Pasivos` (`/dashboard/balance-sheet`)

**Mostrar:** las tres tarjetas de arriba (Total Activos, Total Pasivos, Patrimonio Neto) y las tablas agrupadas (Activos / Pasivos / Patrimonio). Señalar el "Último sync".

**Decir:**
> "El mismo libro que produce el reporte de gastos arma el balance consolidado — EAG con sus sociedades hijas incluidas. Es el balance que le pasamos a ustedes en borrador."

**Respaldo:** balance consolidado (EAG = EAG + hijas), motor de Beancount, flip hecho (ya no lee Sheets). Hay un borrador que ya se generó para el contador.

**Puente al paso 9 (importante, sembrar acá la semilla):** cuando muestres el balance, mencioná al pasar —
> "Un detalle honesto: este balance refleja **lo que pasa por Laudus**. Las inversiones y lo offshore están al valor congelado con que entraron, no a valor de mercado de hoy. Ahí, más adelante, los vamos a necesitar."

Eso deja plantado el pedido del paso 9 sin sonar a reproche.

---

## 4. Lo visual que antes no se veía — Ingresos / Gastos

**Pantalla:** `Ingresos / Gastos` (`/dashboard/income-expenses`)

**Mostrar:** el pie de composición (gastos/ingresos), la línea de tiempo, y hacer un drill-down en una categoría.

**Decir:**
> "Esto es lo que Laudus no les da masticado: composición y evolución en el tiempo, con drill-down. Mismo dato, otra lectura."

Screen corta, de impacto visual. No te detengas mucho.

---

## 5. Multi-entidad: el 2º RUT (Fondo Común FFCC/JAB)

**Pantalla:** `Reporte de Gastos` (`/reportes`) — Libro = **Fondo Común (FFCC/JAB)**

**Mostrar:** generar el xlsx del Fondo Común. Tiene **dos hojas**: **Gastos** (por encabezado) y **Distribuciones** (cuenta corriente de cada socio: retiros, repartos, saldo).

**Decir:**
> "El sistema no está atado a una sola entidad. El Fondo Común vive como entidad hermana en el mismo libro, reconciliado también al peso contra Laudus. Consolidamos por grupos."

**Respaldo:** RUT2 reconciliado 0 diffs / 237 cuentas (DoD PASS). Distribuciones = cuentas corriente de socios (cuenta 115xxx).

**Lo que NO hay que sobre-vender (el reporte ya lo advierte, respetalo):** el balance del Fondo Común está **incompleto** — inversiones y activos reales (yate, avión, etc.) no están cargados, así que **no representa el patrimonio real del fondo**. Es el mismo problema que EAG y **enlaza directo con el pedido del paso 9**. Decilo vos antes de que lo pregunten: da credibilidad.

---

## 6. Conciliación bancaria contra cartola (en vivo)

**Pantalla A:** `Reconciliación` (`/reconciliation`)

**Mostrar:** la tabla de **Períodos reconciliados** (cuenta, mes, estado ✓Completo / N pendientes) y la tabla de discrepancias con sus filtros y badges. Abrir una discrepancia → panel lateral para resolver (confirmar-cartola / confirmar-Laudus / escalar, con justificación) e historial.

**Decir:**
> "Acá cruzamos la cartola del banco contra Laudus, línea por línea. Lo que no calza queda marcado con su motivo, y se resuelve con una decisión trazable — queda el historial de quién y por qué."

**Pantalla B (opcional, en vivo):** `Cargar Cartola` (`/upload`)
- Subir un PDF de cartola → extracción automática (Gemini) → panel de validación de saldos (apertura/cierre) → panel de cuadre.
- **Decir:** "La cartola entra como PDF, la leemos automáticamente y validamos que el saldo de apertura/cierre calce antes de importar."
- **Riesgo:** la extracción en vivo puede tardar o fallar con un PDF difícil. Si no querés arriesgar, mostrá una cartola **ya cargada** y salteá la subida.

---

## 7. Tarjetas de crédito — Cuadre TC

**Pantalla:** `Cuadre TC` (`/cuadre-tc`)

**Mostrar:** la **matriz de cobertura** (tarjeta × mes, celdas 🟢🟡🔴). Elegir una tarjeta y abrir la cascada del mes (saldo anterior → pago → compras → cargos → abonos → saldo contable vs cierre cartola), señalando los checks **C1–C5**.

**Decir:**
> "Las tarjetas son un pasivo, no un gasto, y son las más difíciles de cuadrar. El sistema verifica cinco cosas por tarjeta y por mes; C1 es la clave: deuda contable vs cierre de la cartola. Hoy todas las tarjetas están cuadradas al peso."

**Respaldo (números concretos por si preguntan):** todas materializadas — 1027 CLP −3.219.948 / 1027 USD −23.543.848 / 8996 CLP −4.448.873 / 0858 CLP −7.466.345 / 8996 USD −1.124.166 (feb→may, incluida la lógica de FX heredado para el mes revolving sin pago propio).

---

## 8. Cómo vamos a trabajar juntos — Colaboración + Fava

**Pantalla A:** `Comentarios` (`/comments`)
- **Mostrar:** los hilos de comentarios sobre transacciones entre dueño y contador.
- **Decir:** "Cuando algo necesita una aclaración de ustedes, se comenta sobre la transacción misma y queda registrado. No más mails sueltos."

**Pantalla B (pestaña aparte):** **Fava**
- **Decir:** "Y para ustedes, como contadores, hay una vista técnica completa del libro — Fava — donde tienen estado de resultado, balance, balance de comprobación, y hasta pueden editar con una red de seguridad que valida el libro antes de aceptar el cambio. Esto es solo para ustedes, la familia no entra acá."
- Mostrar rápido: Income Statement o Trial Balance en Fava.
- **Por qué en Fava:** las pantallas "Estado de Resultado" y "Variación Patrimonial" de la app todavía son placeholders. Para estado de resultado, mostrá el de Fava, no el de la app.

---

## 9. Pasos a seguir — LA conversación (el verdadero objetivo)

Encuadre:
> "Todo lo que vieron cuadra con lo que ustedes producen. Pero hay una brecha que **ninguno de los dos puede cerrar solo**, y es donde los necesito."

### Pedido #1 (el grande): cartolas de los custodios de inversiones/offshore
- **El hallazgo, en su versión colaborativa:** Laudus es un excelente libro de **flujos en pesos**, pero no es un estado de **patrimonio a valor de mercado**. Las inversiones entraron a Laudus ya convertidas a CLP al dólar del día, y nunca se revalorizaron. Resultado: el libro **subvalúa** esas cuentas.
- **El ejemplo que impacta (Julius Baer):** el libro muestra ~436 millones CLP en esa cuenta. La cartola real del custodio al 30-06-2025 da **USD 15,4 millones** (≈14.500 millones CLP). El libro muestra ~3% del valor real — no por error de nadie, sino porque Laudus registra el flujo, no la posición.
- **El pedido concreto:** las **cartolas/valorizaciones de los custodios** (Julius Baer y los demás vehículos). Con eso anclamos el patrimonio real, en CLP y en USD, a cualquier fecha.
- **Framing clave:** "esto NO es algo que ustedes hicieron mal — es información que vive en el custodio, no en Laudus".

### Pedido #2: separar capital de ganancia en los retiros de inversión
- **El hallazgo (decir que es de Laudus, no de ellos):** los rescates/retiros de inversión hoy no separan **capital** de **ganancia**. Ejemplo limpio: "Nuevo Ciclo — devolución de préstamos": se cobraron 5.963M, pero el activo sigue mostrando los 2.273M completos y todo se fue a ingreso.
- **Por qué NO lo pescó la reconciliación:** "quiero ser transparente — nuestra validación de paridad da 100% justamente porque **copia fiel a Laudus**; este tema está DENTRO de Laudus, en ambos lados, así que la paridad no lo detecta. Lo encontramos mirando la lógica contable, no comparando números."
- **El pedido:** para cada vehículo (Tecnion, Nuevo Ciclo, MBI, Julius Baer, fondos BCI), el **saldo real confirmado por el custodio**. Con eso reclasificamos capital vs ganancia. Sin ese número, no tocamos nada — corregir con un número inventado es peor.

### Pedido #3: la rama AZBA sin liquidar (yate / avión)
- Hay operaciones de activos (yate Keiki Kai, avión, Leo Partnership) que Laudus mete por cuentas corriente de socios, sin una **cuenta de activo** para el yate o el avión. La rama AZBA queda ≈ −2.490M sin liquidar en cash.
- **El pedido:** definir con ellos cómo se registra ese activo (existe una cuenta, hay que crearla, cuál es el valor).

### Cierre: cómo seguimos
> "Propongo: ustedes nos consiguen las cartolas de los custodios, y nosotros armamos el reporte de patrimonio real dual (CLP/USD) anclado a esas cartolas. Mientras tanto, seguimos con el flujo de siempre — ustedes cargan Laudus, el sistema reconcilia, y lo que necesite aclaración se comenta sobre la transacción."

---

## Anexo A — Cifras de respaldo (para tener a mano, no para leer)

| Afirmación | Cifra |
|---|---|
| Reporte de gastos EAG cuadra vs workbook del contador | peso-a-peso, ene–may |
| RUT2 (Fondo Común) reconciliado vs Laudus | 0 diffs / 237 cuentas (DoD PASS) |
| Validación de cartolas (smoke) | 13/14 = 92,9% |
| Tarjetas de crédito cuadradas al peso | 1027 CLP −3.219.948 · 1027 USD −23.543.848 · 8996 CLP −4.448.873 · 0858 CLP −7.466.345 · 8996 USD −1.124.166 |
| Julius Baer: libro vs custodio real (30-06-2025) | 436M CLP (~USD 465k) vs **USD 15,4M** (≈14.500M CLP) |
| Retiros de inversión a ingreso sin bajar activo (Error A) | ≈ 26.193M CLP |
| Rama AZBA sin liquidar | ≈ −2.490M CLP |

## Anexo B — Qué NO mostrar / trampas

- **NO abrir** "Estado de Resultado" ni "Variación Patrimonial" en la app → son placeholders vacíos. Estado de resultado = Fava.
- El reporte de gastos **descarga xlsx**, no muestra tabla en pantalla. Tené el archivo listo para abrir.
- Casi todo reporte está gated a rol **contador/admin** → logueate con ese rol o el sidebar aparece pelado.
- La carga de cartola en vivo puede fallar con un PDF difícil → plan B: mostrar una ya cargada.
- Fava es una **pestaña/URL aparte** (no está embebida). Abrila y logueate antes.
- Si el backend estuvo dormido (plan Render), el primer request es lento (cold start). Despertalo en el pre-flight.

## Anexo C — Orden sugerido (si el tiempo es corto, hacé los ★)

1. ★ Encuadre (§1)
2. ★★ Reporte de Gastos EAG lado-a-lado (§2) — *el corazón*
3. Balance (§3) + sembrar semilla del pedido
4. Ingresos/Gastos visual (§4)
5. Fondo Común / 2º RUT (§5)
6. Conciliación + cartola (§6)
7. Cuadre TC (§7)
8. Comentarios + Fava (§8)
9. ★★★ Pasos a seguir (§9) — *el verdadero objetivo de la reunión*
