# NexVision TV — Android App

A full-screen Android TV client for [NexVision IPTV](../../README.md). The app is a lightweight WebView wrapper around the NexVision web TV interface, optimised for D-pad navigation and hotel TV-box deployments.

---

## Requirements

| Item | Requirement |
|---|---|
| Android | 6.0+ (API 23 — covers all modern Android TV hardware) |
| Build tools | Android SDK, JDK 17, Gradle (wrapper included) |
| Deployment | `adb` from Android platform-tools |
| ADB method | Wi-Fi ADB (port 5555) — no USB needed |

---

## Project Structure

```
android/nexvision-tv/
├── app/
│   ├── build.gradle.kts
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/nexvision/tv/
│       │   ├── MainActivity.kt       # Full-screen WebView
│       │   ├── SetupActivity.kt      # First-boot IP/port config screen
│       │   ├── ConfigManager.kt      # Reads/writes config.json
│       │   └── BootReceiver.kt       # Auto-launch on device reboot
│       └── res/
│           ├── layout/activity_setup.xml
│           └── values/strings.xml & themes.xml
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
└── deploy.sh                         # Build + ADB deploy script
```

---

## Building & Deploying

### 1. Configure the device IP

Open `deploy.sh` and set `DEVICE_IP` to your Android TV box's local IP:

```bash
DEVICE_IP="192.168.1.XXX"   # ← your TV box IP
```

Make sure **Developer Options** and **Network Debugging (ADB over Wi-Fi)** are enabled on the device.

### 2. Run the deploy script

```bash
cd /opt/nexvision/android/nexvision-tv

./deploy.sh              # build debug APK + deploy
./deploy.sh release      # build release APK (minified + ProGuard) + deploy
BUILD=0 ./deploy.sh      # skip build, redeploy the existing APK
```

The script will:
1. Build the APK via Gradle
2. Connect to the device over Wi-Fi ADB (retries up to 5×)
3. Uninstall the old version if present
4. Install and launch the new APK

### Manual ADB (alternative)

```bash
# Connect
adb connect 192.168.1.XXX:5555

# Install
adb install -r app/build/outputs/apk/release/app-release.apk

# Launch
adb shell am start -n com.nexvision.tv/.MainActivity \
    -a android.intent.action.MAIN \
    -c android.intent.category.LEANBACK_LAUNCHER
```

---

## First-Boot Setup

On the first launch, a setup screen asks for:

| Field | Description |
|---|---|
| **Server IP** | Local IP of your NexVision server (e.g. `192.168.1.100`) |
| **Server Port** | Default: `5000` |

Once saved, the app permanently loads `http://<ip>:<port>/tv?platform=tv`.

### Pre-configure via ADB (skip the setup screen)

Useful for bulk deployments — push the config file before the first launch:

```bash
# Create config locally
echo '{"server_ip":"192.168.1.100","server_port":5000}' > config.json

# Push to device
adb push config.json "/sdcard/Android/data/com.nexvision.tv/files/config.json"
```

The app reads this file on startup and skips the setup screen automatically.

---

## Reconfiguring the Server

To change the server IP after initial setup:

```bash
# Delete the config file
adb shell rm "/sdcard/Android/data/com.nexvision.tv/files/config.json"

# Force stop the app
adb shell am force-stop com.nexvision.tv

# Next launch shows the setup screen again
```

---

## Auto-Launch on Boot

`BootReceiver` listens for `BOOT_COMPLETED` and `LOCKED_BOOT_COMPLETED` and relaunches `MainActivity` automatically after every device restart.

The app is also declared as a **Home/Leanback launcher** in the manifest, so it can be set as the device's default home screen — useful for locked-down hotel kiosk deployments.

---

## How It Works

| Component | Role |
|---|---|
| `MainActivity` | Loads the WebView in immersive full-screen mode; keeps the screen on; navigates WebView history on back-press |
| `SetupActivity` | D-pad-friendly form that captures server IP + port; disabled back button forces valid config before proceeding |
| `ConfigManager` | Reads/writes `config.json` from `getExternalFilesDir()` — requires no storage permissions |
| `BootReceiver` | Starts `MainActivity` on boot, before or after device unlock |

The WebView URL is always `http://<server_ip>:<server_port>/tv?platform=tv`. The `?platform=tv` parameter tells the NexVision frontend it is running inside the Android app.

---

## Monitoring & Debugging

After deployment, watch the WebView logs:

```bash
adb -s 192.168.1.XXX:5555 logcat -s 'chromium' 'WebView'
```

Disconnect when done:

```bash
adb disconnect 192.168.1.XXX:5555
```

---

## Security Notes

- `usesCleartextTraffic="true"` is enabled for hotel LAN (HTTP) deployments.  
  Switch to HTTPS and disable cleartext traffic once SSL is configured on the server.
- `allowBackup="false"` prevents app data from being extracted via ADB backup.
- Release builds run ProGuard code minification (`proguard-rules.pro`).
