package com.nexvision.tv

import android.app.Activity
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SetupActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        hideSystemUI()

        val etOct1  = findViewById<EditText>(R.id.etOct1)
        val etOct2  = findViewById<EditText>(R.id.etOct2)
        val etOct3  = findViewById<EditText>(R.id.etOct3)
        val etOct4  = findViewById<EditText>(R.id.etOct4)
        val etPort  = findViewById<EditText>(R.id.etPort)
        val etRoom  = findViewById<EditText>(R.id.etRoom)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val tvError = findViewById<TextView>(R.id.tvError)
        val tvHint  = findViewById<TextView>(R.id.tvAdbHint)

        val configPath = ConfigManager.configFile(this).absolutePath
        tvHint.text = "Or pre-configure via ADB:\nadb push config.json \"$configPath\"\n" +
                      "Format: { \"server_ip\": \"192.168.1.50\", \"server_port\": 80, \"room_number\": \"101\" }"

        // Auto-advance to next octet when 3 digits are entered
        listOf(etOct1 to etOct2, etOct2 to etOct3, etOct3 to etOct4).forEach { (from, to) ->
            from.addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) { if (s?.length == 3) to.requestFocus() }
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            })
        }

        // Pre-fill from existing config
        ConfigManager.read(this)?.let { cfg ->
            val parts = cfg.ip.split(".")
            if (parts.size == 4) {
                etOct1.setText(parts[0]); etOct2.setText(parts[1])
                etOct3.setText(parts[2]); etOct4.setText(parts[3])
            }
            etPort.setText(cfg.port.toString())
            if (cfg.roomNumber.isNotEmpty()) etRoom.setText(cfg.roomNumber)
        }
        if (etPort.text.isNullOrEmpty()) etPort.setText("80")

        btnSave.setOnClickListener { onSave(etOct1, etOct2, etOct3, etOct4, etPort, etRoom, tvError) }
    }

    private fun onSave(
        etOct1: EditText, etOct2: EditText, etOct3: EditText, etOct4: EditText,
        etPort: EditText, etRoom: EditText, tvError: TextView
    ) {
        val octets = listOf(etOct1, etOct2, etOct3, etOct4).map { it.text.toString().trim() }
        val port   = etPort.text.toString().toIntOrNull() ?: -1
        val room   = etRoom.text.toString().trim()

        val validOctets = octets.all { it.isNotEmpty() && it.toIntOrNull()?.let { n -> n in 0..255 } == true }

        when {
            !validOctets      -> showError(tvError, "Enter all four IP address parts (0–255 each).")
            port !in 1..65535 -> showError(tvError, "Port must be between 1 and 65535.")
            room.isEmpty()    -> showError(tvError, "Room number is required.")
            !ConfigManager.write(this, octets.joinToString("."), port, room) ->
                showError(tvError, "Could not write config file. Check storage availability.")
            else -> { setResult(Activity.RESULT_OK); finish() }
        }
    }

    private fun showError(view: TextView, msg: String) {
        view.text = msg
        view.visibility = View.VISIBLE
    }

    private fun hideSystemUI() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { ctrl ->
                ctrl.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                ctrl.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
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

    @Suppress("OVERRIDE_DEPRECATION")
    override fun onBackPressed() { /* no exit without a config */ }
}
