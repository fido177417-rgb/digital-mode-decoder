#!/data/data/com.termux/files/usr/bin/bash
set -e

SDK="/data/data/com.termux/files/home/android-sdk"
BUILD_TOOLS="$SDK/build-tools/34.0.0"
PLATFORM="$SDK/platforms/android-34/android.jar"
PROJECT="/data/data/com.termux/files/home/digital-mode-decoder/android_build"
BIN="$PROJECT/bin"

AAPT="$BUILD_TOOLS/aapt"
D8="$BUILD_TOOLS/d8"
APKSIGNER="$BUILD_TOOLS/apksigner"
ZIPALIGN="$BUILD_TOOLS/zipalign"

echo "=== Cleaning ==="
rm -rf "$BIN"
mkdir -p "$BIN/classes"

echo "=== Compiling Java ==="
javac -source 1.8 -target 1.8 \
    -classpath "$PLATFORM" \
    -d "$BIN/classes" \
    "$PROJECT/src/com/digitalmodedecoder/MainActivity.java"

echo "=== Converting to DEX ==="
java -cp "$BUILD_TOOLS/lib/d8.jar" com.android.tools.r8.D8 \
    --output "$BIN" \
    --lib "$PLATFORM" \
    "$BIN/classes/com/digitalmodedecoder/MainActivity.class"

echo "=== Packaging with AAPT ==="
$AAPT package -f -m \
    -S "$PROJECT/res" \
    -J "$BIN/gen" \
    -M "$PROJECT/AndroidManifest.xml" \
    -I "$PLATFORM" \
    --auto-add-overlay

echo "=== Linking APK ==="
$AAPT link -f \
    -o "$BIN/dmd-unsigned.apk" \
    -I "$PLATFORM" \
    -S "$PROJECT/res" \
    -M "$PROJECT/AndroidManifest.xml" \
    --auto-add-overlay

echo "=== Adding DEX to APK ==="
cd "$BIN"
zip -j dmd-unsigned.apk classes.dex
cd -

echo "=== Aligning APK ==="
$ZIPALIGN -f 4 "$BIN/dmd-unsigned.apk" "$BIN/dmd-aligned.apk"

echo "=== Signing APK ==="
keytool -genkeypair -v \
    -keystore "$BIN/debug.keystore" \
    -alias debug \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass android -keypass android \
    -dname "CN=Debug,O=Debug,C=US" 2>/dev/null || true

$APKSIGNER sign \
    --ks "$BIN/debug.keystore" \
    --ks-key-alias debug \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$BIN/dmd-debug.apk" \
    "$BIN/dmd-aligned.apk"

echo "=== Done ==="
echo "APK: $BIN/dmd-debug.apk"
ls -lh "$BIN/dmd-debug.apk"
