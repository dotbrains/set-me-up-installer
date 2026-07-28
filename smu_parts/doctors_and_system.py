def catalog_doctor():
    errors = []
    errors.extend(_catalog_registry_errors())
    errors.extend(_catalog_registry_lock_errors())
    errors.extend(_catalog_layer_errors(
        "themes",
        theme_manifests_dir(),
        theme_catalog_path,
        _load_theme_registry(),
    ))
    errors.extend(_catalog_layer_errors(
        "prompts",
        prompt_profiles_path,
        prompt_catalog_path,
        _load_prompt_registry(),
    ))
    errors.extend(_catalog_layer_errors(
        "presets",
        preset_profiles_path,
        preset_catalog_path,
        _load_preset_registry(),
    ))

    prompt_registry = _load_prompt_registry()
    if prompt_registry:
        for profile in prompt_profiles():
            errors.extend(
                f"prompts: {error}"
                for error in prompt_registry.validate_profile(profile)
            )

    theme_registry = _load_theme_registry()
    if theme_registry and hasattr(theme_registry, "validate_theme"):
        for theme in theme_manifests():
            errors.extend(
                f"themes: {error}"
                for error in theme_registry.validate_theme(theme)
            )

    preset_registry = _load_preset_registry()
    if preset_registry:
        for preset in preset_profiles():
            errors.extend(
                f"presets: {error}"
                for error in preset_registry.validate_preset(
                    preset,
                    supported_themes(),
                    supported_prompts(),
                )
            )

    errors.extend(_manifest_authoring_errors("themes", theme_manifests()))
    errors.extend(_manifest_authoring_errors("prompts", prompt_profiles()))
    errors.extend(_manifest_authoring_errors("presets", preset_profiles()))

    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1

    print(f"{COL_GREEN}OK{COL_RESET}   catalogs {catalogs_path}")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_themes())} theme(s)")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_prompts())} prompt profile(s)")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_presets())} preset(s)")
    return 0

def preset_doctor(preset):
    entry = preset_by_id(preset)
    if not entry:
        warn(f"Unknown preset '{preset}'.")
        return 1

    registry = _load_preset_registry()
    errors = []
    if registry:
        errors.extend(registry.validate_preset(entry, supported_themes(), supported_prompts()))

    failed = False
    for error in errors:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} {error}")

    theme = entry.get("theme")
    prompt = entry.get("prompt")
    if theme in supported_themes():
        print(f"{COL_GREEN}OK{COL_RESET}   theme {theme}")
    else:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} preset {preset} references unknown theme {theme}")

    if prompt in supported_prompts():
        print(f"{COL_GREEN}OK{COL_RESET}   prompt {prompt}")
    else:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} preset {preset} references unknown prompt {prompt}")

    return 1 if failed else 0

def doctor():
    failed = False
    preset = current_preset()
    theme = current_theme()
    prompt = current_prompt()

    print(f"{BOLD}Preset:{NORMAL} {preset}")
    failed = preset_doctor(preset) != 0 or failed
    print(f"\n{BOLD}Catalogs:{NORMAL} {catalogs_path}")
    failed = catalog_doctor() != 0 or failed
    print(f"\n{BOLD}Resolved Profile:{NORMAL} {resolved_profile_path}")
    failed = resolved_profile_doctor() != 0 or failed
    print(f"\n{BOLD}Adapters:{NORMAL} {theme} + {prompt}")
    failed = adapter_doctor(theme, prompt) != 0 or failed
    print(f"\n{BOLD}Theme:{NORMAL} {theme}")
    failed = theme_doctor(theme) != 0 or failed
    print(f"\n{BOLD}Prompt:{NORMAL} {prompt}")
    failed = prompt_doctor(prompt) != 0 or failed

    return 1 if failed else 0

def prompt_doctor(prompt):
    profiles = {entry["id"]: entry for entry in prompt_profiles() if entry.get("id")}
    if prompt not in profiles:
        warn(f"Unknown prompt profile '{prompt}'.")
        return 1

    registry = _load_prompt_registry()
    if not registry:
        warn("Prompt registry is not available.")
        return 1

    profile = profiles[prompt]
    failed = False
    for error in registry.validate_profile(profile):
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} {error}")

    set_me_up_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for label, path in registry.adapter_paths(set_me_up_root, profile):
        if os.path.exists(path):
            print(f"{COL_GREEN}OK{COL_RESET}   {label}")
        else:
            failed = True
            print(f"{COL_RED}MISS{COL_RESET} {label}: {path}")

    return 1 if failed else 0

def theme_doctor(theme):
    themes = {entry["id"]: entry for entry in theme_manifests()}
    if theme not in supported_themes():
        warn(f"Unknown theme '{theme}'.")
        return 1

    colorschemes = colorscheme_module_dir()
    set_me_up_root = os.path.abspath(os.path.join(colorschemes, "..", ".."))
    theme_entry = themes.get(theme, {"id": theme})
    registry = _load_theme_registry()

    if registry:
        checks = registry.adapter_paths(
            colorschemes,
            theme_entry,
            aggregate_root=set_me_up_root,
        )
    else:
        checks = [
            ("colorscheme manifest", os.path.join(colorschemes, "themes", f"{theme}.toml")),
            ("universal script", os.path.join(colorschemes, "universal", f"{theme}.sh")),
            ("macos script", os.path.join(colorschemes, "macos", f"{theme}.sh")),
            ("arch script", os.path.join(colorschemes, "arch", f"{theme}.sh")),
        ]

    failed = False
    for label, path in checks:
        if os.path.exists(path):
            print(f"{COL_GREEN}OK{COL_RESET}   {label}")
        else:
            failed = True
            print(f"{COL_RED}MISS{COL_RESET} {label}: {path}")

    return 1 if failed else 0

def list_symlinks():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"lsrc -v -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def symlink():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"rcup -v -f -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def remove_symlinks():
    os.environ["RCRC"] = rcrc

    dotfiles_dir = os.path.join(smu_home_dir, "dotfiles")
    quoted_dotfiles_dir = shlex.quote(dotfiles_dir)
    managed_targets = []

    if os.path.exists(dotfiles_dir):
        # Capture the exact destinations before rcdn removes anything. This keeps
        # cleanup proportional to managed links instead of scanning home.
        result = subprocess.run(
            f"lsrc -v {quoted_dotfiles_dir}",
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                if '->' not in line:
                    continue

                target = line.split('->', 1)[0].strip()
                if target:
                    managed_targets.append(target)

    subprocess.run(f"rcdn -v -d {quoted_dotfiles_dir}", shell=True)

    for target in managed_targets:
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.isdir(target):
            try:
                os.rmdir(target)
            except OSError:
                pass

def create_boot_disk():
    # Execute create boot disk script
    script_path = os.path.join(installer_scripts_path, "create_boot_disk/create_boot_disk.sh")
    subprocess.run(f"bash {script_path}", shell=True)

def update():
    """
    Update the given OS.
    """

    if debian:
        script_path = os.path.join(installer_scripts_path, "update/debian.sh")
    elif macOS:
        script_path = os.path.join(installer_scripts_path, "update/macos.sh")
    elif arch:
        script_path = os.path.join(installer_scripts_path, "update/arch.sh")

    subprocess.run(f"bash {script_path}", shell=True)

def get_module_path(module_name):
    """
    Get the path to the given module.
    If the module is not supported on the current OS or does not exist then return None.
    """

    def extract_dir_and_module_name(module):
        """
        Extract the directory name and module name from the given string.
        """

        # Get the directory name and module name
        # e.g., python/pip (module_name)
        # dir_name = python/pip
        # module_name = pip

        # Split the string by '/'
        parts = module.split('/')

        # The directory name is the input string itself
        dir_name = module

        # The module name is the last part of the split string
        module_name = parts[-1]

        return dir_name, module_name

    def obtain_universal_module_path(module_name):
        """
        Get the path to the given universal module.
        If the module does not exist then return None.
        """

        # If the module name contains a '/', then the module is in a subdirectory of the 'universal' directory
        # e.g., modules/universal/python/pip/pip.sh
        if '/' in module_name:
            dir_name, extracted_module_name = extract_dir_and_module_name(module_name)
            module_dir = os.path.join(module_path, "universal", dir_name)
            script_path = os.path.join(module_dir, f"{extracted_module_name}.sh")
            brewfile_path = os.path.join(module_dir, "brewfile")
            packages_path = os.path.join(module_dir, "packages")

            if os.path.exists(script_path):
                return script_path
            if os.path.exists(brewfile_path):
                return brewfile_path
            if os.path.exists(packages_path):
                return packages_path
            return None

        # Universal module path
        # e.g., modules/universal/fonts/fonts.sh
        module_dir = os.path.join(module_path, "universal", module_name)
        script_path = os.path.join(module_dir, f"{module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")

        if os.path.exists(script_path):
            return script_path
        if os.path.exists(brewfile_path):
            return brewfile_path
        if os.path.exists(packages_path):
            return packages_path
        return None

    # If we are trying to get the 'base' module, then return the path to the 'base' directory
    if module_name == "base":
        return os.path.join(smu_home_dir, "dotfiles/base", f"{module_name}.sh")

    direct_module_dir = os.path.join(module_path, module_name)
    direct_script_path = os.path.join(direct_module_dir, f"{module_name}.sh")
    direct_brewfile_path = os.path.join(direct_module_dir, "brewfile")
    direct_packages_path = os.path.join(direct_module_dir, "packages")

    if os.path.exists(direct_script_path):
        return direct_script_path
    if os.path.exists(direct_brewfile_path):
        return direct_brewfile_path
    if os.path.exists(direct_packages_path):
        return direct_packages_path

    # Determine the OS of the module by checking if the module is part of an OS-specific directory
    # e.g., modules/macos/fonts/fonts.sh
    #       modules/debian/fonts/fonts.sh
    #       modules/arch/fonts/fonts.sh
    # If the module is not part of an OS-specific directory, then the module is universal, so
    # check the 'universal' directory for the module
    # e.g., modules/universal/python/pip/pip.sh

    if not macOS and not debian and not arch:
        return obtain_universal_module_path(module_name)

    smu_os = ""

    if macOS:
        smu_os = "macos"
    elif debian:
        smu_os = "debian"
    elif arch:
        smu_os = "arch"

    # Module path
    # e.g., modules/macos/fonts/fonts.sh
    #       modules/macos/productivity/rectangle-pro/rectangle-pro.sh
    #       modules/debian/fonts/fonts.sh
    if '/' in module_name:
        dir_name, extracted_module_name = extract_dir_and_module_name(module_name)
        module_dir = os.path.join(module_path, smu_os, dir_name)
        script_path = os.path.join(module_dir, f"{extracted_module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")
    else:
        module_dir = os.path.join(module_path, smu_os, module_name)
        script_path = os.path.join(module_dir, f"{module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")

    if os.path.exists(script_path):
        return script_path
    if os.path.exists(brewfile_path):
        return brewfile_path
    if os.path.exists(packages_path):
        return packages_path
    return obtain_universal_module_path(module_name)


def provision_module(module_name):
    # Get the path to the module
    script_path = get_module_path(module_name)

    # Check if the script exists
    if not script_path:
        warn(f"'{script_path}' does not seem to exist, skipping.")
        return False

    # Check that bash is installed
    if subprocess.call("command -v bash &> /dev/null", shell=True) != 0:
        warn("'bash' is not installed, skipping.")
        return False

    action(f"Running {script_path} module\n")

    script_dir = os.path.dirname(script_path)
    os.chdir(script_dir)

    if os.path.basename(script_path) == "brewfile":
        subprocess.run("brew bundle install --file brewfile", shell=True)
        return True

    if os.path.basename(script_path) == "packages":
        if not debian:
            warn(f"'{script_path}' is only supported on Debian-based systems, skipping.")
            return False
        utilities = os.path.join(smu_home_dir, "dotfiles/utilities/utilities.sh")
        subprocess.run(
            f"bash -c 'source {utilities} && apt_install_from_file packages'",
            shell=True,
        )
        return True

    # Execute before.sh if exists
    before_script = os.path.join(script_dir, "before.sh")
    if os.path.exists(before_script):
        subprocess.run(f"bash -c 'source {before_script}'", shell=True)

    # Execute main script
    subprocess.run(f"bash -c 'source {script_path}'", shell=True)

    # Execute after.sh if exists
    after_script = os.path.join(script_dir, "after.sh")
    if os.path.exists(after_script):
        subprocess.run(f"bash -c 'source {after_script}'", shell=True)

    return True

