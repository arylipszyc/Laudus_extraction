# pipeline.odoo_migration — pipeline de migración Laudus (espejo Beancount) → Odoo.
#
# Track autónomo de Epic E1 (Fase 1a). Distinto del `pipeline/` de sync Laudus→Sheets:
# acá el transformador es Python puro testeable SIN Odoo levantado (Tier A, por-commit)
# y el loader (E1.5) es el único que toca Odoo (Tier B, opt-in). Ver README.md.
