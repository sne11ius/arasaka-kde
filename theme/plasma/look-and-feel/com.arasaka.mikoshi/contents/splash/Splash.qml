import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: "#07090c"
    property int stage

    Image {
        anchors.fill: parent
        source: "images/mikoshi.svg"
        fillMode: Image.PreserveAspectCrop
        opacity: 0.72
    }
    Rectangle { anchors.fill: parent; color: "#07090c"; opacity: 0.30 }
    Rectangle {
        width: parent.width
        height: 2
        color: "#e60012"
        opacity: 0.65
        NumberAnimation on y {
            from: 0
            to: root.height
            duration: 2400
            loops: Animation.Infinite
            running: Kirigami.Units.longDuration > 1
        }
    }
    Column {
        anchors.centerIn: parent
        spacing: Kirigami.Units.largeSpacing
        opacity: root.stage >= 2 ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 420 } }
        Image {
            width: Kirigami.Units.gridUnit * 8
            height: width
            anchors.horizontalCenter: parent.horizontalCenter
            source: "images/arasaka.svg"
            fillMode: Image.PreserveAspectFit
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "ARASAKA // MIKOSHI"
            color: "#e8e9ea"
            font.family: "Rajdhani SemiBold"
            font.pixelSize: Kirigami.Units.gridUnit * 1.4
            font.letterSpacing: 4
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Kirigami.Units.gridUnit * 16
            height: 2
            color: "#e60012"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "SECURE SESSION INITIALIZATION"
            color: "#737b86"
            font.family: "JetBrains Mono"
            font.pixelSize: Kirigami.Units.gridUnit * 0.65
            font.letterSpacing: 2
        }
    }
}
