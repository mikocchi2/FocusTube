const { contextBridge } = require('electron');

// Expose APIs to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
    // Add methods if needed
});
