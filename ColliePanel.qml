import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
  id: root
  moduleName: "overp0werj0int.collie"
  ipcTarget: "overp0werj0int.collie"
  manageIpc: false
  property var state: ({installed: false, healthy: false, serviceState: "checking", url: "", tailnetPublished: false})
  property string message: ""
  property bool messageError: false
  property string currentAction: ""
  readonly property bool busy: actionProc.running
  readonly property string helper: Qt.resolvedUrl("scripts/control.py").toString().replace(/^file:\/\//, "")
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string statusLabel: state.healthy
    ? (state.tailnetPublished ? "Running · tailnet ready" : "Running · tailnet not published")
    : (state.installed ? "Service: " + state.serviceState : "Collie not installed")
  readonly property var actions: [
    {label: "Open Collie", action: "open"},
    {label: "Copy tailnet URL", action: "copy"},
    {label: state.healthy ? "Stop service" : "Start service", action: state.healthy ? "stop" : "start"},
    {label: "Restart service", action: "restart"},
    {label: "Publish tailnet access", action: "serve"},
    {label: "Pair a device", action: "pair"},
    {label: "Diagnostics", action: "doctor"}
  ]

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function commandFor(action) {
    return ["python3", helper, action, "--binary", String(setting("collieBinary", "collie")),
      "--port", String(setting("bridgePort", 8787))]
  }
  function refresh() {
    if (!statusProc.running && !busy) statusProc.running = true
  }
  function act(action) {
    if (busy) return
    currentAction = action
    message = "Working…"
    messageError = false
    actionProc.command = commandFor(action)
    actionProc.running = true
  }
  onOpenedChanged: if (opened) refresh()
  onSettingsChanged: refresh()
  Component.onCompleted: refresh()

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function status(): string { return JSON.stringify({state: root.state, busy: root.busy, message: root.message, error: root.messageError}) }
    function start(): void { root.act("start") }
    function stop(): void { root.act("stop") }
    function restart(): void { root.act("restart") }
    function openBrowser(): void { root.act("open") }
    function copyUrl(): void { root.act("copy") }
    function pairDevice(): void { root.act("pair") }
    function publish(): void { root.act("serve") }
    function diagnostics(): void { root.act("doctor") }
  }

  Timer {
    interval: Math.max(5, Number(root.setting("refreshIntervalSec", 10))) * 1000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }
  Timer {
    id: pairExpiry
    interval: 600000
    onTriggered: if (root.currentAction === "pair") root.message = "Pairing code expired. Create a new one."
  }
  Process {
    id: statusProc
    command: root.commandFor("status")
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.state = JSON.parse(text) }
        catch (error) { root.state = {installed: true, healthy: false, serviceState: "unknown", error: "Could not read status."} }
      }
    }
  }
  Process {
    id: actionProc
    onExited: function(exitCode, exitStatus) {
      if (exitCode !== 0 && root.message === "Working…") {
        root.message = "Action failed; check Collie diagnostics."
        root.messageError = true
      }
      Qt.callLater(root.refresh)
    }
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var answer = JSON.parse(text)
          root.message = answer.message || "Done."
          root.messageError = answer.ok !== true
          if (root.currentAction === "pair" && answer.ok) pairExpiry.restart()
        } catch (error) {
          root.message = "Action did not return a result."
          root.messageError = true
        }
      }
    }
  }

  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰩃"
    dimmed: !root.state.healthy
    tooltipText: "Collie · " + root.statusLabel + "\nLeft: controls · Middle: open browser · Right: start/stop"
    iconComponent: Component {
      Item {
        Ui.OpticalGlyph {
          anchors.fill: parent
          text: "󰩃"
          fontFamily: root.fontFamily
          fontSize: Style.bar.iconFont
          color: root.barForeground
        }
        Rectangle {
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          width: Style.space(5)
          height: width
          radius: width / 2
          color: root.state.healthy ? (root.state.tailnetPublished ? Color.accent : Color.urgent) : root.dim
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.act("open")
      else if (buttonCode === Qt.RightButton) root.act(root.state.healthy ? "stop" : "start")
      else root.toggle()
    }
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: content
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(650))

    Item {
      id: content
      anchors.fill: parent
      Keys.onEscapePressed: root.close()
      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        Column {
          id: column
          width: parent.width
          spacing: Style.space(8)
          Text {
            text: "Collie"
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.bold: true
          }
          Text {
            width: parent.width
            text: root.statusLabel + (root.state.version ? "\nv" + root.state.version : "")
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            wrapMode: Text.Wrap
          }
          Text {
            width: parent.width
            text: root.state.url || "Waiting for a tailnet URL…"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WrapAnywhere
          }
          Repeater {
            model: root.actions
            Ui.Button {
              required property var modelData
              width: column.width
              text: modelData.label
              foreground: root.foreground
              fontFamily: root.fontFamily
              leftAlign: true
              focusable: true
              enabled: root.state.installed && !root.busy
                && (!(modelData.action === "open" || modelData.action === "pair") || root.state.healthy)
              opacity: enabled ? 1 : 0.45
              onClicked: root.act(modelData.action)
            }
          }
          Text {
            width: parent.width
            visible: text !== ""
            text: root.message || root.state.error || ""
            textFormat: Text.PlainText
            color: root.messageError ? Color.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WrapAnywhere
          }
        }
      }
    }
  }
}
