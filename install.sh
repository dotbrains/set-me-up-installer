#!/bin/bash

# shellcheck disable=SC2001
# shellcheck disable=SC2154
# shellcheck disable=SC1091

source /dev/stdin <<<"$(curl -s "https://raw.githubusercontent.com/dotbrains/utilities/master/utilities.sh")"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# GitHub user/repo & branch value of your set-me-up blueprint (e.g.: dotbrains/set-me-up-blueprint/master).
# Set this value when the installer should additionally obtain your blueprint.
readonly SMU_BLUEPRINT=${SMU_BLUEPRINT:-""}
readonly SMU_BLUEPRINT_BRANCH=${SMU_BLUEPRINT_BRANCH:-""}

[[ -z "$SMU_BLUEPRINT" ]] && error "SMU_BLUEPRINT must be set."
[[ -z "$SMU_BLUEPRINT_BRANCH" ]] && error "SMU_BLUEPRINT_BRANCH must be set."

# Verify that SMU_BLUEPRINT is a valid GitHub repository
# It must follow the format: 'username/repo'
if ! [[ "$SMU_BLUEPRINT" =~ ^[a-z0-9]+/[a-z0-9-]+$ ]]; then
	error "SMU_BLUEPRINT must be in the format 'username/repo'."
fi

# A set of ignored paths that 'git' will ignore
# syntax: '<path>|<path>'
# Note: <path> is relative to '$HOME/set-me-up'
readonly SMU_IGNORED_PATHS="${SMU_IGNORED_PATHS:-""}"

# Where to install set-me-up
readonly SMU_HOME_DIR=${SMU_HOME_DIR:-"${HOME}/set-me-up"}
readonly SMU_INSTALLER_REF=${SMU_INSTALLER_REF:-"main"}
readonly SMU_INSTALLER_URL=${SMU_INSTALLER_URL:-"https://raw.githubusercontent.com/dotbrains/set-me-up-installer/${SMU_INSTALLER_REF}/install.sh"}
readonly SMU_SUBMODULE_SCOPE=${SMU_SUBMODULE_SCOPE:-"all"}

readonly smu_download="https://github.com/${SMU_BLUEPRINT}"

# Get the absolute path of the installer 'scripts' directory.
readonly installer_scripts_path="${SMU_HOME_DIR}/set-me-up-installer/scripts"

SMU_THEME="${SMU_THEME:-gruvbox}"
SMU_PROMPT="${SMU_PROMPT:-starship}"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Initialize the flag to "true" for showing the header (if '--no-header' is not passed)
# By default, the header will be shown.
show_header=true

# Initialize the flag to "false" for skipping the confirmation prompt (if '--skip-confirm' is passed)
# By default, the confirmation prompt will be shown.
skip_confirmation=false
force_reset=false
plan_only=false
json_output=false
doctor_only=false

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Determine if we're on MacOS, Debian, or Arch Linux

function detect_os() {
	# Use get_os() from utilities/system.sh
	case "$(get_os)" in
	macos)
		readonly SMU_OS="MacOS"
		;;
	arch)
		readonly SMU_OS="arch"
		;;
	ubuntu|debian)
		readonly SMU_OS="debian"
		;;
	*)
		readonly SMU_OS="unsupported"
		;;
	esac
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function parse_arguments() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
		# If '--skip-confirm' is found, set the flag to "true"
		--skip-confirm) skip_confirmation=true ;;
			# If '--no-header' is found, set the flag to "false"
		--no-header) show_header=false ;;
		--force-reset) force_reset=true ;;
		--plan) plan_only=true ;;
		--doctor) doctor_only=true ;;
		--json) json_output=true ;;
		--theme)
			shift
			SMU_THEME="${1:-$SMU_THEME}"
			;;
		--theme=*) SMU_THEME="${1#*=}" ;;
		--prompt)
			shift
			SMU_PROMPT="${1:-$SMU_PROMPT}"
			;;
		--prompt=*) SMU_PROMPT="${1#*=}" ;;
		esac
		shift
	done
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function mkcd() {
	local dir="${1}"
	[[ ! -d "${dir}" ]] && mkdir "${dir}"
	cd "${dir}" || return
}

function is_git_repo() {
	[[ -d "${SMU_HOME_DIR}/.git" ]] || git -C "${SMU_HOME_DIR}" rev-parse --is-inside-work-tree &>/dev/null
}

function has_remote_origin() {
	git -C "${SMU_HOME_DIR}" config --list | grep -qE 'remote.origin.url' 2>/dev/null
}

function has_submodules() {
	[[ -f "${SMU_HOME_DIR}"/.gitmodules ]]
}

function has_active_submodules() {
	git -C "${SMU_HOME_DIR}" config --list | grep -qE '^submodule' 2>/dev/null
}

function selected_submodule_paths() {
	local path
	if [[ "${SMU_SUBMODULE_SCOPE}" = "all" ]]; then
		git -C "${SMU_HOME_DIR}" config --file .gitmodules --get-regexp 'submodule\..*\.path' | awk '{print $2}'
		return 0
	fi

	git -C "${SMU_HOME_DIR}" config --file .gitmodules --get-regexp 'submodule\..*\.path' | awk '{print $2}' |
		while IFS= read -r path; do
			case "$path" in
			docs | set-me-up-installer | dotfiles/utilities | dotfiles/modules/universal)
				printf "%s\n" "$path"
				;;
			dotfiles/modules/debian)
				[[ "$SMU_OS" = "debian" ]] && printf "%s\n" "$path"
				;;
			dotfiles/modules/macos/*)
				[[ "$SMU_OS" = "MacOS" ]] && printf "%s\n" "$path"
				;;
			dotfiles/modules/arch/*)
				[[ "$SMU_OS" = "arch" ]] && printf "%s\n" "$path"
				;;
			esac
		done
}

function update_selected_submodules() {
	local -a paths=()
	while IFS= read -r path; do
		[[ -n "$path" ]] && paths+=("$path")
	done < <(selected_submodule_paths)

	if ((${#paths[@]} == 0)); then
		return 0
	fi

	git -C "${SMU_HOME_DIR}" submodule update --init --recursive --depth 1 -- "${paths[@]}"
}

function has_untracked_changes() {
	[[ $(git -C "${SMU_HOME_DIR}" diff-index HEAD -- 2>/dev/null) ]]
}

function does_repo_contain() {
	git -C "${SMU_HOME_DIR}" ls-files | grep -qE "$1" &>/dev/null
}

function is_git_repo_out_of_date() {
	UPSTREAM=${1:-'@{u}'}
	LOCAL=$(git -C "${SMU_HOME_DIR}" rev-parse @)
	REMOTE=$(git -C "${SMU_HOME_DIR}" rev-parse "$UPSTREAM")
	BASE=$(git -C "${SMU_HOME_DIR}" merge-base @ "$UPSTREAM")

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	[[ "$LOCAL" = "$BASE" ]] && [[ "$LOCAL" != "$REMOTE" ]]
}

function is_dir_empty() {
	[ -z "$(ls -A "$1")" ]
}

function has_worktree_changes() {
	[[ -n "$(git -C "${SMU_HOME_DIR}" status --porcelain 2>/dev/null)" ]]
}

function json_escape() {
	local value="$1"

	value="${value//\\/\\\\}"
	value="${value//\"/\\\"}"
	value="${value//$'\n'/\\n}"
	printf "%s" "$value"
}

function update_mode() {
	[[ "$force_reset" = true ]] && printf "force-reset" || printf "ff-only"
}

function install_target_state() {
	if [[ ! -e "${SMU_HOME_DIR}" ]]; then
		printf "missing"
	elif is_git_repo; then
		if has_worktree_changes; then
			printf "dirty"
		else
			printf "clean"
		fi
	else
		printf "not-git"
	fi
}

function install_readiness() {
	case "$(install_target_state)" in
	missing | clean)
		printf "ready"
		;;
	dirty)
		if [[ "$force_reset" = true ]]; then
			printf "ready-force-reset"
		else
			printf "blocked-dirty"
		fi
		;;
	not-git)
		printf "blocked-not-git"
		;;
	esac
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function are_xcode_command_line_tools_installed() {
	xcode-select --print-path &>/dev/null
}

function install_xcode_command_line_tools() {
	# If necessary, prompt user to install
	# the `Xcode Command Line Tools`.

	action "Installing '${bold}Xcode Command Line Tools${normal}'"

	xcode-select --install &>/dev/null

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	# Wait until the `Xcode Command Line Tools` are installed.

	until are_xcode_command_line_tools_installed; do
		sleep 5
	done

	are_xcode_command_line_tools_installed &&
		success "'${bold}Xcode Command Line Tools${normal}' has been successfully installed\n"
}

function can_install_rosetta() {
	# Determine OS version
	os_version=$(/usr/bin/sw_vers -productVersion)
	osvers_major=${os_version%%.*}

	# Check the major OS version and determine if Rosetta needs to be installed
	if [[ "$osvers_major" -ge 11 ]]; then
		# Check to see if the Mac needs Rosetta installed by testing the processor
		processor=$(/usr/sbin/sysctl -n machdep.cpu.brand_string | grep -o "Apple")
		if [[ -n $processor ]]; then
			return 0
		else
			return 1
		fi
	else
		return 1
	fi
}

function is_rosetta_installed() {
	/usr/bin/pgrep oahd >/dev/null 2>&1
}

function install_rosetta() {
	action "Installing '${bold}Rosetta${normal}'"

	/usr/sbin/softwareupdate --install-rosetta --agree-to-license

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	# Wait until the `Rosetta` is installed.

	until is_rosetta_installed; do
		sleep 5
	done

	is_rosetta_installed &&
		success "'${bold}Rosetta${normal}' was successfully installed\n"
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function confirm() {
	# Check if skip_confirmation is true, if so, return without prompting
	if [[ "$skip_confirmation" = true ]]; then
		return
	fi

	printf "\n"
	read -r -p "Would you like '${bold}set-me-up${normal}' to continue? (y/n) " -n 1
	echo ""

	[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function obtain() {
	local -r DOWNLOAD_URL="${1}"

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	if [[ -d "${SMU_HOME_DIR}/.git" ]]; then
		if [[ "$force_reset" != true ]] && has_worktree_changes; then
			error "Existing blueprint checkout has local changes. Commit, stash, or rerun with --force-reset to discard them."
		fi

		git -C "${SMU_HOME_DIR}" fetch --quiet
		if [[ "$force_reset" = true ]]; then
			git -C "${SMU_HOME_DIR}" reset --hard "origin/${SMU_BLUEPRINT_BRANCH}"
		else
			git -C "${SMU_HOME_DIR}" merge --ff-only "origin/${SMU_BLUEPRINT_BRANCH}"
		fi
		update_selected_submodules

		return 0
	fi

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	# Otherwise, clone the repository and update selected submodules.
	git clone --depth 1 --branch "${SMU_BLUEPRINT_BRANCH}" "${DOWNLOAD_URL}" "${SMU_HOME_DIR}"
	update_selected_submodules
}

function setup() {
	warn "This script will download '${bold}${SMU_BLUEPRINT:-set-me-up}${normal}' on branch '${bold}${SMU_BLUEPRINT_BRANCH}${normal}' to ${bold}${SMU_HOME_DIR}${normal}"
	if [[ "$plan_only" = true || "$doctor_only" = true ]]; then
		if [[ "$json_output" = true ]]; then
			printf '{"blueprint":{"repo":"%s","branch":"%s","path":"%s","state":"%s","readiness":"%s"},"installer":{"ref":"%s","url":"%s"},"mode":"%s","submodule_scope":"%s","doctor":%s}\n' \
				"$(json_escape "$SMU_BLUEPRINT")" "$(json_escape "$SMU_BLUEPRINT_BRANCH")" \
				"$(json_escape "$SMU_HOME_DIR")" "$(install_target_state)" "$(install_readiness)" \
				"$(json_escape "$SMU_INSTALLER_REF")" "$(json_escape "$SMU_INSTALLER_URL")" \
				"$(update_mode)" "$(json_escape "$SMU_SUBMODULE_SCOPE")" "$doctor_only"
		else
			printf "plan\tblueprint\t%s\t%s\t%s\n" "${SMU_BLUEPRINT}" "${SMU_BLUEPRINT_BRANCH}" "${SMU_HOME_DIR}"
			printf "plan\tinstaller\t%s\t%s\n" "${SMU_INSTALLER_REF}" "${SMU_INSTALLER_URL}"
			printf "plan\tmode\t%s\n" "$(update_mode)"
			printf "plan\tsubmodules\t%s\n" "${SMU_SUBMODULE_SCOPE}"
			if [[ "$doctor_only" = true ]]; then
				printf "doctor\tstate\t%s\n" "$(install_target_state)"
				printf "doctor\treadiness\t%s\n" "$(install_readiness)"
			fi
		fi
		return 0
	fi
	confirm

	mkcd "${SMU_HOME_DIR}"
	printf "\n"
	action "Obtaining '${bold}${SMU_BLUEPRINT:-set-me-up}${normal}' on branch '${bold}${SMU_BLUEPRINT_BRANCH}${normal}'."
	obtain "${smu_download}"
	printf "\n"

	success "'${bold}set-me-up${normal}' has been successfully installed on your system."
	write_profile
	printf "\nNext checks:\n"
	printf "  smu update doctor --json\n"
	printf "  smu update --plan\n"
	echo -e "\nFor more information, visit: [https://github.com/$SMU_BLUEPRINT/tree/$SMU_BLUEPRINT_BRANCH]\n"
}

function write_profile() {
	local -r profile_dir="${XDG_CONFIG_HOME:-$HOME/.config}/set-me-up"
	local -r profile="${profile_dir}/profile.env"

	mkdir -p "$profile_dir"
	cat >"$profile" <<EOF
# set-me-up profile
export SMU_THEME="${SMU_THEME}"
export SMU_PROMPT="${SMU_PROMPT}"
EOF

	success "Saved set-me-up profile to ${bold}${profile}${normal}"
}

function install_rosetta_if_needed() {
	# Installing Rosetta 2 on Apple Silicon Macs
	# See https://derflounder.wordpress.com/2020/11/17/installing-rosetta-2-on-apple-silicon-macs/

	if can_install_rosetta && ! is_rosetta_installed; then
		install_rosetta

		return 0
	fi

	if is_rosetta_installed; then
		success "'${bold}Rosetta${normal}' is already installed\n"
	fi
}

function install_xcode_command_line_tools_if_needed() {
	if ! are_xcode_command_line_tools_installed; then
		install_xcode_command_line_tools

		return 0
	fi

	success "'${bold}Xcode Command Line Tools${normal}' are already installed\n"
}

function invoked_via_smu_blueprint() {
	# Check if both SMU_BLUEPRINT and SMU_BLUEPRINT_BRANCH are set
	if [[ -n "$SMU_BLUEPRINT" ]] && [[ -n "$SMU_BLUEPRINT_BRANCH" ]]; then
		# Both variables are set, so we can assume that the installer was invoked via SMU Blueprint.
		return 0
	fi

	return 1
}

function check_os_support() {
	# Check if both SMU_BLUEPRINT and SMU_BLUEPRINT_BRANCH are set
	if invoked_via_smu_blueprint; then
		# If invoked via SMU Blueprint, then we can assume that the OS is supported.
		# This is because the SMU Blueprint is responsible for determining if the OS is supported.
		# By default, 'dotbrains/set-me-up' (non-blueprint) supports MacOS, Debian, and Arch Linux.
		return 0
	fi

	# Check if OS is supported (MacOS, Debian, or Arch Linux)
	if [[ "$SMU_OS" != "MacOS" ]] && [[ "$SMU_OS" != "debian" ]] && [[ "$SMU_OS" != "arch" ]]; then
		error -e "Sorry, '${bold}set-me-up${normal}' is not supported on your OS.\n"
		exit 1
	fi
}

function source_header() {
	if [[ -f "${installer_scripts_path}/header.sh" ]]; then
		source "${installer_scripts_path}/header.sh"

		return 0
	fi

	source /dev/stdin <<<"$(curl -s "https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/scripts/header.sh")"
}

main() {

	detect_os
	parse_arguments "$@"

	[[ "$show_header" = true ]] && source_header

	# Determine if the operating system is supported
	# by the base 'set-me-up' configuration.
	check_os_support

	# Check if we are running on MacOS, if so, install
	# 'Xcode Command Line Tools' and 'Rosetta' if needed.
	if [[ "$SMU_OS" = "MacOS" ]]; then
		install_xcode_command_line_tools_if_needed
		install_rosetta_if_needed
	fi

	# Check if 'git' is installed
	# 'git' is required to install 'set-me-up'
	# given that 'set-me-up' is a git repository and requires submodules.
	if ! cmd_exists git; then
		error "'${bold}git${normal}' is not installed.\n"
		exit 1
	fi

	# If SMU_BLUEPRINT and SMU_BLUEPRINT_BRANCH are set,
	# Then the installer was invoked via SMU Blueprint.

	setup

}

main "$@"
