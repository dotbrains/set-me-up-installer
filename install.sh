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
if ! [[ "$SMU_BLUEPRINT" =~ ^[a-z0-9]+/[a-z0-9]+$ ]]; then
	error "SMU_BLUEPRINT must be in the format 'username/repo'."
fi

# A set of ignored paths that 'git' will ignore
# syntax: '<path>|<path>'
# Note: <path> is relative to '$HOME/set-me-up'
readonly SMU_IGNORED_PATHS="${SMU_IGNORED_PATHS:-""}"

# Where to install set-me-up
readonly SMU_HOME_DIR=${SMU_HOME_DIR:-"${HOME}/set-me-up"}

readonly smu_download="https://github.com/${SMU_BLUEPRINT}/tarball/${SMU_BLUEPRINT_BRANCH}"

# Get the absolute path of the 'utilities' directory.
readonly installer_utilities_path="${SMU_HOME_DIR}/set-me-up-installer/utilities"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Determine if we're on MacOS or Debian

function detect_os() {
	case "$(uname | tr '[:upper:]' '[:lower:]')" in
	darwin*) readonly SMU_OS="MacOS" ;;
	linux-gnu*) readonly SMU_OS="debian" ;;
	*) readonly SMU_OS="unsupported" ;;
	esac
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function parse_arguments() {
	# Initialize the flag to "true" for showing the header (if '--no-header' is not passed)
	# By default, the header will be shown.
	show_header=true

	# Initialize the flag to "false" for skipping the confirmation prompt (if '--skip-confirm' is passed)
	# By default, the confirmation prompt will be shown.
	skip_confirmation=false

	for arg in "$@"; do
		case "$arg" in
		# If '--skip-confirm' is found, set the flag to "true"
		--skip-confirm) skip_confirmation=true ;;
			# If '--no-header' is found, set the flag to "false"
		--no-header) show_header=false ;;
		esac
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

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function install_submodules() {
	# Ensures SMU_HOME_DIR is set
	: "${SMU_HOME_DIR:?SMU_HOME_DIR is not set}"

	# Read the '.gitmodules' file and install the submodules
	git -C "${SMU_HOME_DIR}" config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r key path; do
		# Check if the directory exists and is empty, then remove it
		[[ -d "${SMU_HOME_DIR}/${path}" && $(is_dir_empty "${path}") ]] && rm -rf "${SMU_HOME_DIR}/${path}"

		# Extract submodule name and URL

		name="${key#submodule.}"
		name="${name%.path}"

		url_key="${key/.path/.url}"
		url="$(git -C "${SMU_HOME_DIR}" config -f .gitmodules --get "${url_key}")"

		# Find the default branch
		branch=$(git ls-remote --symref "${url}" HEAD | awk '/^ref:/ {sub(/refs\/heads\//, "", $2); print $2}')

		# Add the submodule
		git -C "${SMU_HOME_DIR}" submodule add --force -b "${branch}" --name "${name}" "${url}" "${path}" || continue
	done

	# Update all submodules
	git -C "${SMU_HOME_DIR}" submodule update --init --recursive
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
	# Save current IFS state
	OLDIFS=$IFS

	IFS='.' read -r osvers_major <<<"$(/usr/bin/sw_vers -productVersion)"

	# restore IFS to previous state
	IFS=$OLDIFS

	# Check to see if the Mac is reporting itself as running macOS 11
	if [[ ${osvers_major} -ge 11 ]]; then
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
	printf "\n"
	read -r -p "Would you like '${bold}set-me-up${normal}' to continue? (y/n) " -n 1
	echo ""

	[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function obtain() {
	local -r DOWNLOAD_URL="${1}"

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

	curl --progress-bar -L "${DOWNLOAD_URL}" |
		tar -xmz --strip-components 1 \
			--exclude={README.md,LICENSE,.gitignore}
}

function setup() {
	warn "This script will download '${bold}${SMU_BLUEPRINT:-set-me-up}${normal}' on branch '${bold}${SMU_BLUEPRINT_BRANCH}${normal}' to ${bold}${SMU_HOME_DIR}${normal}"
	[[ "$skip_confirmation" = false ]] && confirm

	mkcd "${SMU_HOME_DIR}"
	printf "\n"
	action "Obtaining '${bold}${SMU_BLUEPRINT:-set-me-up}${normal}' on branch '${bold}${SMU_BLUEPRINT_BRANCH}${normal}'."
	obtain "${smu_download}"
	printf "\n"

	if ! is_git_repo; then
		git -C "${SMU_HOME_DIR}" init &>/dev/null
		# TODO - install_submodules is not working as expected
		[[ $(has_submodules) ]] && action "Installing '${bold}set-me-up${normal}' submodules." && install_submodules && printf "\n"
	fi

	printf "\n"
	success "'${bold}set-me-up${normal}' has been successfully installed on your system."
	[[ -n "$SMU_BLUEPRINT" ]] && echo -e "\nFor more information, visit: [https://github.com/$SMU_BLUEPRINT/tree/$SMU_BLUEPRINT_BRANCH]\n"
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
		# By default, 'dotbrains/set-me-up' (non-blueprint) supports MacOS and Debian.
		return 0
	fi

	# Check if OS is supported (MacOS or Debian)
	if [[ "$SMU_OS" != "MacOS" ]] && [[ "$SMU_OS" != "debian" ]]; then
		error -e "Sorry, '${bold}set-me-up${normal}' is not supported on your OS.\n"
		exit 1
	fi
}

function source_header() {
	if [[ -f "${installer_utilities_path}/header.sh" ]]; then
		source "${installer_utilities_path}/header.sh"

		return 0
	fi

	source /dev/stdin <<<"$(curl -s "https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/utilities/header.sh")"
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
	if ! command -v git &>/dev/null; then
		error "'${bold}git${normal}' is not installed.\n"
		exit 1
	fi

	# If SMU_BLUEPRINT and SMU_BLUEPRINT_BRANCH are set,
	# Then the installer was invoked via SMU Blueprint.

	setup

}

main "$@"
