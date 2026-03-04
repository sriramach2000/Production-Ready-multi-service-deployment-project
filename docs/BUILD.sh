#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Build script for docs/spec.adoc → PDF (and optionally HTML)
#
# Prerequisites:
#   brew install asciidoctor
#   gem install asciidoctor-pdf
#   Draw.io desktop app installed (or `brew install --cask drawio`)
#
# Usage:
#   cd docs/
#   ./BUILD.sh          # Export diagrams + render PDF
#   ./BUILD.sh html     # Export diagrams + render HTML
#   ./BUILD.sh all      # Export diagrams + render both
#   ./BUILD.sh clean    # Remove generated SVGs and output files
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIAGRAMS_DIR="$SCRIPT_DIR/diagrams"
SPEC="$SCRIPT_DIR/spec.adoc"

# ── Locate draw.io CLI ──────────────────────────────────────
DRAWIO=""
if command -v drawio &>/dev/null; then
    DRAWIO="drawio"
elif [ -x "/Applications/draw.io.app/Contents/MacOS/draw.io" ]; then
    DRAWIO="/Applications/draw.io.app/Contents/MacOS/draw.io"
else
    echo "ERROR: draw.io not found."
    echo "  Install via: brew install --cask drawio"
    echo "  Or download from: https://github.com/jgraph/drawio-desktop/releases"
    exit 1
fi

# ── Step 1: Export .drawio → .svg ────────────────────────────
export_diagrams() {
    echo "==> Exporting DrawIO diagrams to SVG..."
    local count=0
    for f in "$DIAGRAMS_DIR"/*.drawio; do
        [ -f "$f" ] || continue
        local basename="$(basename "$f" .drawio)"
        echo "    $basename.drawio → $basename.svg"
        "$DRAWIO" --export --format svg "$f" 2>/dev/null
        count=$((count + 1))
    done
    echo "    Exported $count diagrams."
}

# ── Step 2: Render PDF ───────────────────────────────────────
render_pdf() {
    if ! command -v asciidoctor-pdf &>/dev/null; then
        echo "ERROR: asciidoctor-pdf not found."
        echo "  Install via: gem install asciidoctor-pdf"
        exit 1
    fi
    echo "==> Rendering PDF..."
    asciidoctor-pdf -a imagesdir=diagrams "$SPEC" -o "$SCRIPT_DIR/spec.pdf"
    echo "    Output: docs/spec.pdf ($(du -h "$SCRIPT_DIR/spec.pdf" | cut -f1 | xargs))"
}

# ── Step 2 (alt): Render HTML ────────────────────────────────
render_html() {
    if ! command -v asciidoctor &>/dev/null; then
        echo "ERROR: asciidoctor not found."
        echo "  Install via: brew install asciidoctor"
        exit 1
    fi
    echo "==> Rendering HTML..."
    asciidoctor -a imagesdir=diagrams "$SPEC" -o "$SCRIPT_DIR/spec.html"
    echo "    Output: docs/spec.html ($(du -h "$SCRIPT_DIR/spec.html" | cut -f1 | xargs))"
}

# ── Clean ────────────────────────────────────────────────────
clean() {
    echo "==> Cleaning generated files..."
    rm -f "$DIAGRAMS_DIR"/*.svg
    rm -f "$SCRIPT_DIR/spec.pdf" "$SCRIPT_DIR/spec.html"
    echo "    Done."
}

# ── Main ─────────────────────────────────────────────────────
MODE="${1:-pdf}"

case "$MODE" in
    pdf)
        export_diagrams
        render_pdf
        ;;
    html)
        export_diagrams
        render_html
        ;;
    all)
        export_diagrams
        render_pdf
        render_html
        ;;
    clean)
        clean
        ;;
    *)
        echo "Usage: $0 [pdf|html|all|clean]"
        exit 1
        ;;
esac

echo "==> Done."
