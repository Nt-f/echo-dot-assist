#!/bin/sh
# Builds scripts/device/hassmic-kiosk.apk (checked into the repository, as hassmic-home.apk is) from tools/kiosk (the
# kiosk, the shell, the keyboard) with the Android SDK: aapt2 (resources, R.java), javac against android.jar, d8,
# zipalign, apksigner.  CI does not build it (no SDK there).
#   ANDROID_HOME (default ~/Android/Sdk), KIOSK_KEYSTORE (default secrets/kiosk.keystore, made on the first build:
#   the Echo takes a system app's new certificate and keeps its data, but one key keeps the login across rebuilds)
set -eu
cd "$(dirname "$0")/../.."
SDK=${ANDROID_HOME:-$HOME/Android/Sdk}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
JAR=$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar
KS=${KIOSK_KEYSTORE:-secrets/kiosk.keystore}
OUT=scripts/device/hassmic-kiosk.apk
W=build/kiosk; rm -rf $W; mkdir -p $W/classes $W/dex $W/gen
# the keyboard's resources (res/: its keys, its view, the input method's declaration), and R.java for them
"$BT"/aapt2 compile --dir tools/kiosk/res -o $W/res.zip
"$BT"/aapt2 link -I "$JAR" --manifest tools/kiosk/AndroidManifest.xml --min-sdk-version 24 --target-sdk-version 25 \
    --java $W/gen -o $W/base.apk $W/res.zip
javac -source 8 -target 8 -bootclasspath "$JAR:$BT/core-lambda-stubs.jar" -classpath "$JAR" -Xlint:-options -d $W/classes \
    $(find tools/kiosk/src $W/gen -name '*.java')
"$BT"/d8 --release --min-api 24 --lib "$JAR" --output $W/dex $(find $W/classes -name '*.class')
(cd $W/dex && zip -q -X ../base.apk classes.dex)
"$BT"/zipalign -f -p 4 $W/base.apk $W/aligned.apk
if [ ! -f "$KS" ]; then
    mkdir -p "$(dirname "$KS")"
    keytool -genkeypair -keystore "$KS" -storepass hassmic -keypass hassmic -alias kiosk -keyalg EC -groupname secp256r1 \
        -validity 36500 -dname "CN=hassmic kiosk" > /dev/null
fi
"$BT"/apksigner sign --ks "$KS" --ks-pass pass:hassmic --key-pass pass:hassmic --ks-key-alias kiosk --v1-signing-enabled true \
    --v2-signing-enabled true --v4-signing-enabled false --min-sdk-version 24 --out $OUT $W/aligned.apk
"$BT"/apksigner verify $OUT && ls -l $OUT
