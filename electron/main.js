const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
    const win = new BrowserWindow({
        width: 1280,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            webSecurity: true,
            allowRunningInsecureContent: false,
            devTools: false
        },
    });

    win.loadFile('index.html');

    // Prevent new windows from being created
    win.webContents.setWindowOpenHandler(() => {
        // Deny all new window requests
        return { action: 'deny' };
    });

    // Allow navigation to local files, prevent navigation to external URLs
    win.webContents.on('will-navigate', (event, url) => {
        if (url.startsWith('file://')) {
            // Allow navigation to local files
            return;
        } else {
            // Prevent navigation to external URLs
            event.preventDefault();
        }
    });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', function () {
    if (process.platform !== 'darwin') app.quit();
});
