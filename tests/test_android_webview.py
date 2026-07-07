from pathlib import Path


def test_android_webview_keeps_system_bars_visible_in_dark_theme():
    activity_source = Path("android-webview/app/src/main/java/com/pjscreator/jisungport/MainActivity.java").read_text(encoding="utf-8")
    styles_source = Path("android-webview/app/src/main/res/values/styles.xml").read_text(encoding="utf-8")

    assert "configureSystemBars(root);" in activity_source
    assert "setStatusBarColor(SYSTEM_BAR_COLOR)" in activity_source
    assert "setNavigationBarColor(SYSTEM_BAR_COLOR)" in activity_source
    assert "~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR" in activity_source
    assert "~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR" in activity_source
    assert '<item name="android:windowLightStatusBar">false</item>' in styles_source
