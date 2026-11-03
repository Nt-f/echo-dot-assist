/* The apps the owner installed (a YouTube client, a music app, Home Assistant's own app): every launchable activity
 * that is no system app's (Amazon's own, hassmic's kiosk and home), without the screen app (the bar's Home).  Android 7
 * has no package visibility rules to work around. */
package io.github.gamer92000.echodotassist.kiosk;

import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.drawable.Drawable;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class Launchable {
    static final class App {
        final String pkg, label; final Drawable icon;
        App(String pkg, String label, Drawable icon) { this.pkg = pkg; this.label = label; this.icon = icon; }
    }

    static List<App> list(Context ctx, String screenApp) {
        PackageManager pm = ctx.getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<App> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (ResolveInfo r : pm.queryIntentActivities(main, 0)) {
            ActivityInfo a = r.activityInfo;
            if (a.packageName.equals(ctx.getPackageName()) || a.packageName.equals(screenApp)) continue;
            if ((a.applicationInfo.flags & (ApplicationInfo.FLAG_SYSTEM | ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)) != 0) continue;
            if (!seen.add(a.packageName)) continue;
            out.add(new App(a.packageName, String.valueOf(a.loadLabel(pm)), a.loadIcon(pm)));
        }
        Collections.sort(out, (x, y) -> x.label.compareToIgnoreCase(y.label));
        return out;
    }

    /* the launcher's own way in: an app already running comes back where it was */
    static Intent intent(Context ctx, String pkg) {
        Intent i = ctx.getPackageManager().getLaunchIntentForPackage(pkg);
        return i == null ? null : i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
    }
}
