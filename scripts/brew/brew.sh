#!/bin/bash

# shellcheck source=/dev/null

declare current_dir &&
    current_dir="$(dirname "${BASH_SOURCE[0]}")" &&
    cd "${current_dir}" &&
    source "$HOME/set-me-up/dotfiles/utilities/utilities.sh"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

install_arch_dependencies() {
    # Install required dependencies for Homebrew on Arch Linux
    # See: https://github.com/orgs/Homebrew/discussions/4503

    action "Installing Arch Linux dependencies for Homebrew"

    # libxcrypt-compat is required for Homebrew to work properly on Arch
    if ! pacman -Q libxcrypt-compat &>/dev/null; then
        sudo pacman -S --noconfirm libxcrypt-compat
    fi

    success "Arch Linux dependencies installed"
}

install_homebrew() {

    # Install Arch-specific dependencies if on Arch-based system
    if is_arch_linux; then
        install_arch_dependencies
    fi

    printf "\n" |
        /bin/bash -c \
            "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

}

get_homebrew_git_config_file_path() {

    local path=""

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    if path="$(brew --repository 2>/dev/null)/.git/config"; then
        printf "%s" "$path"
        return 0
    else
        return 1
    fi

}

opt_out_of_analytics() {

    local path=""

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    # Try to get the path of the `Homebrew` git config file.

    path="$(get_homebrew_git_config_file_path)" ||
        return 1

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    # Opt-out of Homebrew's analytics.
    # https://github.com/Homebrew/brew/blob/0c95c60511cc4d85d28f66b58d51d85f8186d941/share/doc/homebrew/Analytics.md#opting-out

    if [[ "$(git config --file="$path" --get homebrew.analyticsdisabled)" != "true" ]]; then
        git config --file="$path" --replace-all homebrew.analyticsdisabled true &>/dev/null
    fi

}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

main() {

    ask_for_sudo

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    if is_arch_linux; then
        # Set environment variable to force Homebrew to use its vendored Ruby
        # This avoids conflicts with Arch's system Ruby
        # See: https://github.com/orgs/Homebrew/discussions/6333
        export HOMEBREW_FORCE_VENDOR_RUBY=1
    fi

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    # If `brew` is already installed, it may be necessary to
    # initialize the current shell context with brew's environment.
    # Otherwise, the brew commands will not be available.

    initialize_brew

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    if ! cmd_exists "brew"; then
        install_homebrew
        initialize_brew
        opt_out_of_analytics
    else
        brew_upgrade
        brew_update
    fi

    brew_cleanup

}

main
