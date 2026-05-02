package com.nexvision.tv

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private var webView: WebView? = null
    private var currentConfig: ServerConfig? = null
    private var backPressedAt = 0L

    // Fullscreen video state
    private var fullscreenView: View? = null
    private var fullscreenCallback: WebChromeClient.CustomViewCallback? = null

    private val setupLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val config = ConfigManager.read(this)
            if (config != null) {
                initWebView(config)
                hideSystemUI()
            } else {
                openSetup()
            }
        } else {
            openSetup()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val config = ConfigManager.read(this)
        if (config == null) {
            setContentView(View(this).apply { setBackgroundColor(0xFF06060A.toInt()) })
            hideSystemUI()
            openSetup()
        } else {
            initWebView(config)
            hideSystemUI()
        }
    }

    private fun openSetup() {
        setupLauncher.launch(Intent(this, SetupActivity::class.java))
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun initWebView(config: ServerConfig) {
        currentConfig = config
        webView?.let { it.stopLoading(); it.destroy() }

        webView = WebView(this).apply {
            isFocusable          = true
            isFocusableInTouchMode = true
            setBackgroundColor(0xFF06060A.toInt())

            settings.apply {
                javaScriptEnabled                = true
                domStorageEnabled                = true
                mediaPlaybackRequiresUserGesture = false
                useWideViewPort                  = true
                loadWithOverviewMode             = true
                mixedContentMode                 = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                cacheMode                        = WebSettings.LOAD_DEFAULT
                databaseEnabled                  = true
                allowFileAccess                  = false
                allowContentAccess               = false
            }

            // ── WebChromeClient: required for fullscreen video (Live TV) ──────
            webChromeClient = object : WebChromeClient() {
                override fun onShowCustomView(view: View, callback: CustomViewCallback) {
                    fullscreenView?.let { callback.onCustomViewHidden(); return }
                    fullscreenView    = view
                    fullscreenCallback = callback
                    setContentView(view)
                    hideSystemUI()
                }

                override fun onHideCustomView() {
                    fullscreenCallback?.onCustomViewHidden()
                    fullscreenView    = null
                    fullscreenCallback = null
                    setContentView(webView)
                    hideSystemUI()
                    webView?.requestFocus()
                }
            }

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, url: String) = false

                override fun onReceivedError(
                    view: WebView, request: WebResourceRequest, error: WebResourceError
                ) {
                    if (request.isForMainFrame) {
                        val msg = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
                            error.description.toString() else "Connection failed"
                        view.loadData(
                            """<html><body style="background:#06060A;color:#C9A84C;font-family:sans-serif;
                               display:flex;align-items:center;justify-content:center;height:100vh;margin:0;
                               flex-direction:column;text-align:center">
                               <h2>Cannot reach server</h2>
                               <p style="color:#5A5A6A">http://${config.ip}:${config.port}</p>
                               <p style="color:#5A5A6A;font-size:14px">$msg</p>
                               <p style="color:#383848;font-size:12px;margin-top:32px">
                               Press back to exit &nbsp;·&nbsp; Hold back to reconfigure</p>
                               </body></html>""",
                            "text/html", "utf-8"
                        )
                    }
                }

                override fun onPageFinished(view: WebView, url: String) {
                    super.onPageFinished(view, url)
                    view.requestFocus()
                    val cfg = currentConfig ?: return
                    if (cfg.roomNumber.isBlank()) return
                    view.evaluateJavascript("localStorage.getItem('nv_room_token')") { value ->
                        val hasToken = value != null && value != "null"
                                && value.isNotBlank() && value != "\"\""
                        if (!hasToken) registerAndInjectToken(view, cfg)
                    }
                }
            }

            loadUrl(config.url)
        }

        setContentView(webView)
        webView?.requestFocus()
    }

    // ── Key routing ────────────────────────────────────────────────────────────

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val wv = webView ?: return super.dispatchKeyEvent(event)
        return when (event.keyCode) {
            KeyEvent.KEYCODE_BACK -> super.dispatchKeyEvent(event)
            KeyEvent.KEYCODE_DPAD_CENTER,
            KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_NUMPAD_ENTER -> { wv.dispatchKeyEvent(event); true }
            KeyEvent.KEYCODE_DPAD_UP,
            KeyEvent.KEYCODE_DPAD_DOWN,
            KeyEvent.KEYCODE_DPAD_LEFT,
            KeyEvent.KEYCODE_DPAD_RIGHT  -> { wv.dispatchKeyEvent(event); true }
            else -> super.dispatchKeyEvent(event)
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if ((event?.repeatCount ?: 0) >= 3) { openSetup(); return true }
            handleWebBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun handleWebBack() {
        val wv = webView ?: run { finish(); return }

        // Ask the page what state it's in before deciding what to do
        wv.evaluateJavascript("""
            (function() {
                if (document.getElementById('vod-player-modal')?.classList.contains('open')) return 'vod-player';
                if (document.getElementById('movie-detail')?.classList.contains('open'))     return 'modal';
                if (document.getElementById('series-detail')?.classList.contains('open'))    return 'modal';
                if (document.fullscreenElement) return 'fullscreen';
                return typeof activeScreen !== 'undefined' ? String(activeScreen) : 'home';
            })()
        """) { raw ->
            val state = raw?.trim('"') ?: "home"
            when (state) {
                "vod-player", "modal" -> injectKey("Escape")
                "fullscreen"          -> injectKey("Backspace")
                "home"                -> {
                    val now = System.currentTimeMillis()
                    if (now - backPressedAt < 2000) {
                        finish()
                    } else {
                        backPressedAt = now
                        runOnUiThread {
                            Toast.makeText(this, "Press back again to exit", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                else -> injectKey("Backspace")
            }
        }
    }

    private fun injectKey(key: String) {
        webView?.evaluateJavascript(
            """document.dispatchEvent(new KeyboardEvent('keydown',
               {key:'$key',code:'$key',bubbles:true,cancelable:true}));""",
            null
        )
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun onBackPressed() { handleWebBack() }

    // ── Room registration ──────────────────────────────────────────────────────

    private fun registerAndInjectToken(view: WebView, config: ServerConfig) {
        Thread {
            try {
                val conn = (URL("http://${config.ip}:${config.port}/api/rooms/register")
                    .openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/json")
                    connectTimeout = 6000; readTimeout = 6000
                    doOutput = true
                    outputStream.write("""{"room_number":"${config.roomNumber}"}""".toByteArray())
                }
                if (conn.responseCode == 200) {
                    val json       = JSONObject(conn.inputStream.bufferedReader().readText())
                    val token      = json.optString("token", "")
                    val roomNumber = json.optString("room_number", config.roomNumber)
                    val tvName     = json.optString("tv_name", "TV-${config.roomNumber}")
                    if (token.isNotEmpty()) {
                        val roomInfo = JSONObject().apply {
                            put("room_number", roomNumber); put("tv_name", tvName)
                        }
                        val js = """
                            localStorage.setItem('nv_room_token', ${JSONObject.quote(token)});
                            localStorage.setItem('nv_room_info',  ${JSONObject.quote(roomInfo.toString())});
                            location.reload();
                        """.trimIndent()
                        view.post { view.evaluateJavascript(js, null) }
                    }
                }
                conn.disconnect()
            } catch (_: Exception) { /* web page shows its own registration screen as fallback */ }
        }.start()
    }

    // ── System UI ──────────────────────────────────────────────────────────────

    private fun hideSystemUI() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { ctrl ->
                ctrl.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                ctrl.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) { hideSystemUI(); webView?.requestFocus() }
    }

    override fun onResume()  { super.onResume();  webView?.onResume();  webView?.requestFocus() }
    override fun onPause()   { webView?.onPause(); super.onPause() }
    override fun onDestroy() { webView?.stopLoading(); webView?.destroy(); webView = null; super.onDestroy() }
}
