#!/bin/bash
# Collie diagnostics in Omarchy's floating terminal: the doctor's report, then a choice to close.
# Run by omarchy-launch-floating-terminal-with-presentation, which skips its own "Done!" prompt
# when this exits 130; "Keep open" falls through to that prompt so the report stays readable.

"${1:-collie}" doctor
status=$?
echo
gum confirm "Close diagnostics?" --affirmative "Close" --negative "Keep open" && exit 130
exit "$status"
