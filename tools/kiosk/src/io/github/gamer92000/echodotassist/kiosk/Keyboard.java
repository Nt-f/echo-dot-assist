/* The Echo's keyboard, for every app: the Echo has no input method at all (Amazon's went with its apps), so nothing
 * could be typed into an app the owner installed (a video client's search, Home Assistant's own app).  Root's main.sh
 * (screen_grants) switches it on and makes it the default where there is none.  This app's own kiosk screens keep
 * their keyboard (Kiosk.java Keys: key events into the WebView, round screens), so it does not come up for them.
 *
 * android.inputmethodservice.KeyboardView: deprecated, but in every Android an Echo runs (7 to 9) and a few kB.  In the
 * shell's process (":shell"), apart from the kiosk's WebView. */
package io.github.gamer92000.echodotassist.kiosk;

import android.inputmethodservice.InputMethodService;
import android.inputmethodservice.KeyboardView;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;

@SuppressWarnings("deprecation")
public class Keyboard extends InputMethodService implements KeyboardView.OnKeyboardActionListener {
    KeyboardView view;
    android.inputmethodservice.Keyboard letters, symbols;
    boolean caps;

    @Override
    public View onCreateInputView() {
        letters = new android.inputmethodservice.Keyboard(this, R.xml.kb_letters);
        symbols = new android.inputmethodservice.Keyboard(this, R.xml.kb_symbols);
        view = (KeyboardView) getLayoutInflater().inflate(R.layout.keyboard, null);
        view.setKeyboard(letters);
        view.setPreviewEnabled(false);
        view.setOnKeyboardActionListener(this);
        return view;
    }

    @Override
    public void onStartInputView(EditorInfo info, boolean restarting) {
        super.onStartInputView(info, restarting);
        if (view != null) { setCaps(false); view.setKeyboard(letters); }
    }

    boolean other() { EditorInfo e = getCurrentInputEditorInfo(); return e == null || !getPackageName().equals(e.packageName); }
    // the kiosk's screens type with their own; an Echo has no hardware keyboard, so a request to show is always one
    @Override public boolean onShowInputRequested(int flags, boolean configChange) { return other(); }
    @Override public boolean onEvaluateInputViewShown() { return other(); }
    // landscape on a 480 px screen: Android would go full screen (an extract view over the app); the app stays seen
    @Override public boolean onEvaluateFullscreenMode() { return false; }

    void setCaps(boolean on) {
        caps = on;
        if (letters != null) letters.setShifted(on);
        if (view != null) view.invalidateAllKeys();
    }

    @Override
    public void onKey(int code, int[] codes) {
        InputConnection ic = getCurrentInputConnection();
        if (ic == null) return;
        switch (code) {
            case android.inputmethodservice.Keyboard.KEYCODE_DELETE: sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL); break;
            case android.inputmethodservice.Keyboard.KEYCODE_SHIFT: setCaps(!caps); break;
            case android.inputmethodservice.Keyboard.KEYCODE_MODE_CHANGE: view.setKeyboard(view.getKeyboard() == letters ? symbols : letters); break;
            case android.inputmethodservice.Keyboard.KEYCODE_CANCEL: requestHideSelf(0); break;
            case 10: {
                // a search field's "search", a form's "go": the action the field asks for, else a plain Enter
                EditorInfo e = getCurrentInputEditorInfo();
                int o = e == null ? 0 : e.imeOptions, action = o & EditorInfo.IME_MASK_ACTION;
                if ((o & EditorInfo.IME_FLAG_NO_ENTER_ACTION) == 0 && action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED)
                    ic.performEditorAction(action);
                else sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER);
                break;
            }
            default: {
                char c = (char) code;
                if (caps && Character.isLetter(c)) { c = Character.toUpperCase(c); setCaps(false); }   // one capital, as a phone's
                ic.commitText(String.valueOf(c), 1);
            }
        }
    }

    @Override public void onPress(int code) { }
    @Override public void onRelease(int code) { }
    @Override public void onText(CharSequence text) { InputConnection ic = getCurrentInputConnection(); if (ic != null) ic.commitText(text, 1); }
    @Override public void swipeLeft() { }
    @Override public void swipeRight() { }
    @Override public void swipeDown() { requestHideSelf(0); }
    @Override public void swipeUp() { }
}
