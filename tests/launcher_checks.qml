import QtQuick
import QtTest

TestCase {
    id: checks
    property var host
    name: "NativeLauncher"
    when: host !== undefined && host.ready

    Window {
        id: outsideWindow
        transientParent: null
        width: 100
        height: 100
        visible: false
    }

    function cleanup() {
        host.close();
        outsideWindow.visible = false;
        tryCompare(findChild(host, "arasakaLauncherPopup"), "active", false);
    }

    function test_00_nativePopup() {
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
            verify(!host.launcherItem.visible);
            verify(host.trayItem.visible);
            var search = findChild(host, "compactSearchField");
            verify(search !== null);
            tryCompare(search, "activeFocus", true);
            compare(search.text, "");
            compare(popup.x, Math.round(host.targetScreen.virtualX + (host.targetScreen.width - popup.width) / 2));
            const screenBottom = host.targetScreen.virtualY + host.targetScreen.height;
            const launcherY = popup.y;
            // Start at or above center, with room reserved for the still-hidden tray.
            verify(launcherY >= host.targetScreen.virtualY + 24);
            verify(launcherY <= Math.round(host.targetScreen.virtualY + (host.targetScreen.height - popup.height) / 2));
            verify(launcherY + popup.height + trayPopup.height < screenBottom);
            // Deliver real key events into the popup rather than plasmawindowed's outer window.
            checks.parent = search;
            popup.requestActivate();
            tryCompare(popup, "active", true);
            host.trayItem.plasmoid.activated();
            tryCompare(trayPopup, "visible", true);
            compare(popup.visible, true);
            tryVerify(() => trayPopup.y > popup.y + popup.height && trayPopup.y + trayPopup.height <= screenBottom);
            compare(popup.y, launcherY);
            host.toggle();
            tryCompare(popup, "visible", false);
            tryCompare(trayPopup, "visible", false);
            compare(popup.y, launcherY);
            tryCompare(popup, "active", false);
            host.plasmoid.configuration.primaryConnector = ownerScreen.name;
            host.toggle();
            tryCompare(popup, "visible", true);
            compare(host.targetScreen.name, ownerScreen.name);
            tryCompare(popup, "active", true);
            mouseClick(findChild(host, "fullMenuButton"));
            tryCompare(host.launcherItem, "visible", true);
            verify(host.launcherItem.width > 300);
            verify(host.launcherItem.height > 300);
            verify(waitForRendering(host.launcherItem));
            compare(popup.visible, true);
            keyClick(Qt.Key_A);
            tryCompare(host.launcherItem.searchField, "text", "a");
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

    function test_cancelPendingLaunch() {
        var popup = findChild(host, "arasakaLauncherPopup");
        host.toggle();
        tryCompare(popup, "active", true);
        var search = findChild(host, "compactSearchField");
        var results = findChild(host, "applicationResults");
        search.text = "arasakacancelledfixture";
        search.accepted();
        host.close();
        // Allow asynchronous results and any queued activation to finish.
        tryCompare(results, "count", 1);
        tryCompare(results, "enabled", true);
        compare(popup.visible, false);
        tryCompare(popup, "active", false);
        host.toggle();
        tryCompare(popup, "active", true);
        search.text = "arasakacancelledfixture";
        search.accepted();
        findChild(host, "fullMenuButton").clicked();
        verify(waitForRendering(host.launcherItem));
        compare(popup.visible, true);
        mouseClick(findChild(host, "backToSearchButton"));
        tryCompare(search, "activeFocus", true);
        tryCompare(results, "enabled", true);
        compare(search.text, "arasakacancelledfixture");
        compare(popup.visible, true);
    }

    function test_searchAndLaunch() {
        try {
            var popup = findChild(host, "arasakaLauncherPopup");
            host.toggle();
            tryCompare(popup, "active", true);
            var search = findChild(host, "compactSearchField");
            verify(search !== null);
            var results = findChild(host, "applicationResults");
            verify(results !== null);
            checks.parent = search;
            compare(results.visible, false);
            keyClick(Qt.Key_Return);
            compare(popup.visible, true);
            const query = "arasakasearchfixture";
            for (var character of query) {
                keyClick(character);
            }
            compare(search.text, query);
            tryCompare(results, "count", 2);
            tryCompare(results, "enabled", true);
            compare(results.currentIndex, 0);
            verify(results.visible);
            verify(popup.height < 500);
            keyClick(Qt.Key_Down);
            compare(results.currentIndex, 1);
            keyClick(Qt.Key_Up);
            compare(results.currentIndex, 0);

            search.text = "no-such-arasaka-application-93721";
            tryCompare(results, "count", 0);
            keyClick(Qt.Key_Return);
            compare(popup.visible, true);
            search.text = "   ";
            tryCompare(results, "visible", false);
            keyClick(Qt.Key_Return);
            compare(popup.visible, true);

            search.text = "arasakasearchfixture alpha";
            tryCompare(results, "count", 1);
            tryCompare(results, "enabled", true);
            verify(results.currentItem.text.indexOf("Alpha") !== -1);
            keyClick(Qt.Key_Return);
            tryCompare(popup, "visible", false);
            tryCompare(popup, "active", false);

            host.toggle();
            tryCompare(popup, "active", true);
            compare(search.text, "");
            compare(results.visible, false);
            // Enter immediately after replacing an existing match must launch the
            // new query, never the still-visible result of the previous search.
            search.text = "arasakasearchfixture alpha";
            tryCompare(results, "count", 1);
            tryCompare(results, "enabled", true);
            search.text = "arasakasearchfixture beta";
            keyClick(Qt.Key_Return);
            tryCompare(popup, "visible", false);
        } catch (error) {
            console.error(error.stack);
            throw error;
        }
    }

    function test_switchViews() {
        var popup = findChild(host, "arasakaLauncherPopup");
        host.toggle();
        tryCompare(popup, "active", true);
        var search = findChild(host, "compactSearchField");
        verify(search !== null);
        checks.parent = search;
        const compactHeight = popup.height;
        mouseClick(findChild(host, "fullMenuButton"));
        tryCompare(host.launcherItem, "visible", true);
        verify(popup.height > compactHeight);
        verify(host.trayItem.visible);
        var trayPopup = findChild(host.trayItem, "popupWindow");
        const menuY = popup.y;
        host.trayItem.plasmoid.activated();
        tryCompare(trayPopup, "visible", true);
        compare(popup.visible, true);
        compare(popup.y, menuY);
        tryVerify(() => trayPopup.y > popup.y + popup.height);
        verify(trayPopup.y + trayPopup.height <= host.targetScreen.virtualY + host.targetScreen.height);
        host.trayItem.plasmoid.activated();
        tryCompare(trayPopup, "visible", false);
        mouseClick(findChild(host, "backToSearchButton"));
        tryCompare(host.launcherItem, "visible", false);
        compare(popup.visible, true);
        tryCompare(search, "activeFocus", true);
        compare(popup.height, compactHeight);
        mouseClick(findChild(host, "fullMenuButton"));
        host.close();
        host.toggle();
        tryCompare(search, "activeFocus", true);
        compare(host.launcherItem.visible, false);
        compare(search.text, "");
        keyClick(Qt.Key_Escape);
        tryCompare(popup, "visible", false);
    }

    function test_stableSearchGeometry() {
        try {
            var popup = findChild(host, "arasakaLauncherPopup");
            host.toggle();
            tryCompare(popup, "active", true);
            var search = findChild(host, "compactSearchField");
            var results = findChild(host, "applicationResults");
            verify(waitForRendering(search));
            const geometry = Qt.rect(popup.x, popup.y, popup.width, popup.height);
            const searchPosition = search.mapToGlobal(0, 0);
            const trayPosition = host.trayItem.mapToGlobal(0, 0);
            const cases = [
                {query: "arasakasearchfixture", count: 2},
                {query: "arasakasearchfixture alpha", count: 1},
                {query: "arasakascrollfixture", count: 8},
                {query: "no-such-arasaka-application-93721", count: 0},
                {query: "", count: 0}
            ];
            for (const entry of cases) {
                search.text = entry.query;
                tryCompare(results, "count", entry.count);
                if (entry.query) {
                    tryCompare(results, "enabled", true);
                }
                verify(waitForRendering(search));
                compare(Qt.rect(popup.x, popup.y, popup.width, popup.height), geometry,
                    "Search results must not resize or reposition the launcher: " + entry.query);
                compare(search.mapToGlobal(0, 0), searchPosition);
                compare(host.trayItem.mapToGlobal(0, 0), trayPosition);
            }
        } catch (error) {
            console.error(error.stack);
            throw error;
        }
    }

    function test_queryRoundTrip() {
        var popup = findChild(host, "arasakaLauncherPopup");
        host.toggle();
        tryCompare(popup, "active", true);
        var search = findChild(host, "compactSearchField");
        var results = findChild(host, "applicationResults");
        search.text = "arasakasearchfixture";
        tryCompare(results, "count", 2);
        tryCompare(results, "enabled", true);
        search.text = "arasakasearchfixture alpha";
        search.text = "arasakasearchfixture";
        tryCompare(results, "enabled", true);
        compare(results.count, 2);
        compare(results.currentIndex, 0);
        checks.parent = search;
        keyClick(Qt.Key_Down);
        compare(results.currentIndex, 1);
        search.text = "searchfixture";
        tryCompare(results, "enabled", true);
        compare(results.count, 2);
        compare(results.currentIndex, 0);
    }

    function test_scrollAndMouseLaunch() {
        try {
            var popup = findChild(host, "arasakaLauncherPopup");
            host.toggle();
            tryCompare(popup, "active", true);
            var search = findChild(host, "compactSearchField");
            var results = findChild(host, "applicationResults");
            checks.parent = search;
            search.text = "arasakascrollfixture";
            tryCompare(results, "count", 8);
            tryCompare(results, "enabled", true);
            verify(results.height < results.contentHeight);
            const resultsHeight = results.height;
            for (var row = 0; row < 7; row++) {
                keyClick(Qt.Key_Down);
            }
            compare(results.currentIndex, 7);
            verify(results.contentY > 0);
            compare(results.height, resultsHeight);
            // Equal-relevance matches have no guaranteed alphabetical order.
            console.log("ARASAKA_SCROLL_SELECTION", results.currentItem.text);
            keyClick(Qt.Key_Return);
            tryCompare(popup, "visible", false);
            tryCompare(popup, "active", false);
            host.toggle();
            tryCompare(popup, "active", true);
            search.text = "arasakascrollfixture 6";
            tryCompare(results, "count", 1);
            tryCompare(results, "enabled", true);
            mouseClick(results.currentItem);
            tryCompare(popup, "visible", false);
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
