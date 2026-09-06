import QtQuick
import QtQuick.Layouts
import org.kde.draganddrop as DragDrop
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid

ContainmentItem {
    id: root

    Layout.minimumWidth: 1
    Layout.minimumHeight: 1
    Layout.preferredWidth: 1
    Layout.preferredHeight: 1
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Plasmoid.status: PlasmaCore.Types.HiddenStatus
    visible: false

    property Item launcherItem: null
    property Item trayItem: null
    property bool focusAcquired: false
    property var targetScreen: Qt.application.screens[0]
    readonly property bool ready: launcherItem !== null && launcherItem.fullRepresentationItem !== null && trayItem !== null
    readonly property string requestToken: Plasmoid.configuration.requestToken
    onReadyChanged: acknowledge()
    // Scripted config reloads update the whole map; acknowledge after they finish.
    onRequestTokenChanged: Qt.callLater(root.acknowledge)

    function acknowledge() {
        Plasmoid.configuration.ready = ready;
        Plasmoid.configuration.readyToken = ready ? requestToken : "";
    }

    function attach(applet) {
        const plugin = applet.pluginName;
        if (plugin !== "org.kde.plasma.kickoff" && plugin !== "org.kde.plasma.systemtray") {
            return;
        }
        const item = root.itemFor(applet);
        if (!item) {
            console.error("Arasaka launcher could not load", plugin);
            return;
        }
        const slot = plugin === "org.kde.plasma.kickoff" ? menuSlot : traySlot;
        item.anchors.fill = undefined;
        item.parent = slot;
        item.anchors.fill = slot;
        item.visible = true;
        if (plugin === "org.kde.plasma.kickoff") {
            item.switchWidth = 0;
            item.switchHeight = 0;
            item.preferredRepresentation = item.fullRepresentation;
            launcherItem = item;
        } else {
            trayItem = item;
        }
    }

    function close() {
        focusAcquired = false;
        // The native tray advertises an open subpopup through its applet status.
        if (trayItem && trayItem.plasmoid.status === PlasmaCore.Types.RequiresAttentionStatus) {
            trayItem.plasmoid.activated();
        }
        popup.visible = false;
        if (launcherItem) {
            launcherItem.expanded = false;
        }
    }

    function center() {
        if (targetScreen) {
            popup.x = Math.round(targetScreen.virtualX + (targetScreen.width - popup.width) / 2);
            popup.y = Math.round(targetScreen.virtualY + (targetScreen.height - popup.height) / 2);
        }
    }

    function toggle() {
        if (popup.visible) {
            close();
            return;
        }
        if (!launcherItem || !launcherItem.fullRepresentationItem || !trayItem) {
            console.error("Arasaka launcher is not ready");
            return;
        }
        // KDE's output priority can differ from Qt's screen order on Wayland.
        const screens = Qt.application.screens;
        const screen = screens.find(screen => screen.name === Plasmoid.configuration.primaryConnector) || screens[0];
        if (!screen) {
            return;
        }
        targetScreen = screen;
        focusAcquired = false;
        launcherItem.expanded = true;
        popup.visible = true;
        center();
        popup.requestActivate();
        // Rapid reopening can keep the window active without another activeChanged.
        focusAcquired = popup.active;
        launcherItem.fullRepresentationItem.forceActiveFocus(Qt.ShortcutFocusReason);
    }

    Containment.onAppletAdded: applet => root.attach(applet)
    Component.onCompleted: {
        Plasmoid.configuration.ready = false;
        Plasmoid.configuration.readyToken = "";
        Qt.callLater(() => {
            const applets = Containment.applets;
            applets.forEach(applet => root.attach(applet));
            const missing = ["org.kde.plasma.kickoff", "org.kde.plasma.systemtray"].filter(plugin => !applets.some(applet => applet.pluginName === plugin));
            if (missing.length) {
                // Use Plasma's public widget-drop API; createApplet is a private slot.
                creationData.mimeData.setData("text/x-plasmoidservicename", missing.join("\n"));
                root.processMimeData(creationData.mimeData, 0, 0);
            }
            root.acknowledge();
        });
    }
    Component.onDestruction: close()

    DragDrop.DragArea {
        id: creationData
        visible: false
        enabled: false
    }

    Connections {
        target: Plasmoid
        function onActivated() {
            root.toggle();
        }
    }

    Connections {
        target: root.launcherItem
        function onExpandedChanged(expanded) {
            if (!expanded && popup.visible) {
                root.close();
            }
        }
    }

    PlasmaCore.Dialog {
        id: popup
        objectName: "arasakaLauncherPopup"
        title: "Arasaka Launcher"
        visible: false
        location: PlasmaCore.Types.Floating
        type: PlasmaCore.Dialog.AppletPopup
        flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        // Ignore focus-out from a previous opening until this opening gains focus.
        hideOnWindowDeactivate: root.focusAcquired
        onActiveChanged: {
            if (active)
                root.focusAcquired = true;
        }
        onWidthChanged: root.center()
        onHeightChanged: root.center()
        onVisibleChanged: {
            if (!visible) {
                root.close();
            }
        }

        mainItem: FocusScope {
            id: content
            width: Math.min(root.targetScreen ? root.targetScreen.width - 48 : 720, Math.max(640, root.launcherItem ? root.launcherItem.Layout.minimumWidth : 0))
            height: Math.min(root.targetScreen ? root.targetScreen.height - 48 : 620, Math.max(480, root.launcherItem ? root.launcherItem.Layout.minimumHeight : 0) + 56)
            focus: true
            Keys.onEscapePressed: root.close()

            ColumnLayout {
                anchors.fill: parent
                spacing: Kirigami.Units.smallSpacing

                Item {
                    id: menuSlot
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: "#e60012"
                    opacity: 0.6
                }

                Item {
                    id: traySlot
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(content.width, root.trayItem ? root.trayItem.Layout.minimumWidth : 200)
                    Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium + Kirigami.Units.smallSpacing * 2
                    Layout.bottomMargin: Kirigami.Units.smallSpacing
                }
            }
        }
    }
}
