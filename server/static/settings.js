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
        // Format as structured data
        messageHtml = formatJsonResponse(message);
    } else if (isJson && typeof message === 'string') {
        // Try to parse and format if it's a JSON string
        try {
            const parsed = JSON.parse(message);
            messageHtml = formatJsonResponse(parsed);
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

function formatJsonResponse(obj) {
    // Create a structured display of JSON data
    const result = [];
    result.push('<div class="json-structured">');
    
    function renderValue(key, value, indent = 0) {
        const indentStr = '  '.repeat(indent);
        
        if (value === null || value === undefined) {
            return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> <span class="json-null">null</span></div>`;
        } else if (typeof value === 'boolean') {
            return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> <span class="json-boolean">${value}</span></div>`;
        } else if (typeof value === 'number') {
            return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> <span class="json-number">${value}</span></div>`;
        } else if (typeof value === 'string') {
            return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> <span class="json-string">"${escapeHtml(value)}"</span></div>`;
        } else if (Array.isArray(value)) {
            if (value.length === 0) {
                return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> []</div>`;
            }
            let html = `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> [</div>`;
            value.forEach((item, i) => {
                html += renderValue(`[${i}]`, item, indent + 1);
            });
            html += `${indentStr}<div class="json-line">]</div>`;
            return html;
        } else if (typeof value === 'object') {
            const keys = Object.keys(value);
            if (keys.length === 0) {
                return `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> {}</div>`;
            }
            let html = `${indentStr}<div class="json-line"><span class="json-key">${key}:</span> {</div>`;
            keys.forEach(k => {
                html += renderValue(k, value[k], indent + 1);
            });
            html += `${indentStr}<div class="json-line">}</div>`;
            return html;
        }
        return '';
    }
    
    // Render top-level object
    const keys = Object.keys(obj);
    keys.forEach(key => {
        result.push(renderValue(key, obj[key], 0));
    });
    
    result.push('</div>');
    return result.join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
