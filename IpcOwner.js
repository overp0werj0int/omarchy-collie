.pragma library

// One stable IPC target across monitor widgets, without changing the bar's service contract.
var widgets = []

function register(widget) {
    if (widgets.indexOf(widget) < 0) widgets.push(widget)
    elect()
}

function unregister(widget) {
    var index = widgets.indexOf(widget)
    if (index >= 0) widgets.splice(index, 1)
    elect()
}

function elect() {
    for (var i = 0; i < widgets.length; i++) widgets[i].ipcPrimary = i === 0
}
