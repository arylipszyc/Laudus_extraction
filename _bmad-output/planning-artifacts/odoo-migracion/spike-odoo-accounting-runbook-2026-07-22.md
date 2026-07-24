# Spike Odoo Community — Runbook

**Fecha:** 2026-07-22 · **Autor:** Ary (+ Claude)
**Objetivo:** validar con datos, antes de comprometer meses, si Odoo Community resuelve los
dolores reales con Beancount (UI de contador, maestros editables, reportería, dev en un solo
ecosistema) **sin** que el import de Laudus ni el multi-company sean un problema.

Este spike NO decide la migración. Contesta tres preguntas con evidencia:

1. **¿El import de Laudus sale limpio y cuadra?** (el miedo #1: traer la data correcta)
2. **¿La reportería/UI de Odoo es tan mejor para el contador como creemos?**
3. **¿Desarrollar en Odoo es tan simple como esperamos?** (módulos Python en un solo entorno)

Criterio transversal: si al terminar seguimos sin poder responder sí/no a las tres, el spike
falló en diseño, no Odoo.

---

## Criterios de éxito (✓/✗ objetivos)

| # | Prueba | PASS si… |
|---|--------|----------|
| 1 | **Import** | Cargan las 2 companies (EAG + RUT2) para 2026-05 y el **Balance/P&L de EAG en Odoo matchea el número ya validado** contra el contador (workbook "Gastos EAG 05-2026"). Se mide cuánto costó. |
| 2 | **Reportes** | Los reportes OCA (Balance, P&L, Mayor) salen y **Valentina los lee sin que se los expliques**. |
| 3 | **Dev** | Construís **una** cosa chica (un reporte custom o vista filtrada) y la sacás en tiempo acotado sin ahogarte en el framework. |

**Hoja de respuestas (ground truth):** mes **2026-05**. Ya cuadra al peso en Beancount, así
que el import se valida contra un número conocido, no contra la nada.

---

## Estado — lo que ya está hecho (parte Claude)

La data ya está exportada y **balancea al peso**. Corrido hoy contra `ledger/main.beancount`
(0 errores de carga):

```
accounts_EAG.csv       257 cuentas
accounts_RUT2.csv      311 cuentas
moves_EAG_2026-05.csv    87 asientos, 253 patas, debe = haber (desc = 0)
moves_RUT2_2026-05.csv  129 asientos, 402 patas, debe = haber (desc = 0)
```

Artefactos en `_spike-odoo/`:
- `export_laudus_to_odoo.py` — regenera los CSV: `../venv/Scripts/python.exe export_laudus_to_odoo.py 2026 5`
- `csv/` — los 4 CSV listos para importar (formato o2m nativo de Odoo)
- `docker-compose.yml` + `odoo.conf` — stack del VPS

**Mapeo de entidades (clave del multi-company):** el campo `entity` del asiento es la entidad
LEGAL → la Company de Odoo. EAG (+ hijas Jael/Jeannette/Jocelyn/Johanna) = company **EAG**;
FFCC/JAB = company **RUT2**. El plan de cuentas se parte por company con el mismo criterio.

---

## Parte 1 — Montar el VPS (tu acción, ~1–2 h)

Un VPS es una máquina Linux arrendada donde vos administrás todo (a diferencia de Render). Para
el spike se endurece lo mínimo; la carga real de sysadmin (backups, SSL, upgrades) es tema de
producción, NO de este spike.

1. **Arrendar** un Hetzner **CPX21** (3 vCPU AMD / 4 GB / 80 GB, ~€7,6 mes) en **Ashburn, VA
   (US-East)** — mejor latencia desde Chile. Ubuntu 24.04. (El CX22 es solo-EU; desde Chile
   conviene US. Odoo pide 2 GB+ real; con 4 GB y 3 vCPU andás cómodo.)
2. **Entrar** por SSH (la llave ed25519 de Ary ya existe en `~/.ssh/id_ed25519.pub`). Firewall
   Hetzner con dos reglas inbound limitadas a tu IP: **22** (SSH) y **8069** (Odoo) — no expongas
   Odoo abierto al mundo.
3. **Instalar Docker**: `curl -fsSL https://get.docker.com | sh`
4. **Copiar** la carpeta `_spike-odoo/` al VPS (scp o git).
5. **OCA reportes** (antes de levantar):
   ```
   cd _spike-odoo
   git clone --depth 1 -b 18.0 https://github.com/OCA/account-financial-reporting addons/account-financial-reporting
   ```
6. **Cambiar** las 3 passwords en `docker-compose.yml` y `odoo.conf`.
7. **Levantar**: `docker compose up -d` → Odoo en `http://<IP>:8069`.

> Nota versión: el compose usa **Odoo 18** (rama OCA madura). Si preferís 19, cambiá `image:
> odoo:19` y la rama del clone a `19.0` — confirmá que el módulo OCA tenga esa rama antes.

---

## Parte 2 — Odoo inicial (~30 min)

1. En `http://<IP>:8069` crear la base (usa el master password de `odoo.conf`). Idioma es_419,
   moneda CLP.
2. Instalar la app **Contabilidad** (Accounting/Invoicing) y **Facturación**.
3. Activar **modo desarrollador** (Ajustes → al final) — necesario para import y para el reporte custom.
4. Instalar los módulos OCA: **Aplicaciones → quitar filtro "Apps" → buscar
   `account_financial_report`** → instalar (arrastra sus dependencias).
5. **Multi-company**: Ajustes → activar "Multi-empresas". Crear las dos compañías:
   **EAG** y **RUT2**. (La empresa por defecto renómbrala a EAG.)

---

## Parte 3 — Import del plan de cuentas (~30 min, 2 archivos)

Por cada company, con esa company activa en el selector:

1. Contabilidad → Configuración → **Plan de cuentas** → menú ⚙ → **Importar registros**.
2. Subir `accounts_EAG.csv` (con EAG activa) / `accounts_RUT2.csv` (con RUT2 activa).
3. Mapear columnas: `id`→ID externo, `code`, `name`, `account_type`, `currency`→Moneda.
   (`laudus_group` es de referencia; los grupos jerárquicos se pueden armar después.)

> El `account_type` viene con un mapeo grueso (asset_current / asset_cash / liability_current /
> equity / income / expense). Suficiente para que los reportes agrupen; se afina si hace falta.

**Diario:** en cada company crear un diario tipo "Varios" llamado exactamente **"Diario Laudus"**
(los CSV de asientos lo referencian por nombre).

---

## Parte 4 — Import de asientos (~30 min, 2 archivos)

Por company activa: Contabilidad → Asientos contables → menú ⚙ → **Importar**.
- EAG activa → `moves_EAG_2026-05.csv`
- RUT2 activa → `moves_RUT2_2026-05.csv`

El CSV ya trae el formato padre/hijas (id de asiento en la 1ª fila, patas siguientes con id
vacío). Al terminar, los asientos quedan en borrador → **seleccionar todo → Publicar/Asentar**.

**Chequeo inmediato:** cada asiento debe publicar sin error de descuadre (ya validamos desc = 0
en el export). Si alguno falla, casi seguro es una cuenta faltante en el plan → volver a Parte 3.

---

## Parte 5 — Validación vs ground truth (la prueba #1)

Con EAG activa, período mayo 2026:
- **Balance general** y **Estado de resultados** (reportes OCA).
- Comparar contra el workbook del contador "Gastos EAG 05-2026" que ya cuadra en Beancount.

PASS = los totales de gasto por cuenta de EAG-mayo **coinciden** con el número conocido.
(Es el mismo criterio de paridad que usamos para validar Beancount; reutilizamos la respuesta.)

---

## Parte 6 — Reporte custom (la prueba #3)

Construir **una** cosa chica para medir el esfuerzo real de desarrollar en Odoo. Opciones (elegí una):
- Un **reporte pivote** guardado: gastos por `laudus_group` × mes (sin código, solo UI) — mide "¿me
  alcanza con la UI?".
- O un **módulo mínimo** en Python: un reporte QWeb sencillo o un campo calculado — mide "¿es simple
  desarrollar en el ecosistema Odoo?".

Registrar honestamente: cuánto tardaste, dónde te trabaste, si el LLM te sacó rápido del pozo.

---

## Qué NO cubre este spike (para ir con los ojos abiertos)

- **No** testea la carga operativa de producción (SSL, backups, upgrades mayores) — eso aparece
  después si Odoo va en serio.
- **No** migra la reconciliación ni el desglose TC (dijiste que no es la preocupación; se rehace
  como spec si se decide migrar).
- **No** trae histórico 2021→hoy — solo un mes, a propósito.
- La **consolidación** EAG+RUT2 en un solo reporte es Enterprise nativo; en Community se arma
  custom (igual que el roots-only de hoy). Fuera de este spike.

---

## Decisión al cerrar

Con las 3 pruebas respondidas: si las tres dan PASS y el esfuerzo de import/dev fue razonable →
hay caso sólido para planificar la migración como greenfield. Si el import fue peleado, o la UI
no sumó tanto, o desarrollar en Odoo fue un pozo → se queda en Beancount y se ataca la UI del
contador incremental sobre lo actual. Cualquiera de los dos resultados es un éxito del spike.
