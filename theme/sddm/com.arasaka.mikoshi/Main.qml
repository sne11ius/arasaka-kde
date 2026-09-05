import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#07090c"
    property string message: "AUTHORIZED PERSONNEL ONLY"

    Image { anchors.fill: parent; source: config.background; fillMode: Image.PreserveAspectCrop; opacity: 0.72 }
    Rectangle { anchors.fill: parent; color: "#07090c"; opacity: 0.34 }

    Rectangle {
        width: Math.min(520, parent.width - 48)
        height: 500
        anchors.centerIn: parent
        color: "#e607090c"
        border.color: "#e60012"
        border.width: 1
        radius: 2

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 42
            spacing: 16
            Image {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 112
                Layout.preferredHeight: 112
                source: config.logo
                fillMode: Image.PreserveAspectFit
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: "ARASAKA // MIKOSHI"
                color: "#e8e9ea"
                font.family: "Rajdhani SemiBold"
                font.pixelSize: 24
                font.letterSpacing: 3
            }
            Rectangle { Layout.fillWidth: true; height: 2; color: "#e60012" }
            ComboBox {
                id: userName
                Layout.fillWidth: true
                model: userModel
                textRole: "name"
                currentIndex: userModel.lastIndex >= 0 ? userModel.lastIndex : 0
            }
            TextField {
                id: password
                Layout.fillWidth: true
                placeholderText: "PASSWORD"
                echoMode: TextInput.Password
                focus: true
                onAccepted: loginButton.clicked()
            }
            ComboBox {
                id: session
                Layout.fillWidth: true
                model: sessionModel
                textRole: "name"
                currentIndex: sessionModel.lastIndex
            }
            Button {
                id: loginButton
                Layout.fillWidth: true
                text: "AUTHENTICATE"
                onClicked: sddm.login(userName.currentText, password.text, session.currentIndex)
            }
            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: root.message
                color: "#737b86"
                font.family: "JetBrains Mono"
                font.pixelSize: 11
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                Button { text: "SUSPEND"; visible: sddm.canSuspend; onClicked: sddm.suspend() }
                Button { text: "RESTART"; visible: sddm.canReboot; onClicked: sddm.reboot() }
                Button { text: "SHUT DOWN"; visible: sddm.canPowerOff; onClicked: sddm.powerOff() }
            }
        }
    }
    Connections {
        target: sddm
        function onLoginFailed() {
            root.message = "ACCESS DENIED"
            password.text = ""
            password.forceActiveFocus()
        }
        function onLoginSucceeded() { root.message = "ACCESS GRANTED" }
    }
}
