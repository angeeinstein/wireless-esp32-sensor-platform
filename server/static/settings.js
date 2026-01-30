// Load settings on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadDatabaseStats();
});

function loadSettings() {
    // Load retention period
    fetch('/api/settings/retention')
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                document.getElementById('retentionHours').value = data.retention_hours;
            }
        })
        .catch(err => console.error('Error loading settings:', err));
}

function saveRetention() {
    const hours = parseFloat(document.getElementById('retentionHours').value);
    
    fetch('/api/settings/retention', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({retention_hours: hours})
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showToast('success', 'Settings Saved', data.message);
        } else {
            showToast('error', 'Error', data.message);
        }
    })
    .catch(err => {
        showToast('error', 'Error', 'Failed to save settings');
        console.error(err);
    });
}

function clearAllData() {
    if (!confirm('⚠️ Are you sure you want to delete ALL data? This cannot be undone!')) {
        return;
    }
    
    fetch('/api/database/clear', {
        method: 'POST'
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showToast('success', 'Database Cleared', data.message);
            loadDatabaseStats();
        } else {
            showToast('error', 'Error', data.message);
        }
    })
    .catch(err => {
        showToast('error', 'Error', 'Failed to clear database');
        console.error(err);
    });
}

function loadDatabaseStats() {
    fetch('/api/database/stats')
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                const db = data.database;
                document.getElementById('dbTotalSamples').textContent = 
                    formatNumber(db.total_samples);
                document.getElementById('dbSize').textContent = 
                    db.size_mb.toFixed(2) + ' MB';
                document.getElementById('dbTimeSpan').textContent = 
                    db.time_span_hours.toFixed(2) + ' hours';
                document.getElementById('dbQueueSize').textContent = 
                    `${db.write_queue_size} / ${db.write_queue_max}`;
            }
        })
        .catch(err => console.error('Error loading database stats:', err));
}

function sendESPCommand(endpoint, method) {
    const espIp = document.getElementById('espIp').value.trim();
    
    if (!espIp) {
        showToast('error', 'Missing IP', 'Please enter ESP32 IP address');
        return;
    }
    
    showToast('info', 'Sending Command', `${method} ${endpoint}...`);
    
    fetch('/api/esp32/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            esp_ip: espIp,
            endpoint: endpoint,
            method: method
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            // Format JSON response nicely
            const response = data.esp_response;
            showToast('success', 'ESP32 Response', response, true);
        } else {
            showToast('error', 'ESP32 Error', data.message);
        }
    })
    .catch(err => {
        showToast('error', 'Connection Error', 'Failed to communicate with ESP32');
        console.error(err);
    });
}

function formatNumber(num, decimals = 0) {
    if (num == null || isNaN(num)) return '--';
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toFixed(decimals);
}

// ===== TOAST NOTIFICATION SYSTEM =====

let toastId = 0;

function showToast(type, title, message, isJson = false) {
    const container = document.getElementById('toastContainer');
    const id = `toast-${toastId++}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        info: 'ℹ️'
    };
    
    let messageHtml;
    if (isJson && typeof message === 'object') {
        // Format JSON with nice indentation
        messageHtml = `<pre class="toast-json">${JSON.stringify(message, null, 2)}</pre>`;
    } else if (isJson && typeof message === 'string') {
        // Try to parse and format if it's a JSON string
        try {
            const parsed = JSON.parse(message);
            messageHtml = `<pre class="toast-json">${JSON.stringify(parsed, null, 2)}</pre>`;
        } catch {
            messageHtml = `<div class="toast-message">${message}</div>`;
        }
    } else {
        messageHtml = `<div class="toast-message">${message}</div>`;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.id = id;
    toast.innerHTML = `
        <div class="toast-header">
            <div class="toast-icon">${icons[type] || 'ℹ️'}</div>
            <div class="toast-title">${title}</div>
        </div>
        <div class="toast-body">
            ${messageHtml}
        </div>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after 8 seconds (longer for JSON responses)
    const duration = isJson ? 10000 : 5000;
    setTimeout(() => {
        const toastElement = document.getElementById(id);
        if (toastElement) {
            toastElement.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                toastElement.remove();
            }, 300);
        }
    }, duration);
}
