"""Package exports for the set-me-up installer CLI."""

from . import core
from . import profile_commands
from . import catalog_registry
from . import adapters
from . import catalog_packs
from . import nix_provisioning
from . import provisioning_adapters
from . import provisioning_tools
from . import provisioning_preflight
from . import blueprint_providers
from . import blueprint_tools
from . import vps_tools
from . import provisioning_cli
from .ops import adapter_dashboard
from .ops import machine_profiles
from . import setup_profiles
from .ops import trust_runtime
from .ops import secrets_runtime
from . import doctors_and_system
from . import module_discovery
from . import module_lifecycle
from . import state
from .ops import rollback_runtime
from . import client_update
from . import repository_update
from . import update_runtime
from . import product_runtime
from .ops import conformance_runtime
from .ops import support_runtime
from .ops import plan_runtime
from .ops import release_notes_runtime
from .ops import migration_pr_runtime
from .ops import nix_doctor_runtime
from .ops import productization_runtime
from . import operability_runtime
from . import cli


PARTS = (
    core,
    profile_commands,
    catalog_registry,
    adapters,
    catalog_packs,
    nix_provisioning,
    provisioning_adapters,
    provisioning_tools,
    provisioning_preflight,
    blueprint_providers,
    blueprint_tools,
    vps_tools,
    adapter_dashboard,
    provisioning_cli,
    machine_profiles,
    setup_profiles,
    trust_runtime,
    secrets_runtime,
    doctors_and_system,
    module_discovery,
    module_lifecycle,
    state,
    rollback_runtime,
    client_update,
    repository_update,
    update_runtime,
    product_runtime,
    conformance_runtime,
    support_runtime,
    plan_runtime,
    release_notes_runtime,
    migration_pr_runtime,
    nix_doctor_runtime,
    productization_runtime,
    operability_runtime,
    cli,
)


def _exports_from_parts():
    exports = {}
    for module in PARTS:
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            exports[name] = value
    return exports


def _sync_part_globals():
    exports = _exports_from_parts()
    for module in PARTS:
        vars(module).update(exports)


_sync_part_globals()


def public_exports():
    exports = _exports_from_parts()
    exports["__smu_parts__"] = tuple(module.__name__ for module in PARTS)
    return exports


def set_part_attribute(name, value):
    if name == "__file__":
        installer_root = __import__("os").path.dirname(value)
        for module in PARTS:
            setattr(module, "installer_root", installer_root)
    for module in PARTS:
        if hasattr(module, name):
            setattr(module, name, value)
