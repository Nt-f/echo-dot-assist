/* hassmic's shell on the Echo Show: the bar of places pulled down over whatever app is in front (docs/screen-apps.md
 * "The shell").  Home first (the screen app: hassmic's kiosk, Echo-Wall, or whatever app the owner picked), then the
 * screen app's screens (Home Assistant's own UI, Music Assistant, a page: the screen app opens one by its SCREEN
 * intent's extra "screen"), then the apps the owner installed.  So any app can be the screen app and every app is a
 * pull away, without the app knowing anything of hassmic.
 *
 * hassmic starts it (kiosk.c shell_tick: `am startservice` when its process is not there) and tells it what to show
 * over loopback, GET /kiosk/shell, answered to this app's uid alone (no login in it).  Its own process (":shell"), apart
 * from the kiosk's WebView: a few MB.
 *
 * The pull: hassmic reads the touch screen beside Android (display_screen.c) and tells this service of a swipe in
 * from an edge of the panel (GET /kiosk/shell/pull/<v>, a long poll); a swipe down from the middle of the screen's top
 * opens the bar.  No window over the apps: every touch, the swipe too, reaches the app under the finger.  Where hassmic
 * cannot (a model without board.touch_top), an invisible strip over the middle of the top edge stands in: a swipe down
 * there opens the bar, and a tap there does nothing (a window cannot hand a touch it took on to the app below).  The bar closes on a touch
 * anywhere else, a swipe up, a pick, or after 8 s untouched.
 *
 * Drawing over other apps needs SYSTEM_ALERT_WINDOW's app op: root's main.sh (screen_grants) allows it for this
 * package.  Without it there is no strip (an app is then left with Back, where it has one). */
package io.github.gamer92000.echodotassist.kiosk;

import android.animation.ValueAnimator;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;

public class Shell extends Service {
    static final String CONFIG = "http://127.0.0.1:28931/kiosk/shell";
    static final String SCREEN = "io.github.gamer92000.echodotassist.action.SCREEN";
    static final long POLL_MS = 15000, SHOWN_MS = 8000;

    final Handler ui = new Handler(Looper.getMainLooper());
    WindowManager wm;
    View strip;
    FrameLayout bar;
    volatile boolean running;
    /* hassmic's word (UI thread) */
    boolean enabled = true, pulls;
    String app = "", top = "";
    String[] screens = new String[0];
    final Runnable hide = this::collapse;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        running = true;
        Thread t = new Thread(this::poll, "shell-poll"); t.setDaemon(true); t.start();
        Thread p = new Thread(this::pulls, "shell-pulls"); p.setDaemon(true); p.start();
        // an app installed or removed: the bar is built anew each time it opens, nothing to keep; the strip stays
        IntentFilter f = new IntentFilter(Intent.ACTION_PACKAGE_REMOVED); f.addDataScheme("package");
        registerReceiver(new BroadcastReceiver() { @Override public void onReceive(Context c, Intent i) { collapse(); } }, f);
    }

    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        place();
        return START_STICKY;                    // Android starts it again if it takes the process; hassmic does too
    }

    @Override
    public void onDestroy() {
        running = false;
        collapse();
        if (strip != null) { wm.removeView(strip); strip = null; }
        super.onDestroy();
    }

    int dp(float v) { return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()); }

    /* the screen's orientation for hassmic's touch gate (which panel edge is the top, where a pull is held back from the
     * app): at the start, with every poll, and at once when the screen turns */
    String orientation() {
        android.util.DisplayMetrics m = new android.util.DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(m);
        return m.widthPixels > m.heightPixels ? "land" : "port";
    }

    void tellOrientation() {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(CONFIG + "/orientation/" + orientation()).openConnection();
            c.setConnectTimeout(2000); c.setReadTimeout(3000);
            c.getResponseCode(); c.disconnect();
        } catch (Exception e) { }               // hassmic restarting: the next poll says it
    }

    @Override
    public void onConfigurationChanged(android.content.res.Configuration cfg) {
        super.onConfigurationChanged(cfg);
        new Thread(this::tellOrientation, "shell-turn").start();
    }

    void poll() {
        while (running) {
            tellOrientation();
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(CONFIG).openConnection();
                c.setConnectTimeout(2000); c.setReadTimeout(3000);
                if (c.getResponseCode() == 200) {
                    InputStream in = c.getInputStream(); ByteArrayOutputStream o = new ByteArrayOutputStream(); byte[] b = new byte[4096]; int n;
                    while ((n = in.read(b)) > 0) o.write(b, 0, n);
                    JSONObject j = new JSONObject(o.toString("UTF-8"));
                    JSONArray s = j.optJSONArray("screens");
                    String[] names = new String[s == null ? 0 : s.length()];
                    for (int k = 0; k < names.length; k++) names[k] = s.getString(k);
                    final boolean en = j.optBoolean("enabled", true), pl = j.optBoolean("pulls", false);
                    final String a = j.optString("app", ""), tp = j.optString("top", "");
                    ui.post(() -> { enabled = en; app = a; screens = names; pulls = pl; top = tp; place(); });
                }
                c.disconnect();
            } catch (Exception e) { }           // hassmic restarting: the next look
            try { Thread.sleep(POLL_MS); } catch (InterruptedException e) { return; }
        }
    }

    /* hassmic's word of a swipe in from an edge: the bar when it is the screen's top (the panel's edge that is the top in
     * this orientation: "<landscape> <portrait>", board.touch_top) and in its middle 40 % */
    void pulls() {
        long v = -1;
        while (running) {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(CONFIG + "/pull/" + (v < 0 ? "now" : String.valueOf(v))).openConnection();
                c.setConnectTimeout(2000); c.setReadTimeout(30000);
                if (c.getResponseCode() == 200) {
                    InputStream in = c.getInputStream(); ByteArrayOutputStream o = new ByteArrayOutputStream(); byte[] b = new byte[512]; int n;
                    while ((n = in.read(b)) > 0) o.write(b, 0, n);
                    JSONObject j = new JSONObject(o.toString("UTF-8"));
                    long nv = j.optLong("v", 0);
                    if (v >= 0 && nv != v) {
                        final String edge = j.optString("edge", ""), tp = j.optString("top", "");
                        final double at = j.optDouble("at", -1);
                        ui.post(() -> { if (enabled && isTop(edge, tp) && at >= .3 && at <= .7) expand(); });
                    }
                    v = nv;
                } else Thread.sleep(5000);
                c.disconnect();
            } catch (Exception e) { try { Thread.sleep(5000); } catch (InterruptedException x) { return; } }
        }
    }

    boolean isTop(String edge, String tp) {
        String[] t = tp.trim().split("\\s+");
        if (t.length < 2) return false;
        android.util.DisplayMetrics m = new android.util.DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(m);
        return edge.equals(m.widthPixels > m.heightPixels ? t[0] : t[1]);
    }

    @SuppressWarnings("deprecation")
    WindowManager.LayoutParams params(int w, int h, int flags) {
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(w, h,
                Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE,
                flags | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN, PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        return p;
    }

    /* the strip while the screen is Home Assistant's (the kiosk on), none while it is off */
    void place() {
        boolean want = enabled && !pulls && (Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this));
        if (want && strip == null) {
            strip = new View(this) {
                float y0; boolean opened;
                @Override public boolean onTouchEvent(MotionEvent e) {
                    switch (e.getActionMasked()) {
                        case MotionEvent.ACTION_DOWN: y0 = e.getRawY(); opened = false; break;
                        case MotionEvent.ACTION_MOVE: if (!opened && e.getRawY() - y0 > dp(24)) { opened = true; expand(); } break;
                    }
                    return true;
                }
            };
            wm.addView(strip, params((int) (getResources().getDisplayMetrics().widthPixels * .4f), dp(18), 0));
        } else if (!want && strip != null) {
            collapse(); wm.removeView(strip); strip = null;
        }
    }

    /* ---------------------------------------------------------------- the bar */

    void expand() {
        if (bar != null) { ui.removeCallbacks(hide); ui.postDelayed(hide, SHOWN_MS); return; }
        PackageManager pm = getPackageManager();
        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        Drawable homeIcon = null;
        try { homeIcon = pm.getApplicationIcon(app.isEmpty() ? getPackageName() : app); } catch (PackageManager.NameNotFoundException e) { }
        row.addView(item("Home", homeIcon, null, this::home));
        for (final String s : screens) row.addView(item(s, null, s.substring(0, 1).toUpperCase(), () -> screen(s)));
        for (final Launchable.App a : Launchable.list(this, app)) row.addView(item(a.label, a.icon, null, () -> open(a.pkg)));
        HorizontalScrollView glass = new HorizontalScrollView(this);
        glass.setHorizontalScrollBarEnabled(false);
        GradientDrawable g = new GradientDrawable(); g.setColor(0xe6202124); g.setCornerRadius(dp(22));
        glass.setBackground(g);
        glass.setPadding(dp(8), dp(8), dp(8), dp(8));
        glass.addView(row);
        // put away by a touch anywhere else (ACTION_OUTSIDE) or a swipe up on it (seen before the items take it)
        FrameLayout root = new FrameLayout(this) {
            float y0;
            @Override public boolean onInterceptTouchEvent(MotionEvent e) {
                if (e.getActionMasked() == MotionEvent.ACTION_DOWN) y0 = e.getRawY();
                else if (e.getActionMasked() == MotionEvent.ACTION_MOVE && y0 - e.getRawY() > dp(24)) { collapse(); return true; }
                return false;
            }
            @Override public boolean onTouchEvent(MotionEvent e) {
                switch (e.getActionMasked()) {
                    case MotionEvent.ACTION_OUTSIDE: collapse(); return true;
                    case MotionEvent.ACTION_DOWN: y0 = e.getRawY(); return true;
                    case MotionEvent.ACTION_MOVE: if (y0 - e.getRawY() > dp(24)) { collapse(); return true; }
                }
                return super.onTouchEvent(e);
            }
        };
        root.setPadding(dp(16), dp(12), dp(16), 0);
        root.addView(glass, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.CENTER_HORIZONTAL));
        wm.addView(root, params(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH));
        bar = root;
        root.setTranslationY(-dp(120));        // dropped from the edge
        ValueAnimator va = ValueAnimator.ofFloat(-dp(120), 0f); va.setDuration(180);
        va.addUpdateListener(an -> root.setTranslationY((Float) an.getAnimatedValue())); va.start();
        ui.postDelayed(hide, SHOWN_MS);
    }

    void collapse() {
        ui.removeCallbacks(hide);
        if (bar != null) { wm.removeView(bar); bar = null; }
    }

    /* a place: its icon (an app's), else a letter on glass (a screen), the name under it; 84 dp wide */
    View item(String label, Drawable icon, String letter, Runnable go) {
        int w = dp(84);
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL); v.setGravity(Gravity.CENTER_HORIZONTAL);
        v.setPadding(0, dp(8), 0, dp(6));
        if (icon != null) {
            ImageView i = new ImageView(this); i.setImageDrawable(icon);
            v.addView(i, new LinearLayout.LayoutParams(dp(48), dp(48)));
        } else {
            TextView t = new TextView(this); t.setText(letter == null ? "⌂" : letter); t.setTextColor(Color.WHITE); t.setTextSize(22);
            t.setGravity(Gravity.CENTER);
            GradientDrawable b = new GradientDrawable(); b.setColor(0x2effffff); b.setCornerRadius(dp(12)); t.setBackground(b);
            v.addView(t, new LinearLayout.LayoutParams(dp(48), dp(48)));
        }
        TextView t = new TextView(this);
        t.setText(label); t.setTextColor(Color.WHITE); t.setTextSize(12); t.setMaxLines(1); t.setEllipsize(TextUtils.TruncateAt.END);
        t.setGravity(Gravity.CENTER_HORIZONTAL); t.setPadding(dp(4), dp(4), dp(4), 0);
        v.addView(t, new LinearLayout.LayoutParams(w, LinearLayout.LayoutParams.WRAP_CONTENT));
        v.setOnClickListener(x -> { collapse(); go.run(); });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(w, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMargins(dp(2), 0, dp(2), 0);
        v.setLayoutParams(lp);
        return v;
    }

    /* the screen app: by the contract's intent where it has one (an app made for hassmic: brought back where it was,
     * singleTask), else as the launcher starts it */
    void home() { startScreenApp(null); }

    void screen(String name) { startScreenApp(name); }

    void startScreenApp(String screen) {
        String pkg = app.isEmpty() ? getPackageName() : app;
        Intent i = new Intent(SCREEN).addCategory(Intent.CATEGORY_DEFAULT).setPackage(pkg)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        if (screen != null) i.putExtra("screen", screen); else i.putExtra("home", true);
        List<ResolveInfo> r = getPackageManager().queryIntentActivities(i, 0);
        if (r != null && !r.isEmpty()) { startActivity(i); return; }
        open(pkg);
    }

    void open(String pkg) {
        Intent i = Launchable.intent(this, pkg);
        if (i != null) startActivity(i);
    }

}
