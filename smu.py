#!/usr/bin/env python3

import os

_SMU_PARTS = (
    "core.py",
    "profile_commands.py",
    "catalog_registry.py",
    "adapters.py",
    "catalog_packs.py",
    "doctors_and_system.py",
    "module_discovery.py",
    "module_lifecycle.py",
    "cli.py",
)


def _load_parts():
    parts_dir = os.path.join(os.path.dirname(__file__), "smu_parts")
    for part in _SMU_PARTS:
        path = os.path.join(parts_dir, part)
        with open(path) as f:
            code = compile(f.read(), path, "exec")
        exec(code, globals())


_load_parts()


if __name__ == "__main__":
    main()
