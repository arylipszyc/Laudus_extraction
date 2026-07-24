# Deferred Work

Trabajo real pero no bloqueante, diferido con su razón. Revisar al retomar el epic/story asociado.

## Deferred from: code review of E1-0-scaffold-pipeline-migracion (2026-07-24)

- **[Smoke Tier B] El smoke escribe el stub en la carpeta de addons compartida del spike** — `pipeline/odoo_migration/tests/test_odoo_smoke.py`. El compose del spike monta `./addons:/mnt/extra-addons` (bind mount), así que `odoo scaffold x_laudus_smoke /mnt/extra-addons` escribe en `_spike-odoo/addons/x_laudus_smoke` (dir compartido con el stack del spike), y en Linux los archivos root-owned harían fallar el `shutil.rmtree` de teardown (tragado por `ignore_errors=True`) dejando residuo. El aislamiento por project-name cubre volúmenes, no este bind mount del host. Impacto bajo: Tier B es opt-in (no corre por-commit) y se auto-limpia en el happy path. **Razón del defer:** el README ya declara que **E1.1 promoverá su propio compose** cuando monte el addon real — natural resolver el teardown/mount aislado ahí en vez de endurecer un compose que se va a reemplazar.
