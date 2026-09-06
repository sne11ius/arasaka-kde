import QtQuick
import QtTest

TestCase {
    id: checks
    property var host
    name: "NativeLauncher"
    when: host !== undefined && host.launcherItem !== null && host.trayItem !== null

    Window {
        id: outsideWindow
        transientParent: null
        width: 100
        height: 100
        visible: false
    }

    function test_nativePopup() {
        try {
            compare(host.plasmoid.applets.length, 2);
            verify(host.launcherItem.fullRepresentationItem !== null);
            compare(host.plasmoid.configuration.ready, true);
            host.plasmoid.configuration.requestToken = "test-session-1";
            tryCompare(host.plasmoid.configuration, "readyToken", "test-session-1");
            host.plasmoid.configuration.requestToken = "test-session-2";
            // A scripted whole-map reload can restore the old acknowledgement
            // after delivering requestTokenChanged in the same event-loop turn.
            host.plasmoid.configuration.readyToken = "test-session-1";
            tryCompare(host.plasmoid.configuration, "readyToken", "test-session-2");
            var popup = findChild(host, "arasakaLauncherPopup");
            verify(popup !== null);
            var trayPopup = findChild(host.trayItem, "popupWindow");
            verify(trayPopup !== null);
            compare(trayPopup.visible, false);
            compare(popup.visible, false);
            // Keep focus on the host's original screen while selecting the other
            // output as primary, catching accidental active-screen placement.
            const ownerScreen = Qt.application.screens.find(screen => screen.name === host.Screen.name) || Qt.application.screens[0];
            const primaryScreen = Qt.application.screens.find(screen => screen.name !== ownerScreen.name) || ownerScreen;
            host.plasmoid.configuration.primaryConnector = primaryScreen.name;
            host.toggle();
            tryCompare(popup, "visible", true);
            compare(host.targetScreen.name, primaryScreen.name);
            verify(host.launcherItem.fullRepresentationItem.visible);
            verify(host.trayItem.visible);
            verify(host.launcherItem.width > 300);
            verify(host.launcherItem.height > 300);
            compare(popup.x, Math.round(host.targetScreen.virtualX + (host.targetScreen.width - popup.width) / 2));
            compare(popup.y, Math.round(host.targetScreen.virtualY + (host.targetScreen.height - popup.height) / 2));
            // Deliver real key events into the popup rather than plasmawindowed's outer window.
            checks.parent = host.launcherItem;
            popup.requestActivate();
            tryCompare(popup, "active", true);
            keyClick(Qt.Key_A);
            tryCompare(host.launcherItem.searchField, "text", "a");
            host.trayItem.plasmoid.activated();
            tryCompare(trayPopup, "visible", true);
            compare(popup.visible, true);
            host.toggle();
            tryCompare(popup, "visible", false);
            tryCompare(trayPopup, "visible", false);
            host.plasmoid.configuration.primaryConnector = ownerScreen.name;
            host.toggle();
            tryCompare(popup, "visible", true);
            compare(host.targetScreen.name, ownerScreen.name);
            host.launcherItem.expanded = false;
            tryCompare(popup, "visible", false);
            host.toggle();
            tryCompare(popup, "visible", true);
            popup.requestActivate();
            tryCompare(popup, "active", true);
            keyClick(Qt.Key_Escape);
            tryCompare(popup, "visible", false);
            host.toggle();
            tryCompare(popup, "visible", true);
            popup.requestActivate();
            tryCompare(popup, "active", true);
            outsideWindow.visible = true;
            outsideWindow.requestActivate();
            tryCompare(outsideWindow, "active", true);
            tryCompare(popup, "visible", false);
            outsideWindow.visible = false;
        } catch (error) {
            console.error(error.stack);
            throw error;
        }
    }

    function cleanupTestCase() {
        console.log("ARASAKA_TEST_FAILURES", qtest_results.failCount);
        console.log("ARASAKA_TEST_FINISHED");
    }
}
