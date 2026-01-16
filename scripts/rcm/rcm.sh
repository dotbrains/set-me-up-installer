#!/bin/bash

# shellcheck source=/dev/null

declare current_dir &&
    current_dir="$(dirname "${BASH_SOURCE[0]}")" &&
    cd "${current_dir}" &&
    source "$HOME/set-me-up/dotfiles/utilities/utilities.sh"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

main() {

    # Check if debian

    if [[ "$(get_os)" == "debian" ]]; then
        # Install thoughtbot/RCM for dotfile management.
        # see: https://github.com/thoughtbot/rcm#installation

        ! package_is_installed "rcm" && {
            wget -qO - https://apt.thoughtbot.com/thoughtbot.gpg.key | sudo apt-key add -
            echo "deb https://apt.thoughtbot.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/thoughtbot.list
            sudo apt update
            sudo apt install -y "rcm"
        }

        return 0
    fi

    # Check if arch

    if [[ "$(get_os)" == "arch" ]]; then
        # Install 'rcm' from AUR
        # see: https://aur.archlinux.org/packages/rcm
        # see: https://github.com/thoughtbot/rcm#installation

        ! package_is_installed "rcm" && {
            # Check if an AUR helper is available
            if aur_helper_is_installed "yay"; then
                install_aur_package "rcm" "yay"
            elif aur_helper_is_installed "paru"; then
                install_aur_package "rcm" "paru"
            else
                # Fallback: manually build from AUR
                action "Installing rcm from AUR (no AUR helper found)"
                
                # Ensure base-devel is installed for makepkg
                install_package "base-devel"
                install_package "git"
                
                # Build and install rcm from AUR
                local build_dir="$(mktemp -d)"
                cd "$build_dir" || return 1
                git clone https://aur.archlinux.org/rcm.git
                cd rcm || return 1
                makepkg -si --noconfirm
                
                # Cleanup
                cd ~ || return 1
                rm -rf "$build_dir"
                
                success "rcm installed from AUR"
            fi
        }

        return 0
    fi

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    brew_bundle_install -f "brewfile"

}

main
