"""Tests para bootstrap.account_mapping — Story 9.1 Task 2 (lógica pura)."""
import pytest

from bootstrap.account_mapping import (
    UnknownBankAccountType,
    UnmappableCategoria1,
    build_account_path,
    normalize_account_number,
    resolve_root_entity_group,
    slugify,
)


class TestNormalizeAccountNumber:
    @pytest.mark.parametrize("raw,expected", [
        ("1", "100000"),
        ("11", "110000"),
        ("111", "111000"),
        ("111005", "111005"),
        ("413044", "413044"),
    ])
    def test_pad_right_to_six(self, raw, expected):
        assert normalize_account_number(raw) == expected


class TestSlugify:
    @pytest.mark.parametrize("name,expected", [
        ("Banco BCI - 10160175", "BancoBci10160175"),
        ("Combustible Vehículos", "CombustibleVehculos"),
        ("VISA Infinity (Eduardo)", "VisaInfinityEduardo"),
        ("Banco BCI", "BancoBci"),
        ("MERCADOPAGO MERCADOLIBRE", "MercadopagoMercadolibre"),
        ("a", "A"),
    ])
    def test_known_examples(self, name, expected):
        assert slugify(name) == expected

    def test_handles_only_punctuation(self):
        # Si todo se filtra, debe quedar prefijo X seguro
        result = slugify("---")
        assert result.startswith("X") or result[0].isupper()

    def test_starts_uppercase(self):
        for name in ["banco bci", "123", "@@@", " "]:
            assert slugify(name)[0].isupper()


class TestResolveRootEntityGroup:
    def test_eag_active_no_bank(self):
        root, entity, group = resolve_root_entity_group("ACTIVO EAG")
        assert (root, entity, group) == ("Assets", "EAG", None)

    def test_pasivo(self):
        assert resolve_root_entity_group("PASIVO") == ("Liabilities", "EAG", None)

    def test_jocelyn_disponible(self):
        assert resolve_root_entity_group(
            "DISPONIBLE JOCELYN AVAYU DEUTSCH"
        ) == ("Assets", "Jocelyn", None)

    def test_bank_cta_corriente_overrides_to_assets(self):
        # ACTIVO EAG + cta_corriente → Assets/EAG/Bancos
        assert resolve_root_entity_group(
            "ACTIVO EAG", bank_account_type="cta_corriente"
        ) == ("Assets", "EAG", "Bancos")

    def test_bank_tarjeta_credito_overrides_to_liabilities(self):
        # Q7: aún si Categoria1 dice ACTIVO EAG, una TC va a Liabilities
        assert resolve_root_entity_group(
            "ACTIVO EAG", bank_account_type="tarjeta_credito"
        ) == ("Liabilities", "EAG", "TC")

    def test_bank_inversiones_keeps_entity_from_cat1(self):
        assert resolve_root_entity_group(
            "DISPONIBLE JOCELYN AVAYU DEUTSCH", bank_account_type="cta_inversiones"
        ) == ("Assets", "Jocelyn", "Inversiones")

    def test_bank_linea_credito(self):
        assert resolve_root_entity_group(
            "PASIVO", bank_account_type="linea_credito"
        ) == ("Liabilities", "EAG", "LineaCredito")

    def test_unknown_categoria1_raises(self):
        with pytest.raises(UnmappableCategoria1):
            resolve_root_entity_group("CUENTAS DE ORDEN")

    def test_unknown_bank_type_raises(self):
        with pytest.raises(UnknownBankAccountType):
            resolve_root_entity_group("ACTIVO EAG", bank_account_type="cripto_wallet")


class TestBuildAccountPath:
    def test_no_group(self):
        path = build_account_path(
            "Expenses", "EAG", "Combustible Vehículos", "413044",
        )
        assert path == "Expenses:EAG:CombustibleVehculos-413044"

    def test_with_group(self):
        path = build_account_path(
            "Assets", "EAG", "Banco BCI - 10160175", "111005", group="Bancos",
        )
        assert path == "Assets:EAG:Bancos:BancoBci10160175-111005"

    def test_tarjeta_credito_pattern(self):
        path = build_account_path(
            "Liabilities", "EAG", "VISA Infinity Eduardo", "215001", group="TC",
        )
        assert path == "Liabilities:EAG:TC:VisaInfinityEduardo-215001"

    def test_jocelyn_inversiones(self):
        path = build_account_path(
            "Assets", "Jocelyn", "Julius Baer", "112099", group="Inversiones",
        )
        assert path == "Assets:Jocelyn:Inversiones:JuliusBaer-112099"
