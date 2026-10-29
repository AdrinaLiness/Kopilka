#!/bin/bash
# Сборка KOPILKA APK (без Gradle — aapt2 + d8 + apksigner). v1.1
set -e
SDK=/home/z/my-project/android-sdk
PROJ=/home/z/my-project/kopilka_android
BT=$SDK/android-14
PLAT=$SDK/android-34/android.jar
JDK_DIR=$(ls -d "$SDK"/jdk-* 2>/dev/null | head -1)
JAVA="$JDK_DIR/bin"
OUT=$PROJ/out
export PATH="$JAVA:$PATH"

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/dex" "$PROJ/build"

echo "[1/6] javac..."
"$JAVA/javac" --release 8 -nowarn -classpath "$PLAT" \
  -d "$OUT/classes" \
  "$PROJ"/src/com/adrina/kopilka/*.java
ls "$OUT/classes/com/adrina/kopilka/" | head -3

echo "[2/6] d8 (dex)..."
"$BT/d8" --release --lib "$PLAT" --min-api 24 \
  --output "$OUT/dex" $(find "$OUT/classes" -name "*.class")
ls -la "$OUT/dex/"

echo "[3/6] aapt2 compile + link..."
"$BT/aapt2" compile --dir "$PROJ/res" -o "$OUT/res.zip"
"$BT/aapt2" link \
  -o "$OUT/kopilka-unsigned.apk" \
  -I "$PLAT" \
  --manifest "$PROJ/AndroidManifest.xml" \
  -A "$PROJ/assets" \
  --min-sdk-version 24 --target-sdk-version 34 \
  --version-code 2 --version-name 1.1 \
  --auto-add-overlay \
  "$OUT/res.zip"

echo "[4/6] classes.dex → apk..."
cd "$OUT/dex" && zip -q -u "$OUT/kopilka-unsigned.apk" classes.dex && cd "$SDK"

echo "[5/6] zipalign..."
"$BT/zipalign" -f 4 "$OUT/kopilka-unsigned.apk" "$OUT/kopilka-aligned.apk"

echo "[6/6] подпись..."
KS=$PROJ/build/kopilka.keystore
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -alias kopilka -keyalg RSA -keysize 2048 \
    -validity 10950 -storepass kopilka2026 -keypass kopilka2026 \
    -dname "CN=Kopilka, OU=AdrinaLiness, O=AdrinaLiness, C=RU" >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:kopilka2026 \
  --out "$PROJ/KOPILKA-v1.1.apk" "$OUT/kopilka-aligned.apk"
"$BT/apksigner" verify "$PROJ/KOPILKA-v1.1.apk" && echo "APK OK"

ls -la "$PROJ/KOPILKA-v1.1.apk"
"$BT/aapt2" dump badging "$PROJ/KOPILKA-v1.1.apk" | head -8
