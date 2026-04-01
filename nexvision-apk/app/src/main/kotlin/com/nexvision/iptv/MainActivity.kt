package com.nexvision.iptv

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.nexvision.iptv.databinding.ActivityMainBinding
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val executor = Executors.newSingleThreadExecutor()

    private val prefs get() = getSharedPreferences("nexvision", Context.MODE_PRIVATE)
    private var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(v) { prefs.edit().putString("server_url", v).apply() }
    private var roomToken: String
        get() = prefs.getString("room_token", "") ?: ""
        set(v) { prefs.edit().putString("room_token", v).apply() }
    private var roomNumber: String
        get() = prefs.getString("room_number", "") ?: ""
        set(v) { prefs.edit().putString("room_number", v).apply() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupSetupForm()

        if (serverUrl.isNotEmpty() && roomToken.isNotEmpty()) {
            loadTvClient()
        } else {
            showSetupForm()
        }
    }

    private fun setupSetupForm() {
        binding.etServerUrl.setText(serverUrl)
        binding.etRoomNumber.setText(roomNumber)

        binding.btnConnect.setOnClickListener {
            val url = binding.etServerUrl.text.toString().trim()
            val room = binding.etRoomNumber.text.toString().trim()
            if (url.isEmpty() || room.isEmpty()) {
                Toast.makeText(this, "Server URL and room number are required", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            serverUrl = url
            doRegister(url, room)
        }
    }

    private fun doRegister(url: String, room: String) {
        showLoading(true)
        executor.execute {
            try {
                val info = ApiClient.registerRoom(url, room)
                roomToken = info.token
                roomNumber = info.room_number
                runOnUiThread {
                    showLoading(false)
                    loadTvClient()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    showLoading(false)
                    Toast.makeText(this, e.message ?: "Registration failed", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun loadTvClient() {
        val webView = binding.webView

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }

        // Bridge so the TV client JS can trigger native VLC playback
        webView.addJavascriptInterface(
            NexVisionBridge(this),
            "AndroidBridge"
        )

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                val scheme = uri.scheme ?: ""
                // Hand off non-HTTP schemes to VLC
                if (scheme == "rtsp" || scheme == "rtp" || scheme == "udp") {
                    launchVlc(uri.toString(), "")
                    return true
                }
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                showLoading(false)
            }

            @Suppress("OVERRIDE_DEPRECATION")
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                showLoading(false)
                Toast.makeText(
                    this@MainActivity,
                    "Cannot reach server: $description",
                    Toast.LENGTH_LONG
                ).show()
            }
        }

        webView.webChromeClient = object : WebChromeClient() {}

        showLoading(true)
        val tvUrl = "${serverUrl.trimEnd('/')}/?preview_token=$roomToken"
        webView.loadUrl(tvUrl)

        binding.setupForm.visibility = View.GONE
        binding.webView.visibility = View.VISIBLE
    }

    fun launchVlc(url: String, name: String) {
        startActivity(
            Intent(this, VLCPlayerActivity::class.java).apply {
                putExtra(VLCPlayerActivity.EXTRA_STREAM_URL, url)
                putExtra(VLCPlayerActivity.EXTRA_CHANNEL_NAME, name)
            }
        )
    }

    private fun showSetupForm() {
        binding.setupForm.visibility = View.VISIBLE
        binding.webView.visibility = View.GONE
    }

    private fun showLoading(show: Boolean) {
        binding.progressBar.visibility = if (show) View.VISIBLE else View.GONE
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && binding.webView.canGoBack()) {
            binding.webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        super.onDestroy()
        binding.webView.destroy()
        executor.shutdownNow()
    }
}
