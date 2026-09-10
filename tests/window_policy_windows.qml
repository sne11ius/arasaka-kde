import QtQuick
import QtQuick.Window

Window {
    id: ssd
    title: "Policy SSD"
    visible: true
    width: 420; height: 300
    color: "#223344"
    Window {
        title: "Policy CSD"
        transientParent: null
        flags: Qt.Window | Qt.FramelessWindowHint
        visible: true
        width: 420; height: 300
        color: "#443322"
        Rectangle { width: parent.width; height: 35; color: "#995522" }
    }
    Window {
        title: "Policy Dialog"
        flags: Qt.Dialog
        transientParent: ssd
        visible: true
        width: 250; height: 160
        minimumWidth: 250; maximumWidth: 250
        minimumHeight: 160; maximumHeight: 160
        color: "#334422"
    }
}
