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
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    // Null until initWebView() is called (may be skipped on first boot while
    // SetupActivity is in the foreground). All lifecycle hooks guard with ?.
    private var webView: WebView? = null

    // Registered before onCreate per AndroidX requirement — safe as a property
    // initialiser because ComponentActivity accepts registration at any point
    // before onStart.
    private val setupLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            // Config was saved — load the WebView with the new URL
            val config = ConfigManager.read(this)
            if (config != null) {
                initWebView(config.url)
            } else {
                // Defensive: write succeeded but read failed — open setup again
                openSetup()
            }
        } else {
            // SetupActivity swallows Back, so RESULT_CANCELED only arrives if
            // the system kills the activity (e.g. low-memory). Re-open setup.
            openSetup()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemUI()

        val config = ConfigManager.read(this)
        if (config == null) {
            // No config yet — show a dark placeholder and launch setup on top
            setContentView(View(this).apply { setBackgroundColor(0xFF06060A.toInt()) })
            openSetup()
        } else {
            initWebView(config.url)
        }
    }

    // ── Config-driven WebView ──────────────────────────────────────────────────

    private fun openSetup() {
        setupLauncher.launch(Intent(this, SetupActivity::class.java))
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun initWebView(url: String) {
        // If called a second time (config update) destroy the previous instance
        webView?.let { it.stopLoading(); it.destroy() }

        webView = WebView(this).apply {
            isFocusable = true
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

            webChromeClient = WebChromeClient()
            webViewClient   = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, url: String) = false
            }

            loadUrl(url)
        }

        setContentView(webView)
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

    // ── Lifecycle ──────────────────────────────────────────────────────────────

    override fun onResume() {
        super.onResume()
        webView?.onResume()
    }

    override fun onPause() {
        webView?.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        webView?.stopLoading()
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    // ── D-pad / remote back button ─────────────────────────────────────────────

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (webView?.canGoBack() == true) webView?.goBack()
            return true   // always consume — never propagate to the back stack
        }
        return super.onKeyDown(keyCode, event)
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (webView?.canGoBack() == true) webView?.goBack()
        // do not call super — never finish() this activity
    }
}
