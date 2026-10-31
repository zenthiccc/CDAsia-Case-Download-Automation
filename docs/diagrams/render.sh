#!/bin/sh
# Re-render the diagrams after editing a .dot file (needs Graphviz: brew install graphviz).
cd "$(dirname "$0")" && for f in *.dot; do dot -Tsvg "$f" -o "${f%.dot}.svg"; done
