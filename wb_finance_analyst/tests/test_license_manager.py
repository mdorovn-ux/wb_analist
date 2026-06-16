from wb_finance_analyst.services.license_manager import (
    LicenseManager,
    UNIVERSAL_LICENSE_KEY,
    generate_activation_key,
)


def test_license_manager_generates_and_accepts_activation_key(tmp_path):
    path = tmp_path / "license.json"
    manager = LicenseManager(path=path)
    state = manager.state()
    key = generate_activation_key(state.installation_id)

    assert not state.activated
    assert manager.activate(key)

    activated = LicenseManager(path=path).state()
    assert activated.activated
    assert activated.activation_key == key


def test_license_manager_accepts_universal_key(tmp_path):
    manager = LicenseManager(path=tmp_path / "license.json")

    assert manager.activate(UNIVERSAL_LICENSE_KEY)
    assert manager.state().activated


def test_license_manager_rejects_wrong_key(tmp_path):
    manager = LicenseManager(path=tmp_path / "license.json")

    assert not manager.activate("WRONG-KEY")
    assert not manager.state().activated
