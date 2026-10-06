import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "Collie"
import "Collie/IpcOwner.js" as IpcOwner

// An isolated native lab. All service/install actions use fixture_control.py.
ShellRoot {
  IpcHandler {
    target: "labtest"
    function act(action: string): void { lab.act(action) }
    function newPair(): void { lab.newPair() }
    function mode(value: string): void { if (lab.mode !== value) lab.chooseMode(value) }
    function deviceName(value: string): void { lab.deviceName = value }
    function key(text: string): void { lab.shortcut(text) }
    function goBack(): void { lab.goBack() }
    function setup(): void { lab.startSetup() }
    function ownershipProbe(): bool {
      var one = ownerComponent.createObject(window)
      var two = ownerComponent.createObject(window)
      IpcOwner.register(one); IpcOwner.register(two)
      if (one.ipcPrimary || two.ipcPrimary) return false
      IpcOwner.unregister(lab)
      var transferred = one.ipcPrimary && !two.ipcPrimary
      IpcOwner.unregister(one)
      transferred = transferred && two.ipcPrimary
      IpcOwner.unregister(two); IpcOwner.register(lab)
      one.destroy(); two.destroy()
      return transferred && lab.ipcPrimary
    }
    function settingsPort(port: int): void { lab.settings = {bridgePort: port} }
    function orientation(position: string): void { bar.position = position; bar.vertical = position === "left" || position === "right" }
    function expirePair(): void { lab.pairExpiresAt = Date.now() / 1000 - 1 }
    function inspect(): string {
      return JSON.stringify({opened: lab.opened, ready: lab.ready, setupRunning: lab.setupRunning, nextStep: lab.nextStep, busy: lab.busy, mode: lab.mode, pairing: lab.pairing, pairingQr: lab.pairingQr, pairExpired: lab.pairExpired, pairFailed: lab.pairFailed, makingCode: lab.makingCode, qrName: lab.pairQrName, message: lab.feedbackText,
        codeCleared: lab.pairCode === "", qrCleared: lab.pairQr === "", stage: lab.setupStage, error: lab.messageError})
    }
    function capture(path: string): void {
      for (var i = 0; i < lab.data.length; i++) {
        var item = lab.data[i]
        if (item && "anchorItem" in item && "contentItem" in item)
          item.contentItem[0].grabToImage(function(result) { result.saveToFile(path) })
      }
    }
    function focusWalk(): string {
      var items = []
      var first = null
      for (var i = 0; i < lab.data.length; i++) {
        var panel = lab.data[i]
        if (panel && "anchorItem" in panel) first = panel.contentItem[0]
      }
      if (!first) return "missing panel"
      var seen = []
      var next = first.nextItemInFocusChain(true)
      for (var j = 0; j < 100 && next && next !== first; j++) {
        if (seen.indexOf(next) >= 0) break
        seen.push(next)
        if (next.activeFocusOnTab && next.visible && next.enabled && "text" in next) items.push(next.text)
        next = next.nextItemInFocusChain(true)
      }
      return JSON.stringify(items)
    }
  }
  Component { id: ownerComponent; QtObject { property bool ipcPrimary: false } }
  PanelWindow {
    id: window
    anchors { top: true; right: true }
    implicitWidth: 70
    implicitHeight: 48
    color: Color.background
    QtObject {
      id: bar
      property string position: "top"
      property color foreground: Color.foreground
      property color barForeground: Color.foreground
      property color urgent: Color.urgent
      property string fontFamily: Style.font.family
      property int barSize: 48
      property bool vertical: false
      property bool foregroundAnimationEnabled: false
      property var activePopout: null
      function hideTooltip(item) {}
      function showTooltip(item, text) {}
      function requestPopout(item) { activePopout = item }
      function releasePopout(item) { activePopout = null }
    }
    ColliePanel { id: lab; anchors.centerIn: parent; bar: bar }
    Timer { interval: 800; running: true; onTriggered: lab.open() }
  }
}
