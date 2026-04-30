package com.nexvision.tv

import android.app.Activity
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Full-screen first-boot configuration screen.
 *
 * Shown by MainActivity when no config.json is present.
 * On successful save, finishes with RESULT_OK so MainActivity
 * picks up the new config and initialises the WebView.
 *
 * IT staff can bypass this screen entirely by deploying a config
 * file via ADB before the app launches (path shown on-screen).
 *
 * Back is swallowed — there is nowhere to go without a config.
 *
 * Reconfigure (after initial setup): delete the config file via ADB
 *   adb shell rm "<path shown on-screen>"
 *   adb shell am force-stop com.nexvision.tv
 */
class SetupActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        hideSystemUI()
        setContentView(R.layout.activity_setup)

        val etIp    = findViewById<EditText>(R.id.etIp)
        val etPort  = findViewById<EditText>(R.id.etPort)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val tvError = findViewById<TextView>(R.id.tvError)
        val tvHint  = findViewById<TextView>(R.id.tvAdbHint)

        // Show IT staff the ADB path so they can pre-deploy without the UI
        val configPath = ConfigManager.configFile(this).absolutePath
        tvHint.text = "Skip this screen by deploying a config file via ADB:\n" +
                      "adb push config.json \"$configPath\"\n\n" +
                      "Format: { \"server_ip\": \"192.168.1.x\", \"server_port\": 5000 }"

        // Pre-fill fields if the user is re-opening setup to change the server
        ConfigManager.read(this)?.let { cfg ->
            etIp.setText(cfg.ip)
            etPort.setText(cfg.port.toString())
        }
        // Always ensure a default port is shown
        if (etPort.text.isNullOrEmpty()) etPort.setText("5000")

        btnSave.setOnClickListener { onSave(etIp, etPort, tvError) }
    }

    private fun onSave(etIp: EditText, etPort: EditText, tvError: TextView) {
        val ip   = etIp.text.toString().trim()
        val port = etPort.text.toString().toIntOrNull() ?: -1

        when {
            ip.isEmpty()      -> showError(tvError, "IP address is required.")
            !isValidHost(ip)  -> showError(tvError, "Enter a valid IP address or hostname (e.g. 192.168.1.100).")
            port !in 1..65535 -> showError(tvError, "Port must be between 1 and 65535.")
            !ConfigManager.write(this, ip, port) ->
                showError(tvError, "Could not write config file. Check storage availability.")
            else -> {
                setResult(Activity.RESULT_OK)
                finish()
            }
        }
    }

    private fun showError(view: TextView, msg: String) {
        view.text = msg
        view.visibility = View.VISIBLE
    }

    // Accepts IPv4 (192.168.1.x) and simple hostnames (server.local, myserver)
    private fun isValidHost(host: String): Boolean {
        if (host.contains(' ') || host.startsWith("http")) return false
        // IPv4 check
        val parts = host.split(".")
        if (parts.size == 4 && parts.all { it.toIntOrNull()?.let { n -> n in 0..255 } == true }) {
            return true
        }
        // Hostname: at least one char, only valid hostname characters
        return host.matches(Regex("^[a-zA-Z0-9]([a-zA-Z0-9\\-\\.]*[a-zA-Z0-9])?\$"))
    }

    // ── System UI ──────────────────────────────────────────────────────────────

    private fun hideSystemUI() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { ctrl ->
                ctrl.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                ctrl.systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUI()
    }

    // No exit path — there is no system launcher to fall back to
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onBackPressed() { /* swallow */ }
}
