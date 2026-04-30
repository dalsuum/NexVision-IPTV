# WebView JavaScript interface — keep any @JavascriptInterface methods if added later
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
