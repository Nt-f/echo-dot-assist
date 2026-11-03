/* Which app is in front, for hassmic (kiosk.c kiosk_in_front): an accessibility service told of every window that comes
 * forward, which reports the app whose activity it is to GET /kiosk/shell/front/<package> (this app's uid only).
 *
 * Why this way: hassmic is no app and Android 7 tells no one else.  Its /proc hides the others' processes (hidepid=2;
 * group readproc sees them, but an app's oom_score_adj, which says which is in front, is 0400 on Fire OS 7), and Fire
 * OS keeps no usage statistics (dumpsys usagestats lists no app's events).  An accessibility service is what launchers
 * and kiosk apps use; root's main.sh (screen_grants) switches this one on, as it does the keyboard.  It asks for
 * nothing but window changes: no content of any window.
 *
 * Only an app's activity or an app with a launcher entry counts: the keyboard, the shell's own bar and the system's
 * dialogs are windows too, but not "in front". */
package io.github.gamer92000.echodotassist.kiosk;

import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.pm.PackageManager;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;

import java.net.HttpURLConnection;
import java.net.URL;

public class Watcher extends AccessibilityService {
    static final String REPORT = "http://127.0.0.1:28931/kiosk/shell/front/";
    static final long AGAIN_MS = 20000;         // hassmic trusts a report for a minute: said again while nothing changes

    final Handler ui = new Handler(Looper.getMainLooper());
    volatile String front = "";
    final Runnable again = new Runnable() { @Override public void run() { report(); ui.postDelayed(this, AGAIN_MS); } };

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        ui.postDelayed(again, AGAIN_MS);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        if (e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || e.getPackageName() == null || e.getClassName() == null) return;
        String pkg = e.getPackageName().toString(), cls = e.getClassName().toString();
        if (pkg.equals("com.android.systemui") || pkg.equals("android")) return;      // the system's own windows
        boolean activity;
        try { getPackageManager().getActivityInfo(new ComponentName(pkg, cls), 0); activity = true; }
        catch (PackageManager.NameNotFoundException x) { activity = false; }
        if (pkg.equals(getPackageName()) && !activity) return;      // the bar and the keyboard; the kiosk's screen counts
        // an app brought back from behind names a view of its window, not its activity (seen on the Show 5 with
        // NewPipe): an app that has a launcher entry counts all the same; other packages' windows (an overlay) do not
        if (!activity && getPackageManager().getLaunchIntentForPackage(pkg) == null) return;
        if (pkg.equals(front)) return;
        front = pkg;
        report();
    }

    void report() {
        final String p = front;
        if (p.isEmpty()) return;
        new Thread(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(REPORT + p).openConnection();
                c.setConnectTimeout(2000); c.setReadTimeout(3000);
                c.getResponseCode(); c.disconnect();
            } catch (Exception x) { }           // hassmic restarting: said again in 20 s
        }, "watcher-report").start();
    }

    @Override public void onInterrupt() { }
}
