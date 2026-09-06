import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.private.kicker as Kicker

FocusScope {
    id: root

    signal fullMenuRequested()
    signal closeRequested()
    readonly property string query: searchField.text.trim()
    readonly property int rowHeight: Kirigami.Units.iconSizes.medium + Kirigami.Units.smallSpacing * 4
    property string launchQuery: ""
    property bool resultsReady: false
    implicitHeight: layout.implicitHeight

    function focusSearch() {
        searchField.forceActiveFocus(Qt.ShortcutFocusReason);
    }

    function reset() {
        launchQuery = "";
        searchField.text = "";
    }

    function activateCurrent() {
        if (!visible || !query || !runner.count) {
            return;
        }
        if (!resultsReady) {
            launchQuery = query;
            return;
        }
        launchQuery = "";
        if (results.currentIndex >= 0 && results.model.trigger(results.currentIndex, "", null)) {
            root.closeRequested();
        }
    }

    function updateQuery() {
        // Serialize submissions: KDE's debounce can leave querying stuck when
        // an in-flight query is replaced and then restored before it starts.
        if (runner.querying) {
            return;
        }
        if (runner.query !== query) {
            runner.query = query;
            return;
        }
        results.currentIndex = results.count > 0 ? 0 : -1;
        resultsReady = true;
        if (launchQuery && launchQuery === query) {
            activateCurrent();
        }
    }

    onQueryChanged: {
        launchQuery = "";
        resultsReady = false;
        updateQuery();
    }
    onVisibleChanged: {
        if (!visible) {
            launchQuery = "";
        }
    }

    Kicker.RunnerModel {
        id: runner
        runners: ["krunner_services"]
        // An empty enabled-runner list must not fall back to all search providers.
        mergeResults: false
        // Let model sorting and ListView bindings settle before selecting row 0.
        onQueryFinished: Qt.callLater(root.updateQuery)
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true

            PlasmaExtras.SearchField {
                id: searchField
                objectName: "compactSearchField"
                Layout.fillWidth: true
                focus: true
                placeholderText: i18n("Search applications...")
                Accessible.name: i18n("Search applications")
                onAccepted: root.activateCurrent()
                Keys.onDownPressed: {
                    if (results.enabled && results.count) {
                        results.currentIndex = Math.min(results.currentIndex + 1, results.count - 1);
                    }
                }
                Keys.onUpPressed: {
                    if (results.enabled && results.count) {
                        results.currentIndex = Math.max(results.currentIndex - 1, 0);
                    }
                }
            }

            PC3.ToolButton {
                objectName: "fullMenuButton"
                text: i18n("Full Menu")
                icon.name: "applications-all"
                onClicked: root.fullMenuRequested()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // Reserve the same space for empty, pending, and populated searches.
            implicitHeight: 6 * root.rowHeight

            ListView {
                id: results
                objectName: "applicationResults"
                anchors.fill: parent
                visible: root.query.length > 0 && count > 0
                enabled: root.query.length > 0 && runner.count > 0 && root.resultsReady
                model: runner.count ? runner.modelForRow(0) : null
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: false
                onCountChanged: currentIndex = count > 0 ? 0 : -1
                onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)
                PC3.ScrollBar.vertical: PC3.ScrollBar {}

                delegate: PC3.ItemDelegate {
                    id: result
                    required property int index
                    required property var model
                    width: ListView.view.width
                    height: root.rowHeight
                    text: model.display
                    highlighted: ListView.isCurrentItem
                    focusPolicy: Qt.NoFocus
                    onClicked: {
                        results.currentIndex = index;
                        root.activateCurrent();
                    }

                    contentItem: RowLayout {
                        spacing: Kirigami.Units.smallSpacing * 2
                        Kirigami.Icon {
                            source: result.model.decoration
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            PC3.Label {
                                Layout.fillWidth: true
                                text: result.model.display
                                elide: Text.ElideRight
                            }
                            PC3.Label {
                                Layout.fillWidth: true
                                visible: text.length > 0
                                text: result.model.description
                                elide: Text.ElideRight
                                font: Kirigami.Theme.smallFont
                                opacity: 0.7
                            }
                        }
                    }
                }
            }

            PC3.Label {
                anchors.fill: parent
                visible: root.query.length > 0 && results.count === 0
                text: !runner.count ? i18n("Application search is unavailable")
                    : !root.resultsReady ? i18n("Searching...") : i18n("No matching applications")
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                opacity: 0.7
            }
        }
    }
}
