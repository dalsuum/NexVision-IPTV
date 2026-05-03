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
import android.net.http.SslError
import android.webkit.SslErrorHandler
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
import java.net.URL
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

class MainActivity : AppCompatActivity() {

    private var webView: WebView? = null
    private var currentConfig: ServerConfig? = null
    private var backPressedAt = 0L
    private val castHelper by lazy { CastHelper(this) }

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
        castHelper.init()

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

            // Expose native Cast to the web UI (replaces the Web Sender SDK which
            // won't initialise inside a WebView — only works in Chrome).
            if (castHelper.isAvailable()) {
                addJavascriptInterface(castHelper.Bridge(), "Android")
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
                               <p style="color:#5A5A6A">https://${config.ip}:${config.port}</p>
                               <p style="color:#5A5A6A;font-size:14px">$msg</p>
                               <p style="color:#383848;font-size:12px;margin-top:32px">
                               Press back to exit &nbsp;·&nbsp; Hold back to reconfigure</p>
                               </body></html>""",
                            "text/html", "utf-8"
                        )
                    }
                }

                override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                    // Accept self-signed certificate from our configured server
                    if (error.url?.contains(config.ip) == true) handler.proceed()
                    else handler.cancel()
                }

                override fun onPageFinished(view: WebView, url: String) {
                    super.onPageFinished(view, url)
                    view.requestFocus()
                    // Override CastMgr to use the native Android Cast bridge instead of
                    // the Web Sender SDK (which never initialises inside a WebView).
                    if (castHelper.isAvailable()) {
                        view.evaluateJavascript(CAST_OVERRIDE_JS, null)
                    }
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
                val trustAll = arrayOf<X509TrustManager>(object : X509TrustManager {
                    override fun checkClientTrusted(c: Array<X509Certificate>, a: String) {}
                    override fun checkServerTrusted(c: Array<X509Certificate>, a: String) {}
                    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
                })
                val sslCtx = SSLContext.getInstance("TLS").apply { init(null, trustAll, SecureRandom()) }
                val conn = (URL("https://${config.ip}:${config.port}/api/rooms/register")
                    .openConnection() as HttpsURLConnection).apply {
                    sslSocketFactory = sslCtx.socketFactory
                    hostnameVerifier  = HostnameVerifier { _, _ -> true }
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

    // ── Cast JS override ───────────────────────────────────────────────────────

    companion object {
        // Injected into every page load.  Replaces CastMgr's Web Sender SDK
        // calls with Android bridge calls so the Cast buttons work inside WebView.
        private val CAST_OVERRIDE_JS = """
            (function() {
              if (typeof CastMgr === 'undefined') return;
              // Suppress any pending Web Sender SDK callback
              window['__onGCastApiAvailable'] = function() {};
              // Make all cast buttons visible (normally hidden until the SDK fires)
              document.querySelectorAll('.cast-btn').forEach(function(b) {
                b.style.display = '';
              });
              // requestSession: called when user taps Cast button on Live TV
              CastMgr.requestSession = function() {
                var ch = (typeof allChannels !== 'undefined' && typeof currentChId !== 'undefined')
                  ? allChannels.find(function(c) { return c.id === currentChId; })
                  : null;
                var url   = ch ? String(ch.stream_url  || '').trim() : '';
                var title = ch ? String(ch.name        || '')        : '';
                var logo  = (ch && typeof usableLogo === 'function')
                  ? (usableLogo(ch.tvg_logo_url) || '') : '';
                Android.requestCast(url, title, logo);
              };
              // loadMedia: called when channel changes while already casting
              CastMgr.loadMedia = function(ch) {
                if (!ch) return;
                var url   = String(ch.stream_url || '').trim();
                var title = String(ch.name       || '');
                var logo  = (typeof usableLogo === 'function')
                  ? (usableLogo(ch.tvg_logo_url) || '') : '';
                if (url) Android.loadCast(url, title, logo);
              };
              // loadVod: called when user casts a movie/episode
              CastMgr.loadVod = function(url, title, poster) {
                if (url) Android.loadVod(String(url), String(title || ''), String(poster || ''));
              };
              // isConnected: synchronous check used before opening local player
              CastMgr.isConnected = function() {
                return !!Android.isConnected();
              };
            })();
        """.trimIndent()
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
    override fun onDestroy() {
        castHelper.release()
        webView?.stopLoading(); webView?.destroy(); webView = null
        super.onDestroy()
    }
}
