import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui
import "IpcOwner.js" as IpcOwner

Ui.Panel {
  id: root
  moduleName: "overp0werj0int.collie"
  ipcTarget: "overp0werj0int.collie"
  manageIpc: false
  property bool ipcPrimary: false
  property double lastIpcActionAt: 0
  property var state: ({installed: false, healthy: false, serviceState: "checking", url: "", version: "", error: "", tailnetPublished: false, tailscaleReady: false, tailscaleInstalled: false, qrAvailable: false, muxes: [], missingTools: []})
  property bool checked: false
  property string message: ""
  property bool messageError: false
  property string currentAction: ""
  property int requestRevision: 0
  property int actionRevision: 0
  property string actionBaseUrl: ""
  readonly property string collieExecutable: String(setting("collieBinary", "collie"))
  readonly property int bridgePort: Math.min(65535, Math.max(1, Number(setting("bridgePort", 8787)) || 8787))
  readonly property int pollSeconds: Math.min(120, Math.max(5, Number(setting("refreshIntervalSec", 10)) || 10))
  readonly property string requestIdentity: JSON.stringify([collieExecutable, bridgePort, requestRevision])
  property bool actionAnswered: false
  property int setupStage: -1
  property string selectedMux: "herdr"
  property string qr: ""
  property string qrUrl: ""
  property string qrError: ""
  // Connect: nothing is made until a way in is chosen. "watch" shows the plain link,
  // "control" a pairing link with the code (and the device name) filled in.
  property string mode: ""
  property string deviceName: ""
  property bool pairFailed: false
  property string pairError: ""
  property bool pairExpired: false
  property int pairRetries: 0
  property string pendingAction: ""
  property string pendingName: ""
  // The device that used the code on screen, once Collie lists it.
  property string pairedLabel: ""
  property string revokeArmed: ""
  property int statusFailures: 0
  property string pairCode: ""
  property string pairQr: ""
  property string pairQrName: ""
  property string pairBaseUrl: ""
  property double pairExpiresAt: 0
  property double pairIssuedAt: 0
  property double now: Date.now() / 1000
  property double actionStartedAt: 0
  property bool showDetails: false
  property bool copied: false

  // Guided setup: one request walks every remaining step, stopping at the first failure.
  property bool setupRunning: false
  property var setupTried: ({})
  property string setupStep: ""
  property string failedStep: ""
  property bool continueAfterStatus: false
  property bool awaitingTailscale: false
  property double awaitStartedAt: 0

  readonly property bool busy: actionProc.running
  readonly property bool feedbackError: messageError && !busy
  // Collie's own warnings only matter while it is not ready; then they explain why.
  readonly property string feedbackText: message
    || (statusFailures >= 2 ? "Can’t read Collie’s status right now. Retrying."
    : checked && !ready && state.installed && state.error ? state.error : "")
  readonly property bool ready: state.healthy && state.tailnetPublished
  readonly property bool reachableUrl: state.url && !/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])([:/]|$)/.test(state.url)
  readonly property bool pairing: pairCode !== "" && pairExpiresAt > now
  readonly property int pairSeconds: Math.max(0, Math.ceil(pairExpiresAt - now))
  readonly property bool pairingQr: pairing && pairQr !== ""
  readonly property bool makingCode: pairProc.running
  readonly property string timerText: Math.floor(pairSeconds / 60) + ":" + ("0" + pairSeconds % 60).slice(-2)
  // Collie gates writes only once a device is paired; until then a plain link can type too.
  readonly property bool writesGated: state.pairedDevices !== 0
  readonly property bool canOpenHere: state.healthy && !!state.url
  readonly property string helper: Qt.resolvedUrl("scripts/control.py").toString().replace(/^file:\/\//, "")
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.alpha(foreground, 0.62)
  readonly property color outline: Qt.alpha(foreground, 0.12)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var muxes: state.muxes || []
  readonly property string urlHost: { var m = /^https?:\/\/([^/]+)/.exec(state.url || ""); return m ? m[1] : "" }
  readonly property bool bridgeOn: busy && (currentAction === "start" || currentAction === "restart") ? true
    : busy && currentAction === "stop" ? false : state.healthy

  readonly property var neededPackages: {
    var list = state.tailscaleInstalled ? [] : ["tailscale"]
    if (!state.installed) {
      if (!muxes.length) list.push(selectedMux)
      if (!state.qrAvailable) list.push("qrencode")
      list = list.concat(state.missingTools || [])
    }
    return list
  }
  readonly property var stepOrder: ["packages", "tailscale", "bridge", "route"]
  readonly property var stepDone: ({
    packages: checked && neededPackages.length === 0,
    tailscale: !!state.tailscaleReady,
    bridge: state.installed && state.healthy,
    route: !!state.tailnetPublished
  })
  readonly property string nextStep: {
    for (var i = 0; i < stepOrder.length; i++) if (!stepDone[stepOrder[i]]) return stepOrder[i]
    return ""
  }
  readonly property string activeStep: awaitingTailscale ? "tailscale"
    : !busy ? ""
    : currentAction === "install-deps" ? "packages"
    : currentAction === "tailscale-setup" ? "tailscale"
    : currentAction === "setup" ? "bridge"
    : currentAction === "start" || currentAction === "restart" ? "bridge"
    : currentAction === "serve" ? "route" : ""
  readonly property string primaryLabel: setupRunning || busy && activeStep !== "" ? "Setting up…"
    : !state.installed ? (failedStep ? "Try setup again" : "Set up Collie")
    : nextStep === "packages" ? "Install Tailscale"
    : nextStep === "tailscale" ? "Connect Tailscale"
    : nextStep === "bridge" ? "Start bridge"
    : "Publish to tailnet"

  readonly property string elapsedText: busy && now - actionStartedAt >= 3 ? "  " + Math.floor(now - actionStartedAt) + " s" : ""
  readonly property string statusLabel: !checked ? "Checking this machine"
    : setupRunning ? "Setting up"
    : ready ? "Ready for your phone"
    : state.healthy ? "Online, not published"
    : state.installed ? (state.serviceState === "failed" ? "Bridge failed" : "Bridge stopped")
    : "Not set up"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  component LabText: Text {
    width: parent ? parent.width : implicitWidth
    color: root.foreground
    textFormat: Text.PlainText
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    wrapMode: Text.Wrap
  }
  component Caption: LabText {
    color: root.dim
    font.pixelSize: Style.font.bodySmall
  }
  component LabButton: Ui.Button {
    foreground: root.foreground
    fontFamily: root.fontFamily
    focusable: true
    bordered: true
    opacity: enabled ? 1 : 0.4
    onActiveFocusChanged: if (activeFocus && visible) root.reveal(this)
  }
  component Primary: LabButton {
    width: parent.width
    foreground: Color.accent
    selected: true
    fontSize: Style.font.body
  }
  component Section: Ui.PanelSectionHeader {
    foreground: root.foreground
    fontFamily: root.fontFamily
  }
  component Rule: Ui.PanelSeparator { foreground: root.foreground }

  // One Tab stop; h/l or arrows walk the chips, Enter/Space chooses.
  component Segmented: Item {
    id: seg
    property var options: []
    property string value: ""
    property int cursor: -1
    signal chosen(string value)
    width: parent.width
    implicitHeight: segRow.implicitHeight
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    onActiveFocusChanged: {
      if (!activeFocus) { cursor = -1; return }
      for (var i = 0; i < options.length; i++) if (options[i].value === value) cursor = i
      if (cursor < 0) cursor = 0
      root.reveal(seg)
    }
    function step(delta) {
      for (var i = cursor + delta; i >= 0 && i < options.length; i += delta)
        if (options[i].enabled !== false) { cursor = i; return }
    }
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Left || event.text === "h") { step(-1); event.accepted = true }
      else if (event.key === Qt.Key_Right || event.text === "l") { step(1); event.accepted = true }
      else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
        if (cursor >= 0) chosen(options[cursor].value)
        event.accepted = true
      }
    }
    Row {
      id: segRow
      width: parent.width
      spacing: Style.space(6)
      Repeater {
        model: seg.options
        Ui.Button {
          required property var modelData
          required property int index
          width: (seg.width - segRow.spacing * (seg.options.length - 1)) / seg.options.length
          text: modelData.label
          iconText: modelData.icon || ""
          tooltipText: modelData.tooltip || ""
          foreground: root.foreground
          fontFamily: root.fontFamily
          bordered: true
          selected: seg.value === modelData.value
          hasCursor: seg.activeFocus && seg.cursor === index
          enabled: modelData.enabled !== false
          opacity: enabled ? 1 : 0.4
          Accessible.role: Accessible.PageTab
          onClicked: seg.chosen(modelData.value)
        }
      }
    }
  }

  // A way in: icon and name on one line, what it allows below. Same states as the kit's Button.
  component ChoiceTile: Ui.BorderSurface {
    id: tile
    property string icon: ""
    property string title: ""
    property string detail: ""
    property bool selected: false
    property bool hasCursor: false
    property bool focusable: false
    readonly property string text: title
    signal clicked()
    readonly property bool hot: tileMouse.containsMouse || hasCursor || focusable && activeFocus
    implicitHeight: tileText.implicitHeight + Style.space(10) * 2
    radius: Style.cornerRadius
    activeFocusOnTab: focusable
    Accessible.role: Accessible.Button
    Accessible.name: title + ". " + detail
    Keys.onReturnPressed: if (focusable) clicked()
    Keys.onEnterPressed: if (focusable) clicked()
    Keys.onSpacePressed: if (focusable) clicked()
    onActiveFocusChanged: if (activeFocus) root.reveal(tile)
    // Drawn here rather than from control tokens: some themes give controls no border at rest
    // or in focus, and a tile must read as pressable and show the keyboard cursor in every theme.
    readonly property bool cursorOn: hasCursor || focusable && activeFocus
    color: tileMouse.pressed ? Style.pressedFillFor(root.foreground, Color.accent)
      : selected ? Style.selectedFillFor(root.foreground, Color.accent)
      : hot ? Style.hoverFillFor(root.foreground, Color.accent)
      : Qt.alpha(root.foreground, 0.04)
    borderSpec: cursorOn ? Border.flat(Color.accent, 2)
      : selected ? Border.flat(Color.accent, 1)
      : Border.flat(Qt.alpha(root.foreground, hot ? 0.24 : 0.1), 1)
    Behavior on color { ColorAnimation { duration: 120 } }
    Column {
      id: tileText
      x: Style.space(12)
      y: Style.space(10)
      width: parent.width - Style.space(24)
      spacing: Style.space(3)
      Row {
        spacing: Style.space(7)
        Text {
          text: tile.icon
          color: tile.selected ? Color.accent : root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.title
          anchors.verticalCenter: parent.verticalCenter
        }
        Text {
          text: tile.title
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
          anchors.verticalCenter: parent.verticalCenter
        }
      }
      Caption { text: tile.detail }
    }
    Text {
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(9)
      visible: tile.selected
      text: "󰄬"
      color: Color.accent
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      Accessible.ignored: true
    }
    MouseArea {
      id: tileMouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: tile.clicked()
    }
  }

  // Watch only | Full control: one Tab stop, h/l or arrows move, Enter/Space choose.
  component ModePicker: Item {
    id: picker
    readonly property string text: "Choose how to connect"
    property int cursor: -1
    width: parent.width
    implicitHeight: Math.max(watchTile.implicitHeight, controlTile.implicitHeight)
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    Accessible.name: text
    onActiveFocusChanged: {
      cursor = !activeFocus ? -1 : root.mode === "watch" ? 0 : 1
      if (activeFocus) root.reveal(picker)
    }
    // A choice made by shortcut moves the cursor along with it.
    Connections {
      target: root
      function onModeChanged() { if (picker.activeFocus && root.mode !== "") picker.cursor = root.mode === "watch" ? 0 : 1 }
    }
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Left || event.text === "h") { cursor = 0; event.accepted = true }
      else if (event.key === Qt.Key_Right || event.text === "l") { cursor = 1; event.accepted = true }
      else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
        root.chooseMode(cursor === 0 ? "watch" : "control")
        event.accepted = true
      }
    }
    Row {
      spacing: Style.space(8)
      ChoiceTile {
        id: watchTile
        width: (picker.width - parent.spacing) / 2
        height: picker.height
        icon: "󰈈"
        title: "Watch only"
        detail: root.writesGated ? "Follow sessions live. No typing or approving." : "Follow sessions live. Read-only once a device is paired."
        selected: root.mode === "watch"
        hasCursor: picker.activeFocus && picker.cursor === 0
        onClicked: { picker.forceActiveFocus(); picker.cursor = 0; root.chooseMode("watch") }
      }
      ChoiceTile {
        id: controlTile
        width: (picker.width - parent.spacing) / 2
        height: picker.height
        icon: "󰌌"
        title: "Full control"
        detail: "Type, answer and approve. Pairs the device."
        selected: root.mode === "control"
        hasCursor: picker.activeFocus && picker.cursor === 1
        onClicked: { picker.forceActiveFocus(); picker.cursor = 1; root.chooseMode("control") }
      }
    }
  }

  // A QR drawn at whole pixels per module, on white, or a short note while there is none.
  component QrBox: Rectangle {
    id: box
    property string source: ""
    property string label: ""
    property string emptyTitle: ""
    property string emptyDetail: ""
    property bool spinning: false
    default property alias actions: emptyColumn.data
    readonly property int modules: qrImage.sourceSize.width > 0 ? Math.round(qrImage.sourceSize.width / 8) : 0
    width: Style.space(176)
    height: width
    radius: Math.max(Style.space(6), Style.cornerRadius)
    color: qrImage.visible ? "white" : "transparent"
    border.width: qrImage.visible ? 0 : 1
    border.color: root.outline
    Image {
      id: qrImage
      anchors.centerIn: parent
      width: box.modules ? box.modules * Math.max(1, Math.floor((box.width - Style.space(4)) / box.modules)) : box.width - Style.space(8)
      height: width
      source: box.source
      visible: box.source !== "" && status === Image.Ready
      fillMode: Image.PreserveAspectFit
      smooth: false
      cache: false
      Accessible.role: Accessible.Graphic
      Accessible.name: box.label
    }
    Column {
      id: emptyColumn
      anchors.centerIn: parent
      width: parent.width - Style.space(24)
      spacing: Style.space(6)
      visible: !qrImage.visible
      Text {
        id: boxSpinner
        anchors.horizontalCenter: parent.horizontalCenter
        visible: box.spinning
        text: "󰑐"
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        RotationAnimator on rotation {
          running: boxSpinner.visible && emptyColumn.visible
          from: 0; to: 360; duration: 1100; loops: Animation.Infinite
        }
      }
      LabText {
        visible: text !== ""
        horizontalAlignment: Text.AlignHCenter
        font.pixelSize: Style.font.bodySmall
        font.bold: true
        text: box.emptyTitle
      }
      Caption {
        visible: text !== ""
        horizontalAlignment: Text.AlignHCenter
        font.pixelSize: Style.font.caption
        text: box.emptyDetail
        maximumLineCount: 6
        elide: Text.ElideRight
      }
    }
  }

  component StepRow: Item {
    id: stepRow
    property string key: ""
    property string title: ""
    property string detail: ""
    readonly property bool done: !!root.stepDone[key]
    readonly property bool active: root.activeStep === key
    readonly property bool failed: !active && root.failedStep === key && root.messageError
    width: parent.width
    implicitHeight: Math.max(stepGlyph.implicitHeight, stepText.implicitHeight)
    Accessible.role: Accessible.ListItem
    Accessible.name: title + ", " + (done ? "done" : active ? "in progress" : failed ? "failed" : "to do") + ". " + detail
    Text {
      id: stepGlyph
      width: Style.space(20)
      horizontalAlignment: Text.AlignHCenter
      text: stepRow.active ? "󰑐" : stepRow.done ? "󰄬" : stepRow.failed ? "󰀦" : "󰝦"
      color: stepRow.failed ? Color.urgent : stepRow.done || stepRow.active ? Color.accent : Qt.alpha(root.foreground, 0.35)
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      RotationAnimator on rotation {
        running: stepRow.active
        from: 0; to: 360; duration: 1100; loops: Animation.Infinite
        onRunningChanged: if (!running) stepGlyph.rotation = 0
      }
      Accessible.ignored: true
    }
    Column {
      id: stepText
      x: Style.space(30)
      width: parent.width - x
      spacing: Style.space(1)
      LabText {
        text: stepRow.title
        opacity: stepRow.done && !stepRow.active ? 0.7 : 1
        font.bold: stepRow.active || !stepRow.done && root.nextStep === stepRow.key
      }
      Caption {
        text: stepRow.active && root.busy && root.message ? root.message + root.elapsedText
          : stepRow.failed ? "Did not finish. The reason is shown above." : stepRow.detail
        color: stepRow.failed ? Color.urgent : root.dim
      }
    }
  }

  component KeyHint: Row {
    property string cap: ""
    property string verb: ""
    spacing: Style.space(5)
    Rectangle {
      width: Math.max(height, capText.implicitWidth + Style.space(8))
      height: capText.implicitHeight + Style.space(2)
      radius: Math.min(Style.cornerRadius, height / 3)
      color: "transparent"
      border.width: 1
      border.color: Qt.alpha(root.foreground, 0.25)
      anchors.verticalCenter: parent.verticalCenter
      Text {
        id: capText
        anchors.centerIn: parent
        text: parent.parent.cap
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      text: parent.verb
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  function commandFor(action, name) {
    var argv = ["/usr/bin/python3", "-I", helper, action, "--binary", collieExecutable,
      "--port", String(bridgePort), "--mux", selectedMux]
    return name ? argv.concat(["--name", name]) : argv
  }
  function reveal(item) {
    if (!item || !scroll.visible) return
    var position = item.mapToItem(scroll.contentItem, 0, 0)
    var limit = Math.max(0, scroll.contentHeight - scroll.height)
    if (item.height > scroll.height || position.y < scroll.contentY)
      scroll.contentY = Math.min(limit, Math.max(0, position.y - Style.space(8)))
    else if (position.y + item.height > scroll.contentY + scroll.height)
      scroll.contentY = Math.min(limit, position.y + item.height - scroll.height + Style.space(8))
  }
  function refresh() {
    if (!statusProc.running && !busy) statusProc.running = true
  }
  function clearPair() {
    pairCode = ""
    pairQr = ""
    pairQrName = ""
    pairExpiresAt = 0
    pairIssuedAt = 0
    pairBaseUrl = ""
  }
  // A code exists only while Full control is chosen; an expired one waits for "New code".
  function ensurePair() {
    if (mode !== "control" || pairing || pairFailed || pairExpired || pairedLabel) return
    requestPair()
  }
  function requestPair() {
    if (pairProc.running || busy || !opened || !ready || !reachableUrl || !state.qrAvailable) return
    pairFailed = false
    pairProc.baseUrl = state.url
    pairProc.name = deviceName.trim()
    pairProc.command = commandFor("pair", pairProc.name)
    pairProc.running = true
  }
  function newPair() {
    clearPair()
    pairError = ""
    pairedLabel = ""
    pairRetries = 0
    pairFailed = false
    pairExpired = false
    if (mode !== "control") mode = "control"
    requestPair()
  }
  function receivePair(text) {
    try {
      // A late code must never appear after closing, a settings change or a URL change.
      if (pairProc.identity !== requestIdentity || !opened || !ready || pairProc.baseUrl !== state.url) return
      var lines = text.trim().split("\n")
      var answer = JSON.parse(lines[lines.length - 1])
      if (answer.ok && answer.qr && answer.pairCode) {
        pairCode = answer.pairCode
        pairQr = answer.qr
        pairQrName = pairProc.name
        pairBaseUrl = state.url
        pairIssuedAt = Date.now() / 1000
        pairExpiresAt = Math.min(Number(answer.expiresAt) || 0, pairIssuedAt + 600)
        now = pairIssuedAt
        pairRetries = 0
        pairExpired = false
        // The name changed while the code was being made: draw it in.
        if (deviceName.trim() !== pairQrName) nameSettle.restart()
      } else {
        // The helper's messages never carry the code: say why, instead of a bare failure.
        pairError = String(answer.message || "")
        pairMissed()
      }
    } catch (error) { pairMissed() }
  }
  // Same code, new name: only the picture changes, the countdown keeps running.
  function redrawPair() {
    var name = deviceName.trim()
    if (!pairing || name === pairQrName) return
    if (pairQrProc.running) { nameSettle.restart(); return }
    pairQrProc.code = pairCode
    pairQrProc.name = name
    pairQrProc.environment = ({COLLIE_LAB_PAIR_CODE: pairCode})
    pairQrProc.command = commandFor("pair-qr", name)
    pairQrProc.running = true
  }
  function seen(at) {
    if (!at) return "not seen since pairing"
    var ago = Math.max(0, Date.now() / 1000 - at)
    if (ago < 90) return "seen just now"
    if (ago < 3600) return "seen " + Math.round(ago / 60) + " min ago"
    if (ago < 86400) return "seen " + Math.round(ago / 3600) + " h ago"
    return "seen " + new Date(at * 1000).toLocaleDateString(Qt.locale(), "MMM d")
  }
  function chooseMode(value) {
    mode = mode === value ? "" : value
    if (mode === "control") { pairedLabel = ""; ensurePair() }
    else if (mode === "watch") loadQr(false)
  }
  function focusDefault() {
    if (!opened) return
    if (ready) modePicker.forceActiveFocus()
    else if (primaryButton.visible) primaryButton.forceActiveFocus()
  }
  // Esc leaves the innermost thing first: the name field, then the chosen way in, then the panel.
  function goBack() {
    if (revokeArmed) revokeArmed = ""
    else if (nameField.activeFocus) modePicker.forceActiveFocus()
    else if (mode !== "") { mode = ""; if (ready) modePicker.forceActiveFocus() }
    else close()
  }
  // One quiet retry covers a busy backend lock; after that the plain code stays.
  function pairMissed() {
    if (pairRetries < 1) { pairRetries++; pairRetry.restart() }
    else pairFailed = true
  }
  function loadQr(force) {
    if (qrProc.running || !ready || !reachableUrl || !state.qrAvailable) return
    if (!force && qrUrl === state.url) return
    qrUrl = state.url
    qrError = ""
    qrProc.command = commandFor("qr")
    qrProc.running = true
  }
  function applyState(answer) {
    if (!answer || typeof answer !== "object" || Array.isArray(answer)
        || typeof answer.healthy !== "boolean" || typeof answer.tailnetPublished !== "boolean"
        || typeof answer.installed !== "boolean" || typeof answer.url !== "string")
      throw new Error("Invalid status")
    if (state.url !== answer.url || !answer.healthy || !answer.tailnetPublished) {
      qr = ""
      qrUrl = ""
      if (pairBaseUrl !== answer.url || !answer.healthy || !answer.tailnetPublished) clearPair()
    }
    // A device enrolled after this code was made used it: show that, the code is spent.
    if (pairing && Array.isArray(answer.devices)) {
      var known = (state.devices || []).map(function(d) { return d.label })
      for (var i = 0; i < answer.devices.length; i++) {
        var d = answer.devices[i]
        if (known.indexOf(d.label) < 0 && Number(d.created) >= pairIssuedAt - 5) {
          clearPair()
          pairedLabel = String(d.label)
          break
        }
      }
    }
    state = answer
    checked = true
    // Keep a choice the user may still install when nothing is available yet.
    if (muxes.length && muxes.indexOf(selectedMux) < 0) selectedMux = muxes[0]
    if (awaitingTailscale && answer.tailscaleReady) {
      awaitingTailscale = false
      Qt.callLater(root.continueSetup)
    }
    statusFailures = 0
    Qt.callLater(function() { root.loadQr(false); root.ensurePair() })
  }

  function startSetup() {
    if (busy) return
    setupTried = ({})
    failedStep = ""
    showDetails = false
    continueSetup()
  }
  function continueSetup() {
    if (busy) return
    var step = nextStep
    if (!step) {
      if (setupRunning) { message = "You’re set. Choose how to connect."; messageError = false; quietMessage.restart() }
      setupRunning = false
      setupStep = ""
      return
    }
    if (setupTried[step]) {
      // The same step did not complete: stop here and leave its error visible.
      setupRunning = false
      failedStep = step
      if (!messageError) { message = "Setup stopped before finishing. Try again or run diagnostics."; messageError = true }
      return
    }
    var tried = Object.assign({}, setupTried); tried[step] = true; setupTried = tried
    setupRunning = true
    setupStep = step
    if (step === "packages") act("install-deps")
    else if (step === "tailscale") {
      awaitingTailscale = true
      awaitStartedAt = Date.now() / 1000
      act("tailscale-setup")
    }
    else if (step === "bridge") act(state.installed ? "start" : "setup")
    else act("serve")
  }
  function cancelWaiting() {
    awaitingTailscale = false
    setupRunning = false
    message = ""
  }

  readonly property var actionMessages: ({
    "install-deps": "Installing " + neededPackages.join(", ") + "…",
    "install-qr": "Installing the QR tool…",
    "tailscale-setup": "Opening Tailscale sign-in…",
    "setup": "Checking this machine…",
    "start": "Starting the bridge…",
    "stop": "Stopping the bridge…",
    "restart": "Restarting the bridge…",
    "serve": "Publishing to your tailnet…",
    "doctor": "Running diagnostics…",
    "open": "Opening Collie…",
    "copy": "Copying the address…",
    "revoke": "Revoking…"
  })
  function act(action, name) {
    if (busy) return
    // Pairing holds the backend lock for a moment; run the action right after it.
    if (pairProc.running) { pendingAction = action; pendingName = name || ""; return }
    if (action === "setup") setupStage = 0
    if (action !== "doctor") showDetails = false
    quietMessage.stop()
    requestRevision++
    if (qrProc.running) qrUrl = ""
    actionRevision = requestRevision
    actionBaseUrl = state.url
    currentAction = action
    actionStartedAt = Date.now() / 1000
    now = actionStartedAt
    actionAnswered = false
    message = actionMessages[action] || "Working…"
    messageError = false
    actionProc.command = commandFor(action, name)
    actionProc.running = true
  }
  function receiveAction(line) {
    try {
      if (actionRevision !== requestRevision) return
      var answer = JSON.parse(line)
      if (answer.event === "progress") {
        setupStage = answer.stage
        message = answer.message
        return
      }
      actionAnswered = true
      message = answer.message || "Done."
      messageError = answer.ok !== true
      if (answer.state) applyState(answer.state)
      if (messageError && setupRunning && !awaitingTailscale) failedStep = setupStep
      else if (messageError && currentAction === "setup") failedStep = "bridge"
      if (!messageError) {
        if (currentAction === "copy") { copied = true; copiedReset.restart(); message = "" }
        else if (currentAction === "open") { message = ""; root.close() }
        else if (currentAction === "setup") setupStage = 5
        // Success is normally true: let it fade instead of staying on screen.
        if (currentAction !== "doctor" && message) quietMessage.restart()
      }
      if (messageError || currentAction === "doctor") revealFeedback.restart()
    } catch (error) {
      message = "Could not read the action result. Try again or run diagnostics."
      messageError = true
    }
  }
  function retry() {
    if (!message && state.error) refresh()
    else if (failedStep || setupRunning) startSetup()
    else act(currentAction || "doctor")
  }
  function shortcut(text) {
    var t = text.toLowerCase()
    if (t === "o" && canOpenHere) act("open")
    else if (t === "w" && ready) chooseMode("watch")
    else if (t === "f" && ready) chooseMode("control")
    else if (t === "n" && mode === "control" && ready && state.qrAvailable && !pairProc.running) newPair()
    else if (t === "c" && mode === "watch" && ready) act("copy")
    else if (t === "s" && state.installed) act(state.healthy ? "stop" : "start")
    else if (t === "r" && state.installed) act("restart")
    else if (t === "d" && state.installed) { showDetails = true; act("doctor") }
    else return false
    return true
  }

  onOpenedChanged: {
    if (opened) {
      // Every visit starts at the choice: nothing is minted until one is made.
      mode = ""
      deviceName = ""
      pairRetries = 0
      pairFailed = false
      pairExpired = false
      pairedLabel = ""
      revokeArmed = ""
      refresh()
      Qt.callLater(function() { scroll.contentY = 0; root.focusDefault() })
    } else {
      clearPair(); revealFeedback.stop(); nameSettle.stop()
      mode = ""
      showDetails = false
      // An old failure is no help next time; setup failures stay with their step.
      if (!busy && !failedStep) { message = ""; messageError = false }
    }
  }
  onSettingsChanged: {
    requestRevision++
    clearPair(); qr = ""; qrUrl = ""
    Qt.callLater(function() {
      root.state = Object.assign({}, root.state, {healthy: false, tailnetPublished: false, url: ""})
      root.checked = false
      root.refresh()
    })
  }
  onReadyChanged: if (opened) Qt.callLater(focusDefault)
  onDeviceNameChanged: if (pairing) nameSettle.restart()
  Component.onCompleted: { IpcOwner.register(root); refresh() }
  Component.onDestruction: IpcOwner.unregister(root)

  function ipcAct(action) {
    var timestamp = Date.now()
    if (timestamp - lastIpcActionAt < 1000) return
    lastIpcActionAt = timestamp
    if (action === "setup") startSetup()
    else act(action)
  }

  IpcHandler {
    enabled: root.ipcPrimary
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    // Never includes the pairing code or QR image.
    function status(): string { return JSON.stringify({state: root.state, busy: root.busy, error: root.messageError, message: root.feedbackText.slice(0, 500), setupRunning: root.setupRunning, nextStep: root.nextStep, mode: root.mode, pairing: root.pairing, pairExpired: root.pairExpired}) }
    function setup(): void { root.open(); root.ipcAct("setup") }
    function start(): void { root.ipcAct("start") }
    function stop(): void { root.ipcAct("stop") }
    function restart(): void { root.ipcAct("restart") }
    function openBrowser(): void { root.ipcAct("open") }
    function copyUrl(): void { root.ipcAct("copy") }
    function pairDevice(): void { root.open(); root.newPair() }
    function publish(): void { root.ipcAct("serve") }
    function diagnostics(): void { root.showDetails = true; root.ipcAct("doctor") }
  }
  Timer {
    id: revealFeedback
    interval: 60
    onTriggered: root.reveal(feedback)
  }
  Timer {
    id: quietMessage
    interval: 4000
    onTriggered: if (!root.busy && !root.messageError) root.message = ""
  }
  Timer {
    id: revokeDisarm
    interval: 4000
    onTriggered: root.revokeArmed = ""
  }
  Timer {
    // Redraw once typing settles, not on every key.
    id: nameSettle
    interval: 450
    onTriggered: root.redrawPair()
  }
  Timer {
    id: pairRetry
    interval: 1500
    onTriggered: root.requestPair()
  }
  Timer {
    id: copiedReset
    interval: 1600
    onTriggered: root.copied = false
  }
  Timer {
    // While a code is on screen, check often so a new device shows up as soon as it pairs.
    interval: root.pairing ? 3000 : root.pollSeconds * 1000
    running: !root.awaitingTailscale
    repeat: true
    onTriggered: root.refresh()
  }
  Timer {
    // Pick up Tailscale sign-in from the terminal quickly, for ten minutes at most.
    interval: 2000
    running: root.awaitingTailscale
    repeat: true
    onTriggered: {
      if (Date.now() / 1000 - root.awaitStartedAt > 600) {
        root.cancelWaiting()
        root.message = "Tailscale is still not connected. Continue setup after signing in."
        root.messageError = true
        root.failedStep = "tailscale"
      } else root.refresh()
    }
  }
  Timer {
    interval: 1000
    running: root.pairCode !== "" || root.busy
    repeat: true
    onTriggered: {
      root.now = Date.now() / 1000
      if (root.pairCode !== "" && root.pairExpiresAt <= root.now) {
        root.clearPair()
        root.pairExpired = true
      }
    }
  }
  Process {
    id: statusProc
    property string identity: ""
    onRunningChanged: if (running) identity = root.requestIdentity
    onExited: if (root.continueAfterStatus) Qt.callLater(root.refresh)
    command: root.commandFor("status")
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          if (root.busy || statusProc.identity !== root.requestIdentity) return
          root.applyState(JSON.parse(text))
          if (root.continueAfterStatus) {
            root.continueAfterStatus = false
            Qt.callLater(root.continueSetup)
          }
        } catch (error) { root.checked = true; root.statusFailures++ }
      }
    }
  }
  Process {
    id: qrProc
    property string identity: ""
    onRunningChanged: if (running) identity = root.requestIdentity
    onExited: Qt.callLater(function() {
      if (qrProc.identity !== root.requestIdentity) root.qrUrl = ""
      root.loadQr(false)
    })
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          if (qrProc.identity !== root.requestIdentity) return
          var answer = JSON.parse(text)
          // A late QR result must never replace a newer URL or a stopped service.
          if (answer.ok && answer.url === root.state.url && root.ready) root.qr = answer.qr
          else root.qrError = answer.message || "Could not make the QR code."
        } catch (error) { root.qrError = "Could not make the QR code." }
      }
    }
  }
  Process {
    id: pairProc
    property string identity: ""
    property string baseUrl: ""
    property string name: ""
    onRunningChanged: if (running) identity = root.requestIdentity
    onExited: {
      if (!root.pendingAction) return
      var queued = root.pendingAction, queuedName = root.pendingName
      root.pendingAction = ""
      root.pendingName = ""
      Qt.callLater(function() { root.act(queued, queuedName) })
    }
    stdout: StdioCollector { onStreamFinished: root.receivePair(text) }
  }
  Process {
    id: pairQrProc
    property string code: ""
    property string name: ""
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var answer = JSON.parse(text)
          // Only the code on screen, and only the name still typed, may replace the picture.
          if (answer.ok && answer.qr && pairQrProc.code === root.pairCode && root.pairing) {
            root.pairQr = answer.qr
            root.pairQrName = pairQrProc.name
            if (root.deviceName.trim() !== root.pairQrName) nameSettle.restart()
          }
        } catch (error) {}
      }
    }
  }
  Process {
    id: actionProc
    stdout: SplitParser { onRead: data => root.receiveAction(data) }
    onExited: function(exitCode, exitStatus) {
      if (!root.actionAnswered && root.actionRevision === root.requestRevision) {
        root.message = "The action ended without a result. Try again or run diagnostics."
        root.messageError = true
        if (root.setupRunning) root.failedStep = root.setupStep
      }
      if (root.setupRunning && !root.awaitingTailscale) {
        if (root.messageError) root.setupRunning = false
        else root.continueAfterStatus = true
      }
      Qt.callLater(root.refresh)
    }
  }

  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰩃"
    dimmed: !root.state.healthy
    tooltipText: "Collie · " + root.statusLabel + "\nClick: panel · Middle: open · Right: start or stop"
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
          visible: root.checked && (root.state.installed || root.busy)
          color: root.busy ? root.barForeground : root.ready ? Color.accent : root.state.healthy ? Color.urgent : root.dim
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton && root.state.healthy) root.act("open")
      else if (buttonCode === Qt.RightButton && root.state.installed) root.act(root.state.healthy ? "stop" : "start")
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
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(760))

    FocusScope {
      id: content
      anchors.fill: parent
      Keys.onEscapePressed: root.goBack()
      Keys.onPressed: function(event) {
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return
        if (event.text && event.text.length === 1 && root.shortcut(event.text)) event.accepted = true
      }
      Rectangle { anchors.fill: parent; color: Color.popups.background }
      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: scroll.width
          spacing: Style.space(14)

          Ui.PanelHero {
            id: hero
            width: parent.width
            title: "Collie"
            meta: root.statusLabel
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.state.healthy ? 1 : 0.5
            iconComponent: Component {
              Text {
                text: "󰩃"
                color: root.ready ? Color.accent : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
            trailingControl: Component {
              Ui.ToggleSwitch {
                id: power
                visible: root.state.installed
                checked: root.bridgeOn
                busy: root.busy
                foreground: root.foreground
                hasCursor: activeFocus
                activeFocusOnTab: true
                Accessible.role: Accessible.CheckBox
                Accessible.name: "Collie bridge"
                Accessible.checked: root.bridgeOn
                onToggled: root.act(root.state.healthy ? "stop" : "start")
                Keys.onSpacePressed: if (!root.busy) toggled()
                Keys.onReturnPressed: if (!root.busy) toggled()
                Ui.PanelToolTip {
                  visible: power.containsMouse
                  text: root.state.healthy ? "Stop the bridge · s" : "Start the bridge · s"
                  fontFamily: root.fontFamily
                }
              }
            }
          }

          // Activity and errors sit under the header, as in Omarchy's own panels.
          Column {
            id: feedback
            width: parent.width
            spacing: Style.space(8)
            // While setup runs, the active step carries the progress instead.
            visible: (root.busy || root.feedbackText !== "")
              && !(setupView.visible && root.activeStep !== "" && !root.messageError)
            Row {
              width: parent.width
              spacing: Style.space(8)
              Text {
                id: busyGlyph
                visible: root.busy || root.awaitingTailscale
                text: "󰑐"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                RotationAnimator on rotation {
                  running: busyGlyph.visible
                  from: 0; to: 360; duration: 1100; loops: Animation.Infinite
                }
              }
              Caption {
                width: parent.width - (busyGlyph.visible ? busyGlyph.width + parent.spacing : 0)
                text: root.feedbackText + root.elapsedText
                color: root.feedbackError ? Color.urgent : root.dim
                maximumLineCount: root.showDetails ? 400 : 3
                elide: Text.ElideRight
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
              }
            }
            Row {
              spacing: Style.space(8)
              visible: !root.busy && (root.feedbackError || root.showDetails && root.message !== "")
              // In setup the main button already retries.
              LabButton { visible: root.feedbackError && !setupView.visible; text: "Try again"; onClicked: root.retry() }
              LabButton {
                visible: root.feedbackError || root.showDetails
                text: root.showDetails ? "Less detail" : "Show details"
                bordered: false
                onClicked: root.showDetails = !root.showDetails
              }
              LabButton {
                visible: root.feedbackError && root.state.installed && root.currentAction !== "doctor"
                text: "Diagnostics"; bordered: false
                onClicked: { root.showDetails = true; root.act("doctor") }
              }
            }
            LabButton {
              visible: root.awaitingTailscale
              text: "Stop waiting"; bordered: false
              onClicked: root.cancelWaiting()
            }
          }

          Rule {}

          // Setup and recovery: one list, one button that finishes whatever is left.
          Column {
            id: setupView
            width: parent.width
            spacing: Style.space(12)
            visible: root.checked && !root.ready
            Section { text: root.state.installed ? "GET BACK ONLINE" : "SET UP"; Accessible.name: root.state.installed ? "Get back online" : "Set up" }
            StepRow {
              key: "packages"
              title: "Requirements"
              detail: root.stepDone.packages
                ? (root.muxes.length ? root.muxes.join(", ") : "Tailscale") + (root.state.qrAvailable ? " and QR codes ready" : " ready")
                : "Installs " + root.neededPackages.join(", ") + " with one password prompt"
            }
            Column {
              width: parent.width - x
              x: Style.space(30)
              spacing: Style.space(6)
              visible: !root.state.installed && !root.busy
              Caption { text: root.muxes.length ? "Workspace to mirror" : "Workspace to install and mirror" }
              Segmented {
                value: root.selectedMux
                options: ["herdr", "tmux", "zellij"].map(function(name) {
                  return {value: name, label: name, enabled: !root.muxes.length || root.muxes.indexOf(name) >= 0,
                    tooltip: root.muxes.length && root.muxes.indexOf(name) < 0 ? name + " is not installed" : ""}
                })
                onChosen: function(value) { root.selectedMux = value }
              }
            }
            StepRow {
              key: "tailscale"
              title: "Tailscale"
              detail: root.awaitingTailscale ? "Finish signing in in the terminal. Setup continues by itself."
                : root.state.tailscaleReady ? "Signed in"
                : "Opens a terminal to sign in to your tailnet"
            }
            StepRow {
              key: "bridge"
              title: "Collie bridge"
              detail: root.state.healthy ? "Running" + (root.state.version ? ", version " + root.state.version : "")
                : root.state.installed ? (root.state.serviceState === "failed" ? "The service failed. Start it or run diagnostics." : "Installed and stopped")
                : "Installs the reviewed Collie 1.16.2 in your home folder"
            }
            StepRow {
              key: "route"
              title: "Private address"
              detail: root.state.tailnetPublished ? (root.urlHost || "Published on your tailnet")
                : root.state.healthy && root.failedStep === "route" ? "Turn on HTTPS for your tailnet in the Tailscale admin console, then try again."
                : "Publishes an HTTPS address only your tailnet can reach"
            }
            Primary {
              id: primaryButton
              focus: true
              text: root.primaryLabel
              iconText: root.setupRunning || root.busy && root.activeStep !== "" ? "󰑐" : ""
              iconSpinning: iconText !== ""
              enabled: root.checked && !root.busy && !root.awaitingTailscale
              onClicked: root.startSetup()
            }
          }

          // Connect: two ways in for another device, and this computer in one press.
          Column {
            id: connectView
            width: parent.width
            spacing: Style.space(10)
            visible: root.ready
            Section { text: "CONNECT"; Accessible.name: "Connect" }
            ModePicker { id: modePicker }

            // Watch only: the plain address.
            Row {
              id: watchDetail
              visible: root.mode === "watch"
              width: parent.width
              spacing: Style.space(14)
              QrBox {
                id: watchQr
                source: root.qr
                label: "QR code that opens Collie to watch"
                spinning: root.state.qrAvailable && root.qrError === ""
                emptyTitle: !root.state.qrAvailable ? "QR codes need qrencode" : root.qrError ? "Could not make the QR code" : ""
                emptyDetail: !root.state.qrAvailable ? "Codes are drawn on this computer." : root.qrError
                LabButton {
                  anchors.horizontalCenter: parent.horizontalCenter
                  visible: !root.state.qrAvailable || root.qrError !== ""
                  text: !root.state.qrAvailable ? "Install QR tool" : "Try again"
                  enabled: !root.busy
                  onClicked: if (!root.state.qrAvailable) root.act("install-qr"); else root.loadQr(true)
                }
              }
              Column {
                width: parent.width - watchQr.width - parent.spacing
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(8)
                LabText { text: "Scan with your phone’s camera"; font.bold: true }
                Caption {
                  text: root.writesGated ? "Opens Collie to follow along. Typing needs Full control."
                    : "Nothing is paired yet, so this link can still type."
                }
                Caption { text: root.urlHost; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
                LabButton {
                  text: root.copied ? "Copied" : "Copy link"
                  iconText: root.copied ? "󰄬" : "󰆏"
                  tooltipText: "c"
                  enabled: !root.busy
                  onClicked: root.act("copy")
                }
              }
            }

            // Full control: a pairing link with the code and the device name filled in.
            Row {
              id: controlDetail
              visible: root.mode === "control"
              width: parent.width
              spacing: Style.space(14)
              QrBox {
                id: controlQr
                source: root.pairingQr ? root.pairQr : ""
                label: "QR code that opens Collie with your pairing code filled in"
                spinning: pairProc.running
                emptyTitle: !root.state.qrAvailable ? "QR codes need qrencode"
                  : root.pairedLabel ? "󰄬 Paired"
                  : root.pairExpired ? "Code expired"
                  : root.pairFailed ? "Could not make a code" : ""
                emptyDetail: !root.state.qrAvailable ? "Codes are drawn on this computer."
                  : root.pairedLabel ? root.pairedLabel + " has full control now."
                  : root.pairExpired ? "Make a new one when your phone is ready."
                  : root.pairFailed ? (root.pairError || "Try a new code, or run diagnostics.")
                  : pairProc.running ? "Making your code…" : ""
                LabButton {
                  anchors.horizontalCenter: parent.horizontalCenter
                  visible: !root.state.qrAvailable
                  text: "Install QR tool"
                  enabled: !root.busy
                  onClicked: root.act("install-qr")
                }
              }
              Item {
                id: controlSide
                width: parent.width - controlQr.width - parent.spacing
                height: controlQr.height
                // Timer and code share one size: the largest at which the code still fits the column.
                readonly property int bigSize: Math.max(Style.font.title, Math.min(Math.round(Style.font.display * 1.2),
                  Math.floor(width * 100 / Math.max(1, codeMetrics.advanceWidth))))
                TextMetrics {
                  id: codeMetrics
                  font.family: root.fontFamily
                  font.bold: true
                  font.pixelSize: 100
                  text: root.pairCode.length > 8 ? root.pairCode : "WWWWWWWW"
                }
                Column {
                  width: parent.width
                  spacing: Style.space(4)
                  Text {
                    text: root.pairing ? root.timerText : root.pairExpired ? "0:00" : "–:––"
                    color: root.pairExpired || root.pairing && root.pairSeconds <= 60 ? Color.urgent
                      : root.pairing ? root.foreground : root.dim
                    font.family: root.fontFamily
                    font.pixelSize: controlSide.bigSize
                    font.bold: true
                    Accessible.role: Accessible.StaticText
                    Accessible.name: root.pairing ? "Code expires in " + root.timerText : "No code"
                  }
                  // Time left on the code, as a draining line.
                  Rectangle {
                    width: parent.width
                    height: Style.space(3)
                    radius: height / 2
                    color: root.outline
                    Rectangle {
                      visible: root.pairing
                      height: parent.height
                      radius: parent.radius
                      color: root.pairSeconds <= 60 ? Color.urgent : Color.accent
                      width: parent.width * Math.max(0, Math.min(1, root.pairSeconds / Math.max(1, root.pairExpiresAt - root.pairIssuedAt)))
                    }
                  }
                  Text {
                    width: parent.width
                    text: root.pairing ? root.pairCode : " "
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: controlSide.bigSize
                    font.bold: true
                    Accessible.role: Accessible.StaticText
                    Accessible.name: root.pairing ? "Pairing code " + root.pairCode.split("").join(" ") : ""
                  }
                }
                Column {
                  anchors.bottom: parent.bottom
                  width: parent.width
                  spacing: Style.space(5)
                  Caption { text: "Device name, optional"; font.pixelSize: Style.font.caption }
                  Ui.TextField {
                    id: nameField
                    width: parent.width
                    text: root.deviceName
                    placeholderText: "iPhone, iPad…"
                    maximumLength: 48
                    foreground: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    verticalPadding: Style.space(5)
                    Accessible.name: "Device name, optional"
                    onTextEdited: root.deviceName = text
                    onAccepted: { nameSettle.stop(); root.redrawPair(); modePicker.forceActiveFocus() }
                    onActiveFocusChanged: if (activeFocus) root.reveal(nameField)
                  }
                  LabButton {
                    width: parent.width
                    text: "New code"
                    iconText: "󰑐"
                    iconSpinning: pairProc.running
                    tooltipText: "n"
                    selected: root.pairExpired || root.pairFailed
                    enabled: !root.busy && !pairProc.running && root.state.qrAvailable
                    onClicked: root.newPair()
                  }
                }
              }
            }
            Caption {
              visible: root.mode !== ""
              horizontalAlignment: Text.AlignHCenter
              font.pixelSize: Style.font.caption
              text: (root.mode === "control" ? "Scan with your phone’s camera; the code fills itself in.\n" : "")
                + "Your phone needs Tailscale on, in the same tailnet."
            }

            ChoiceTile {
              id: openHere
              width: parent.width
              focusable: true
              icon: "󰍹"
              title: "Open on this computer"
              detail: !root.writesGated || root.state.thisComputerPaired ? "Collie in its own window, with full control."
                : "Collie in its own window. Pairs this computer once, then goes straight in."
              enabled: !root.busy
              opacity: enabled ? 1 : 0.4
              onClicked: root.act("open")
            }
          }

          Rule { visible: devicesView.visible }

          // Paired devices: what holds full control, and a way to take it back.
          Column {
            id: devicesView
            width: parent.width
            spacing: Style.space(8)
            visible: root.ready && root.state.pairedDevices >= 0
            Section { text: "PAIRED DEVICES"; Accessible.name: "Paired devices" }
            Caption {
              visible: !(root.state.devices || []).length
              text: "None yet, so Collie lets any device type. Full control pairs one."
            }
            Repeater {
              model: root.state.devices || []
              Item {
                id: deviceRow
                required property var modelData
                readonly property bool armed: root.revokeArmed === modelData.label
                width: devicesView.width
                implicitHeight: Math.max(deviceText.implicitHeight, revokeButton.implicitHeight)
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.label + ". " + deviceDetail.text
                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(20)
                  horizontalAlignment: Text.AlignHCenter
                  text: deviceRow.modelData.thisComputer ? "󰍹" : "󰄜"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  Accessible.ignored: true
                }
                Column {
                  id: deviceText
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(30)
                  anchors.right: revokeButton.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(1)
                  LabText { text: deviceRow.modelData.label; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                  Caption {
                    id: deviceDetail
                    font.pixelSize: Style.font.caption
                    color: deviceRow.armed ? Color.urgent : root.dim
                    text: deviceRow.armed
                      ? ((root.state.devices || []).length === 1 ? "Press again. With none paired, any device can type."
                        : deviceRow.modelData.thisComputer ? "Press again. Opening here will pair it again."
                        : "Press again to take away its full control.")
                      : (deviceRow.modelData.thisComputer ? "This computer, " : "") + root.seen(deviceRow.modelData.lastSeen)
                  }
                }
                LabButton {
                  id: revokeButton
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  text: deviceRow.armed ? "Revoke?" : "Revoke"
                  bordered: deviceRow.armed
                  foreground: deviceRow.armed ? Color.urgent : root.foreground
                  enabled: !root.busy
                  Accessible.name: "Revoke " + deviceRow.modelData.label
                  onClicked: {
                    // Destructive: the first press asks in place, the second within a few seconds revokes.
                    if (deviceRow.armed) { root.revokeArmed = ""; root.act("revoke", deviceRow.modelData.label) }
                    else { root.revokeArmed = deviceRow.modelData.label; revokeDisarm.restart() }
                  }
                }
              }
            }
          }

          Rule { visible: root.state.installed }

          // The installed bridge: version, and the quiet maintenance actions.
          Item {
            width: parent.width
            height: Math.max(bridgeInfo.implicitHeight, bridgeActions.implicitHeight)
            visible: root.state.installed
            Column {
              id: bridgeInfo
              anchors.left: parent.left
              anchors.right: bridgeActions.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(1)
              LabText { text: "Bridge"; font.pixelSize: Style.font.bodySmall; font.bold: true }
              Caption {
                font.pixelSize: Style.font.caption
                text: (root.state.version ? "Collie " + root.state.version + ", " : "") + "port " + root.bridgePort
              }
            }
            Row {
              id: bridgeActions
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(6)
              LabButton {
                visible: root.state.healthy && !root.state.tailnetPublished
                text: "Publish"; enabled: !root.busy && root.state.tailscaleReady
                onClicked: root.act("serve")
              }
              LabButton { text: "Restart"; bordered: false; tooltipText: "r"; enabled: !root.busy; onClicked: root.act("restart") }
              LabButton { text: "Diagnostics"; bordered: false; tooltipText: "d"; enabled: !root.busy; onClicked: { root.showDetails = true; root.act("doctor") } }
            }
          }

          // Keys for what is on screen now.
          Flow {
            width: parent.width
            spacing: Style.space(12)
            visible: root.checked
            KeyHint { visible: root.ready && root.mode === ""; cap: "w"; verb: "Watch only" }
            KeyHint { visible: root.ready && root.mode === ""; cap: "f"; verb: "Full control" }
            KeyHint { visible: root.ready && root.mode === "control"; cap: "n"; verb: "New code" }
            KeyHint { visible: root.ready && root.mode === "watch"; cap: "c"; verb: "Copy link" }
            KeyHint { visible: root.ready && root.canOpenHere; cap: "o"; verb: "Open here" }
            KeyHint { visible: !root.ready && primaryButton.activeFocus; cap: "↵"; verb: root.primaryLabel }
            KeyHint { visible: !root.ready && root.state.installed; cap: "s"; verb: root.state.healthy ? "Stop" : "Start" }
            KeyHint { cap: "Esc"; verb: root.mode !== "" ? "Back" : "Close" }
          }
        }
      }
    }
  }
}
