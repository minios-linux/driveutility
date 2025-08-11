#!/bin/bash

# Universal translation management script
# Automatically detects project info and manages translations

# Function to display help
usage() {
    echo "Usage: $(basename "$0") [options]"
    echo
    echo "This script manages gettext translation files (.po, .pot)."
    echo
    echo "Options:"
    echo "  --debug      Show detailed lists of untranslated and fuzzy strings for each language."
    echo "  -h, --help   Display this help message and exit."
}

# Parse command line arguments
DEBUG_MODE=false
for arg in "$@"; do
    case $arg in
    -h | --help)
        usage
        exit 0
        ;;
    --debug)
        DEBUG_MODE=true
        shift # Shift arguments
        ;;
    esac
done

SCRIPT_DIR="$(dirname "$(readlink -f "${0}")")"
cd "$SCRIPT_DIR"

# Auto-detect configuration
if [ -f "debian/changelog" ]; then
    APPNAME=$(head -n1 debian/changelog | cut -d' ' -f1)
    VERSION=$(head -n1 debian/changelog | sed 's/.*(\([^)]*\)).*/\1/' | sed 's/-.*//')
else
    APPNAME=$(basename "$PWD")
    VERSION="unknown"
fi

POTFILE="po/messages.pot"

# Configuration
BUGS_EMAIL="support@minios.dev"
COPYRIGHT_HOLDER="MiniOS Linux"

# Auto-detect languages from existing .po files
if [ -d "po" ]; then
    LANGUAGES=($(find po -maxdepth 1 -name "*.po" -exec basename {} .po \; | sort))
fi

# Default languages if none found
if [ ${#LANGUAGES[@]} -eq 0 ]; then
    LANGUAGES=("ru" "pt" "pt_BR" "it" "id" "fr" "es" "de")
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_stats() {
    if [ ! -f "$POTFILE" ]; then
        log_warning "Translation template not found, skipping statistics"
        return 1
    fi

    log_info "Translation statistics for $APPNAME:"

    # Get total number of messages
    local total=$(msgcat "$POTFILE" | grep -c '^msgid ' 2>/dev/null || echo "0")

    if [ "$total" -eq 0 ]; then
        log_warning "No translatable messages found"
        return 1
    fi

    printf "%-8s %-12s %-12s %-8s\n" "Lang" "Translated" "Fuzzy" "Percent"
    echo "----------------------------------------"

    for lang in "${LANGUAGES[@]}"; do
        local pofile="po/${lang}.po"

        if [ -f "$pofile" ]; then
            local stats=$(msgfmt --statistics -o /dev/null "$pofile" 2>&1)
            local translated=$(echo "$stats" | grep -o '[0-9]\+ translated' | grep -o '[0-9]\+' || echo "0")
            local fuzzy=$(echo "$stats" | grep -o '[0-9]\+ fuzzy' | grep -o '[0-9]\+' || echo "0")
            local percent=0

            if [ "$total" -gt 0 ]; then
                percent=$((translated * 100 / total))
            fi

            printf "%-8s %-12s %-12s %-8s%%\n" "$lang" "$translated" "$fuzzy" "$percent"
        else
            printf "%-8s %-12s %-12s %-8s\n" "$lang" "missing" "-" "-"
        fi
    done

    echo "----------------------------------------"
    log_info "Total messages: $total"

    # Show summary of issues
    local has_issues=false
    for lang in "${LANGUAGES[@]}"; do
        local pofile="po/${lang}.po"
        if [ -f "$pofile" ]; then
            # We use msgfmt for general statistics, not msgattrib, as it is faster
            local stats=$(msgfmt --statistics -o /dev/null "$pofile" 2>&1)
            local untranslated=$(echo "$stats" | grep -o '[0-9]\+ untranslated' | grep -o '[0-9]\+' || echo "0")
            local fuzzy=$(echo "$stats" | grep -o '[0-9]\+ fuzzy' | grep -o '[0-9]\+' || echo "0")

            if [ "$untranslated" -gt 0 ] || [ "$fuzzy" -gt 0 ]; then
                if [ "$has_issues" = false ]; then
                    echo
                    log_info "Translation issues found:"
                    has_issues=true
                fi

                local issues=""
                [ "$untranslated" -gt 0 ] && issues="$untranslated untranslated"
                [ "$fuzzy" -gt 0 ] && issues="$issues${issues:+, }$fuzzy fuzzy"

                echo "  $lang: $issues"
            fi
        fi
    done

    if [ "$has_issues" = true ]; then
        echo
        log_info "Use 'msgattrib --untranslated po/LANG.po' to see untranslated strings"
        log_info "Use 'msgattrib --only-fuzzy po/LANG.po' to see fuzzy translations"
        log_info "Or run this script with the --debug option for a full report."
    fi
}

generate_pot() {
    log_info "Generating translation template for $APPNAME..."

    # Auto-detect source files by type
    local python_sources=$(find . -maxdepth 3 -type f -name "*.py" -not -path "./generate_additional_files.py" 2>/dev/null)
    local glade_sources=$(find . -maxdepth 3 -type f \( -name "*.glade" -o -name "*.ui" \) 2>/dev/null)
    local desktop_sources=$(find . -maxdepth 3 -type f -name "*.desktop" 2>/dev/null)
    local polkit_sources=$(find . -maxdepth 4 -type f -name "*.policy" 2>/dev/null)

    if [ -z "$python_sources" ] && [ -z "$glade_sources" ] && [ -z "$desktop_sources" ] && [ -z "$polkit_sources" ]; then
        log_error "No source files found for translation (.py, .glade, .desktop, .policy)"
        return 1
    fi

    # Create po directory and ensure we start with a clean POT file
    mkdir -p po
    rm -f "$POTFILE"

    local pot_created=false
    local success=true

    if [ -n "$python_sources" ]; then
        log_info "Scanning Python sources..."
        xgettext --language=Python \
            --keyword=_ \
            --keyword=N_ \
            --add-comments=TRANSLATORS \
            --from-code=UTF-8 \
            --package-name="$APPNAME" \
            --package-version="$VERSION" \
            --msgid-bugs-address="$BUGS_EMAIL" \
            --copyright-holder="$COPYRIGHT_HOLDER" \
            --output="$POTFILE" \
            $python_sources

        if [ $? -eq 0 ]; then
            log_success "Processed Python sources."
            pot_created=true
        else
            log_error "Failed to process Python sources."
            success=false
        fi
    fi

    if [ "$success" = true ] && [ -n "$glade_sources" ]; then
        log_info "Scanning Glade sources..."
        local join_opt=""
        if [ "$pot_created" = true ]; then
            join_opt="--join-existing"
        fi

        xgettext --language=Glade \
            $join_opt \
            --add-comments=TRANSLATORS \
            --from-code=UTF-8 \
            --package-name="$APPNAME" \
            --package-version="$VERSION" \
            --msgid-bugs-address="$BUGS_EMAIL" \
            --copyright-holder="$COPYRIGHT_HOLDER" \
            --output="$POTFILE" \
            $glade_sources

        if [ $? -eq 0 ]; then
            log_success "Processed Glade sources."
            pot_created=true
        else
            log_error "Failed to process Glade sources."
            success=false
        fi
    fi

    if [ "$success" = true ] && [ -n "$desktop_sources" ]; then
        log_info "Scanning .desktop sources..."
        local join_opt=""
        if [ "$pot_created" = true ]; then
            join_opt="--join-existing"
        fi

        xgettext --language=Desktop \
            $join_opt \
            --add-comments=TRANSLATORS \
            --from-code=UTF-8 \
            --package-name="$APPNAME" \
            --package-version="$VERSION" \
            --msgid-bugs-address="$BUGS_EMAIL" \
            --copyright-holder="$COPYRIGHT_HOLDER" \
            --output="$POTFILE" \
            $desktop_sources

        if [ $? -eq 0 ]; then
            log_success "Processed .desktop sources."
            pot_created=true
        else
            log_error "Failed to process .desktop sources."
            success=false
        fi
    fi

    if [ "$success" = true ] && [ -n "$polkit_sources" ]; then
        log_info "Scanning Polkit policy sources..."
        local join_opt=""
        if [ "$pot_created" = true ]; then
            join_opt="--join-existing"
        fi

        # Check for .policy.template files first (untranslated versions)
        local template_sources=""
        local temp_dir=""
        local cleanup_needed=false
        
        for policy_file in $polkit_sources; do
            local template_file="${policy_file%.policy}.policy.template"
            if [ -f "$template_file" ]; then
                if [ -z "$temp_dir" ]; then
                    temp_dir=$(mktemp -d)
                    cleanup_needed=true
                fi
                # Create temporary .policy file from template (xgettext doesn't recognize .template extension)
                local temp_policy="$temp_dir/$(basename "${template_file%.template}")"
                cp "$template_file" "$temp_policy"
                template_sources="$template_sources $temp_policy"
            fi
        done

        # Use template files if available, otherwise use original policy files
        local sources_to_use=""
        if [ -n "$template_sources" ]; then
            sources_to_use="$template_sources"
            log_info "Using .policy.template files for string extraction."
        else
            sources_to_use="$polkit_sources"
        fi

        xgettext \
            $join_opt \
            --add-comments=TRANSLATORS \
            --from-code=UTF-8 \
            --package-name="$APPNAME" \
            --package-version="$VERSION" \
            --msgid-bugs-address="$BUGS_EMAIL" \
            --copyright-holder="$COPYRIGHT_HOLDER" \
            --output="$POTFILE" \
            $sources_to_use

        if [ $? -eq 0 ]; then
            log_success "Processed Polkit policy sources."
            pot_created=true
        else
            log_error "Failed to process Polkit policy sources."
            success=false
        fi
        
        # Clean up temporary files
        if [ "$cleanup_needed" = true ]; then
            rm -rf "$temp_dir"
        fi
    fi

    if [ "$success" = true ] && [ -f "$POTFILE" ]; then
        log_success "Translation template generated: $POTFILE"
        msguniq --sort-output "$POTFILE" -o "$POTFILE"
        log_info "Setting POT file charset to UTF-8..."
        sed -i 's/charset=CHARSET/charset=UTF-8/' "$POTFILE"
        return 0
    else
        log_error "Failed to generate translation template."
        rm -f "$POTFILE" 2>/dev/null
        return 1
    fi
}

update_po_files() {
    log_info "Updating .po files for languages: ${LANGUAGES[*]}"

    if [ ! -f "$POTFILE" ]; then
        log_error "Translation template not found: $POTFILE"
        return 1
    fi

    local updated=0
    local created=0

    for lang in "${LANGUAGES[@]}"; do
        local pofile="po/${lang}.po"

        if [ ! -f "$pofile" ]; then
            log_warning "Creating new translation file for $lang..."
            if msginit --input="$POTFILE" --locale="$lang" --output-file="$pofile" --no-translator; then
                log_success "Created: $pofile"
                ((created++))
            else
                log_error "Failed to create: $pofile"
            fi
        else
            if msgmerge --update --backup=off "$pofile" "$POTFILE"; then
                log_success "Updated: $pofile"
                ((updated++))
            else
                log_error "Failed to update: $pofile"
            fi
        fi
    done

    if [ $created -gt 0 ] || [ $updated -gt 0 ]; then
        log_info "Summary: $created created, $updated updated"
    else
        log_warning "No files were created or updated"
    fi
}

# New function for detailed .po file checks
run_debug_checks() {
    if [ "$DEBUG_MODE" = false ]; then
        return 0
    fi

    echo
    log_info "--- Running Detailed Debug Checks ---"

    for lang in "${LANGUAGES[@]}"; do
        local pofile="po/${lang}.po"
        if [ ! -f "$pofile" ]; then
            continue
        fi

        local has_output=false

        # Check for untranslated strings
        local untranslated_output
        untranslated_output=$(msgattrib --untranslated "$pofile" 2>/dev/null)
        if [ -n "$untranslated_output" ]; then
            echo
            log_warning "--- Untranslated strings for '$lang' ---"
            echo "$untranslated_output"
            has_output=true
        fi

        # Check for fuzzy translations
        local fuzzy_output
        fuzzy_output=$(msgattrib --only-fuzzy "$pofile" 2>/dev/null)
        if [ -n "$fuzzy_output" ]; then
            echo
            log_warning "--- Fuzzy strings for '$lang' ---"
            echo "$fuzzy_output"
            has_output=true
        fi

        if [ "$has_output" = false ]; then
            log_success "No issues found for '$lang'."
        fi
    done
    log_info "--- End of Detailed Debug Checks ---"
}

# Main execution
log_info "Starting translation workflow for $APPNAME (version $VERSION)..."
if [ "$DEBUG_MODE" = true ]; then # Message about debug mode
    log_info "Debug mode is ON. Detailed report will be shown at the end."
fi
log_info "Languages: ${LANGUAGES[*]}"

if generate_pot; then
    update_po_files
    show_stats
    run_debug_checks # Call new function
    log_success "Translation workflow completed!"
else
    log_error "Workflow failed during template generation"
    exit 1
fi
