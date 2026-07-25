# Deferred Work

Trabajo real pero no bloqueante, diferido con su razón. Revisar al retomar el epic/story asociado.

## Deferred from: code review of E1-0-scaffold-pipeline-migracion (2026-07-24)

- **[Smoke Tier B] El smoke escribe el stub en la carpeta de addons compartida del spike** — `pipeline/odoo_migration/tests/test_odoo_smoke.py`. El compose del spike monta `./addons:/mnt/extra-addons` (bind mount), así que `odoo scaffold x_laudus_smoke /mnt/extra-addons` escribe en `_spike-odoo/addons/x_laudus_smoke` (dir compartido con el stack del spike), y en Linux los archivos root-owned harían fallar el `shutil.rmtree` de teardown (tragado por `ignore_errors=True`) dejando residuo. El aislamiento por project-name cubre volúmenes, no este bind mount del host. Impacto bajo: Tier B es opt-in (no corre por-commit) y se auto-limpia en el happy path. **Razón del defer:** el README ya declara que **E1.1 promoverá su propio compose** cuando monte el addon real — natural resolver el teardown/mount aislado ahí en vez de endurecer un compose que se va a reemplazar.

## Deferred from: code review of E1-1-modulo-odoo-x-laudus-migration (2026-07-24)

- **[Hook] `del registry._auto_install_template` depende de un interno privado de Odoo + tag flotante `odoo:18`** — `pipeline/odoo_migration/addons/x_laudus_migration/hooks.py`. Si un point release de Odoo 18 renombra/mueve ese mecanismo, el guard `hasattr` convierte la cancelación en no-op silencioso y el CoA genérico se cargaría (borrando LAU1). Mitigado: la regresión la pescan los tests Tier B (conteo de diarios; el patch de asserts del review propone además un assert directo `count(account_account)==0`). Pinnear la imagen (digest/tag fechado) es una decisión de stack que afecta también al compose del spike — resolver cuando se levante el VPS (entorno definitivo).
- **[Smoke Tier B] `up -d` fallido → `pytest.skip` enmascara causas reales** — `pipeline/odoo_migration/tests/test_x_laudus_migration_install.py`. Un fallo de `docker compose up` (puerto 8070 ocupado, compose inválido, pull fallido) se reporta como skip "¿daemon Docker abajo?" y el gate de release no corre pareciendo verde. Mismo patrón ya adjudicado en el smoke de E1.0 (`test_odoo_smoke.py`) — si se endurece, endurecer ambos a la vez (skip solo si docker no está / daemon no responde; fail en el resto).

