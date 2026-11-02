/* hassmic's kiosk on the Echo Show: Home Assistant (the wall panel, its own UI), Music Assistant or any page of the
 * integration's list, full screen in a WebView on the firmware's Amazon WebView (Chromium 118).
 *
 * Everything it shows comes from hassmic (src/hassmic/kiosk.c) over loopback, GET http://127.0.0.1:28931/kiosk/config:
 * the screens, Home Assistant's address and a long-lived token of the kiosk's own Home Assistant user, all set up from
 * Home Assistant by the hassmic integration.  The poll is also how hassmic knows the app is in front (/front, /back):
 * its display gives the screen to the app while it has nothing of its own to show.
 *
 * The login: the Echo has no keyboard.  Before the first page of Home Assistant's address, the token goes into that
 * origin's localStorage as the frontend keeps its own ("hassTokens", never expiring, no refresh token), through a page
 * loaded with Home Assistant's origin as its base URL; the frontend and the wall panel then use it as they would a
 * login of their own.
 *
 * Memory (the Show 5 has 1 GB, the whole of this must stay well under 512 MB): one WebView, one page at a time
 * (switching screens navigates, so the last screen's page is freed), no WebView at all while the kiosk is off, the
 * renderer's caches dropped when Android says memory runs low.
 *
 * Switching: a small handle at the top edge; a tap shows the screens.  Untouched for "return" seconds on another
 * screen, back to the default one.
 *
 * Typing: the Echo has no input method at all (Amazon's bluestone IME goes with its apps, there was never a LatinIME),
 * so the app has a keyboard of its own (Keys below): a script put into every page tells it through the bridge when a
 * text field has the focus (focusin/focusout, through shadow roots: Home Assistant's fields are in them), and it types
 * by real key events into the WebView, as a USB keyboard would.  The page gets smaller while it shows. */
package org.hassmic.kiosk;

import android.app.Activity;
import android.content.ComponentCallbacks2;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class Kiosk extends Activity {
    static final String CONFIG = "http://127.0.0.1:28931/kiosk/config";
    static final int POLL_MS = 5000;            // in front: hassmic gives the screen to the app by these
    static final int PAUSED_POLL_MS = 30000;    // paused (the screen dark): only that it is alive, so hassmic does not start it

    final Handler ui = new Handler(Looper.getMainLooper());
    FrameLayout root;
    WebView web;
    LinearLayout bar, column;
    Keys keys;
    TextView note;
    volatile boolean resumed;
    Thread poller;

    /* the config as hassmic last gave it (UI thread) */
    String cfgText = "";
    boolean enabled;
    String ha = "", token = "";
    String[] names = new String[0], urls = new String[0];
    int def, returnS;
    int current = -1;
    long touched;
    String injectedFor = "";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        note = new TextView(this);
        note.setTextColor(0xff8a8a8a);
        note.setTextSize(18);
        note.setGravity(Gravity.CENTER);
        root.addView(note, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        immersive();
        touched = SystemClock.uptimeMillis();
        try { WebView.setWebContentsDebuggingEnabled(true); } catch (Throwable t) { }   // adb is root's already
    }

    void immersive() {
        root.setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        immersive();
        if (web != null) web.onResume();
        if (poller == null) { poller = new Thread(this::pollLoop, "kiosk-poll"); poller.setDaemon(true); poller.start(); }
        else synchronized (this) { notifyAll(); }
    }

    @Override
    protected void onPause() {
        resumed = false;
        if (web != null) web.onPause();
        synchronized (this) { notifyAll(); }    // the poller says /back at once
        super.onPause();
    }

    @Override
    public void onUserInteraction() { touched = SystemClock.uptimeMillis(); }

    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        if (web != null && level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW) web.freeMemory();
    }

    @Override
    public void onBackPressed() { if (web != null && web.canGoBack()) web.goBack(); }

    /* ---------------------------------------------------------------- the config */

    static String fetch(String u) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(u).openConnection();
            c.setConnectTimeout(2000); c.setReadTimeout(3000); c.setUseCaches(false);
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream o = new ByteArrayOutputStream();
            byte[] buf = new byte[4096]; int n;
            while ((n = in.read(buf)) > 0 && o.size() < 65536) o.write(buf, 0, n);
            return o.toString("UTF-8");
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    void pollLoop() {
        for (;;) {
            // with nothing of its own to show (no web page among the screens), as if it were not in front: hassmic's clock
            boolean front = resumed && (urls.length > 0 || cfgText.isEmpty());
            final String t = fetch(CONFIG + (front ? "/front" : "/back"));
            if (front) ui.post(() -> apply(t));
            synchronized (this) { try { wait(front ? POLL_MS : PAUSED_POLL_MS); } catch (InterruptedException e) { return; } }
        }
    }

    void apply(String t) {
        if (t == null) { if (web == null) note.setText("Waiting for hassmic…"); return; }
        if (!t.equals(cfgText)) {
            cfgText = t;
            try {
                JSONObject j = new JSONObject(t);
                enabled = j.optBoolean("enabled");
                ha = j.optString("ha", "");
                String tok = j.optString("token", "");
                boolean newLogin = !tok.equals(token);
                token = tok;
                JSONArray s = j.optJSONArray("screens");
                int n = s == null ? 0 : s.length();
                String[] nn = new String[n], uu = new String[n];
                // only web pages: "hassmic:clock" and the like are for screen apps that draw them (docs/screen-apps.md)
                java.util.List<String> ln = new java.util.ArrayList<>(), lu = new java.util.ArrayList<>();
                for (int i = 0; i < n; i++) {
                    String u = s.getJSONObject(i).optString("url");
                    if (u.startsWith("http://") || u.startsWith("https://")) { ln.add(s.getJSONObject(i).optString("name")); lu.add(u); }
                }
                n = lu.size(); nn = ln.toArray(new String[0]); uu = lu.toArray(new String[0]);
                boolean same = java.util.Arrays.equals(uu, urls);
                names = nn; urls = uu;
                // the start screen counted among all of them: here among the web pages (one this app skips: the first)
                int d0 = j.optInt("default", 0), total = s == null ? 0 : s.length();
                String du = d0 >= 0 && d0 < total ? s.getJSONObject(d0).optString("url") : "";
                def = Math.max(0, lu.indexOf(du)); returnS = j.optInt("return", 0);
                if (newLogin) injectedFor = "";
                if (!enabled || n == 0) { stop(); return; }
                start();
                buildBar();
                if (!same || newLogin || current < 0 || current >= n) show(def);
            } catch (Exception e) {
                note.setText("hassmic sent a config this app cannot read");
            }
            return;
        }
        if (!enabled || web == null) return;
        // untouched long enough on another screen: back to the default one
        if (returnS > 0 && current != def && SystemClock.uptimeMillis() - touched > returnS * 1000L) show(def);
    }

    /* ---------------------------------------------------------------- the WebView */

    void start() {
        if (web != null) return;
        note.setText("");
        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setSupportZoom(false);
        s.setUserAgentString(s.getUserAgentString() + " hassmic-kiosk/1");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) { return false; }     // every link stays here

            @Override
            public void onPageStarted(WebView v, String url, android.graphics.Bitmap icon) { keys.hide(); }

            @Override
            public void onPageFinished(WebView v, String url) { v.evaluateJavascript(FOCUS_JS, null); }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (!r.isForMainFrame()) return;
                final int at = current;
                // Home Assistant restarting, Wi-Fi back later: try the screen again
                ui.postDelayed(() -> { if (web != null && current == at) show(at); }, 15000);
            }
        });
        web.addJavascriptInterface(new Bridge(), "HassmicKiosk");
        // the page above, the keyboard below it while one types: the page gets smaller, its field stays in sight
        column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.addView(web, new LinearLayout.LayoutParams(-1, 0, 1f));
        keys = new Keys();
        column.addView(keys, new LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(column, 0, new FrameLayout.LayoutParams(-1, -1));
        if (resumed) web.onResume();
    }

    void stop() {
        current = -1;
        if (bar != null) { root.removeView(bar); bar = null; }
        View h = root.findViewWithTag("handle"); if (h != null) root.removeView(h);
        if (web == null) return;
        root.removeView(column); column = null; keys = null;
        web.stopLoading(); web.loadUrl("about:blank"); web.destroy();
        web = null;
        note.setText("");
    }

    static String origin(String u) {
        Uri x = Uri.parse(u);
        if (x.getScheme() == null || x.getHost() == null) return "";
        return x.getScheme() + "://" + x.getHost() + (x.getPort() > 0 ? ":" + x.getPort() : "");
    }

    void show(int i) {
        if (web == null || i < 0 || i >= urls.length) return;
        current = i;
        touched = SystemClock.uptimeMillis();
        String url = urls[i], o = origin(url), hao = origin(ha);
        hideBar();
        if (!token.isEmpty() && !hao.isEmpty() && o.equals(hao) && !injectedFor.equals(hao)) {
            injectedFor = hao;
            String tokens;
            try {
                JSONObject t = new JSONObject();
                t.put("access_token", token); t.put("token_type", "Bearer"); t.put("expires_in", 315360000);
                t.put("hassUrl", hao); t.put("clientId", hao + "/"); t.put("expires", 4102444800000L); t.put("refresh_token", "");
                tokens = t.toString();
            } catch (Exception e) { tokens = "{}"; }
            String html = "<!doctype html><script>try{localStorage.setItem('hassTokens'," + JSONObject.quote(tokens)
                    + ")}catch(e){}location.replace(" + JSONObject.quote(url) + ")</script>";
            web.loadDataWithBaseURL(hao + "/hassmic-kiosk-login", html, "text/html", "UTF-8", null);
        } else {
            web.loadUrl(url);
        }
        web.clearHistory();
    }

    /* ---------------------------------------------------------------- the switcher */

    int dp(float v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    void buildBar() {
        if (bar != null) root.removeView(bar);
        View old = root.findViewWithTag("handle"); if (old != null) root.removeView(old);
        // the handle: a pill at the top edge, its touch area larger than it looks
        FrameLayout handle = new FrameLayout(this);
        handle.setTag("handle");
        View pill = new View(this);
        GradientDrawable g = new GradientDrawable(); g.setColor(0x99a0a0a0); g.setStroke(1, 0x55000000); g.setCornerRadius(dp(3));   // seen on white pages and dark ones
        pill.setBackground(g);
        handle.addView(pill, new FrameLayout.LayoutParams(dp(56), dp(5), Gravity.CENTER));
        handle.setOnClickListener(v -> { if (bar.getVisibility() == View.VISIBLE) hideBar(); else showBar(); });
        root.addView(handle, new FrameLayout.LayoutParams(dp(120), dp(24), Gravity.TOP | Gravity.CENTER_HORIZONTAL));

        bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setPadding(dp(8), dp(8), dp(8), dp(8));
        GradientDrawable bg = new GradientDrawable(); bg.setColor(0xe6202124); bg.setCornerRadius(dp(18));
        bar.setBackground(bg);
        for (int i = 0; i < names.length; i++) {
            final int k = i;
            Button b = new Button(this);
            b.setText(names[i]); b.setAllCaps(false); b.setTextColor(Color.WHITE); b.setTextSize(16);
            GradientDrawable bb = new GradientDrawable(); bb.setColor(0x33ffffff); bb.setCornerRadius(dp(14));
            b.setBackground(bb);
            b.setPadding(dp(18), 0, dp(18), 0);
            b.setOnClickListener(v -> show(k));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(44));
            lp.setMargins(dp(4), 0, dp(4), 0);
            bar.addView(b, lp);
        }
        Button reload = new Button(this);
        reload.setText("↻"); reload.setTextColor(Color.WHITE); reload.setTextSize(18);
        GradientDrawable rb = new GradientDrawable(); rb.setColor(0x22ffffff); rb.setCornerRadius(dp(14));
        reload.setBackground(rb);
        reload.setOnClickListener(v -> { hideBar(); if (web != null) web.reload(); });
        bar.addView(reload, new LinearLayout.LayoutParams(dp(48), dp(44)));
        bar.setVisibility(View.GONE);
        root.addView(bar, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.CENTER_HORIZONTAL) {{ topMargin = dp(28); }});
    }

    final Runnable autoHide = this::hideBar;
    void showBar() { if (bar == null) return; bar.setVisibility(View.VISIBLE); bar.bringToFront(); ui.removeCallbacks(autoHide); ui.postDelayed(autoHide, 8000); }
    void hideBar() { if (bar != null) bar.setVisibility(View.GONE); ui.removeCallbacks(autoHide); }

    /* ---------------------------------------------------------------- for the pages: the screens and switching
     * (the wall panel's "Home Assistant" and "Music" buttons).  Nothing secret: no token through here. */
    class Bridge {
        @JavascriptInterface
        public String screens() {
            JSONArray a = new JSONArray();
            String[] n = names;
            for (String s : n) a.put(s);
            return a.toString();
        }

        @JavascriptInterface
        public int current() { return current; }

        @JavascriptInterface
        public void go(final int i) { ui.post(() -> show(i)); }

        /* the page's focus (FOCUS_JS): a text field has it (kind 1 a password, 2 numbers) or none has */
        @JavascriptInterface
        public void typing(final boolean on, final int kind) { ui.post(() -> { if (keys == null) return; if (on) keys.show(kind); else keys.hide(); }); }
    }

    /* put into every page once loaded: tells the app whether a text field has the focus, looking through shadow roots */
    static final String FOCUS_JS = "(function(){if(window.__hmk)return;window.__hmk=1;"
        + "function deep(){var a=document.activeElement;while(a&&a.shadowRoot&&a.shadowRoot.activeElement)a=a.shadowRoot.activeElement;return a}"
        + "function ed(e){if(!e)return false;if(e.isContentEditable)return true;var t=(e.tagName||'').toLowerCase();if(t==='textarea')return true;"
        + "if(t!=='input')return false;var y=(e.type||'text').toLowerCase();"
        + "return['button','checkbox','radio','range','submit','reset','file','color','image','hidden'].indexOf(y)<0}"
        + "function tell(){try{var e=deep(),k=e&&e.type==='password'?1:e&&(e.type==='number'||e.inputMode==='numeric'||e.inputMode==='decimal')?2:0;"
        + "HassmicKiosk.typing(ed(e),k)}catch(x){}}"
        + "document.addEventListener('focusin',function(){setTimeout(tell,0)},true);"
        + "document.addEventListener('focusout',function(){setTimeout(tell,60)},true);tell()})()";

    /* ---------------------------------------------------------------- the keyboard */
    static final String[][] LETTERS = { { "q", "w", "e", "r", "t", "y", "u", "i", "o", "p" }, { "a", "s", "d", "f", "g", "h", "j", "k", "l" },
                                        { "\u21e7", "z", "x", "c", "v", "b", "n", "m", "\u232b" }, { "?123", "@", " ", ".", "\u23ce", "\u2304" } };
    static final String[][] SYMBOLS = { { "1", "2", "3", "4", "5", "6", "7", "8", "9", "0" }, { "@", "#", "$", "%", "&", "*", "-", "+", "(", ")" },
                                        { "=", "!", "\"", "'", ":", ";", "/", "?", "\u232b" }, { "ABC", ",", " ", ".", "\u23ce", "\u2304" } };
    class Keys extends LinearLayout {
        final KeyCharacterMap map = KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD);
        boolean shift, symbols;

        Keys() {
            super(Kiosk.this);
            setOrientation(VERTICAL);
            setBackgroundColor(0xff1c1c1e);
            setPadding(dp(4), dp(5), dp(4), dp(5));
            setVisibility(GONE);
            draw();
        }

        void show(int kind) {
            boolean was = getVisibility() == VISIBLE;
            symbols = kind == 2; shift = false; draw();
            setVisibility(VISIBLE);
            if (!was) ui.postDelayed(() -> { if (web != null) web.evaluateJavascript(
                "(function(){var a=document.activeElement;while(a&&a.shadowRoot&&a.shadowRoot.activeElement)a=a.shadowRoot.activeElement;"
                + "if(a&&a.scrollIntoView)a.scrollIntoView({block:'center'})})()", null); }, 200);
        }

        void hide() { setVisibility(GONE); }

        void draw() {
            removeAllViews();
            for (String[] row : symbols ? SYMBOLS : LETTERS) {
                LinearLayout r = new LinearLayout(Kiosk.this);
                r.setGravity(Gravity.CENTER);
                for (String k : row) {
                    TextView b = new TextView(Kiosk.this);
                    boolean special = k.length() > 1 || k.equals("\u21e7") || k.equals("\u232b") || k.equals("\u23ce") || k.equals("\u2304");
                    String label = k.equals(" ") ? "space" : k.length() == 1 && Character.isLetter(k.charAt(0)) && shift ? k.toUpperCase() : k;
                    b.setText(label);
                    b.setTextColor(Color.WHITE);
                    b.setTextSize(k.length() == 1 && !special ? 20 : 15);
                    b.setGravity(Gravity.CENTER);
                    GradientDrawable g = new GradientDrawable();
                    g.setColor(special ? 0xff2c2c2e : 0xff48484a);
                    if (k.equals("\u21e7") && shift) g.setColor(0xffe5e5ea);
                    if (k.equals("\u21e7") && shift) b.setTextColor(Color.BLACK);
                    g.setCornerRadius(dp(7));
                    b.setBackground(g);
                    float w = k.equals(" ") ? 4.6f : special ? 1.5f : 1f;
                    LayoutParams lp = new LayoutParams(0, dp(46), w);
                    lp.setMargins(dp(3), dp(3), dp(3), dp(3));
                    b.setOnTouchListener((v, ev) -> key(k, v, ev));
                    r.addView(b, lp);
                }
                addView(r, new LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT));
            }
        }

        final Runnable repeat = new Runnable() { public void run() { code(KeyEvent.KEYCODE_DEL); ui.postDelayed(this, 70); } };

        boolean key(String k, View v, MotionEvent ev) {
            int a = ev.getActionMasked();
            if (a == MotionEvent.ACTION_DOWN) {
                v.setAlpha(.6f);
                touched = SystemClock.uptimeMillis();
                if (k.equals("\u232b")) { code(KeyEvent.KEYCODE_DEL); ui.postDelayed(repeat, 450); }   // held: deletes on
                return true;
            }
            if (a == MotionEvent.ACTION_CANCEL) { v.setAlpha(1f); ui.removeCallbacks(repeat); return true; }
            if (a != MotionEvent.ACTION_UP) return true;
            v.setAlpha(1f); ui.removeCallbacks(repeat);
            switch (k) {
                case "\u232b": break;
                case "\u21e7": shift = !shift; draw(); break;
                case "?123": symbols = true; draw(); break;
                case "ABC": symbols = false; draw(); break;
                case "\u23ce": code(KeyEvent.KEYCODE_ENTER); break;
                case "\u2304": hide(); break;
                default:
                    type(shift && k.length() == 1 ? k.toUpperCase() : k);
                    if (shift) { shift = false; draw(); }
            }
            return true;
        }

        void code(int c) {
            if (web == null) return;
            long t = SystemClock.uptimeMillis();
            web.dispatchKeyEvent(new KeyEvent(t, t, KeyEvent.ACTION_DOWN, c, 0));
            web.dispatchKeyEvent(new KeyEvent(t, t, KeyEvent.ACTION_UP, c, 0));
        }

        /* real key events, as the virtual keyboard map has them; a character it lacks goes in by insertText */
        void type(String s) {
            if (web == null) return;
            KeyEvent[] evs = map.getEvents(s.toCharArray());
            if (evs != null) { for (KeyEvent e : evs) web.dispatchKeyEvent(e); return; }
            web.evaluateJavascript("document.execCommand('insertText',false," + JSONObject.quote(s) + ")", null);
        }
    }
}
