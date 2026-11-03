#!/bin/sh
# Echo-Wall's Home built for the web, for the Echo Local panel's preview (docs/home-screens.md): its lib/preview.dart
# compiled with Flutter, then what a browser loads copied into custom_components/echo_local/frontend/echowall/, served
# by the integration at /echo_local/echowall/.  CanvasKit goes along (Home Assistant may have no internet), its build
# for every browser only (web/flutter_bootstrap.js picks it), without debug symbols.  Rerun after a change to
# Echo-Wall's WallView and commit the result.
#
#   tools/echowall-preview.sh [path to Echo-Wall]     default: ../hassmic-homeview
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
app=$(cd "${1:-$here/../hassmic-homeview}" && pwd)
flutter=${FLUTTER:-$(command -v flutter || echo "$HOME/flutter/bin/flutter")}
out="$here/custom_components/echo_local/frontend/echowall"
(cd "$app" && "$flutter" build web -t lib/preview.dart --release --base-href /echo_local/echowall/ --no-web-resources-cdn \
    --no-source-maps --pwa-strategy=none)
src="$app/build/web"
rm -rf "$out"; mkdir -p "$out/canvaskit"
cp "$src/index.html" "$src/flutter_bootstrap.js" "$src/main.dart.js" "$out/"
cp -r "$src/assets" "$out/"
cp "$src/canvaskit/canvaskit.js" "$src/canvaskit/canvaskit.wasm" "$out/canvaskit/"
# what it was built from, for whoever wonders
(cd "$app" && printf 'Echo-Wall %s%s, built %s\n' "$(git rev-parse --short HEAD)" "$(git diff --quiet || echo ' + changes')" \
    "$(date -u +%Y-%m-%dT%H:%MZ)") > "$out/BUILT_FROM"
du -sh "$out"
