// Load settings on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadDatabaseStats();
});

// Make functions globally accessible
window.loadSettings = loadSettings;
window.saveRetention = saveRetention;
window.clearAllData = clearAllData;
window.optimizeDatabase = optimizeDatabase;
window.loadDatabaseStats = loadDatabaseStats;
window.sendESPCommand = sendESPCommand;

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

function optimizeDatabase() {
    if (!confirm('⚠️ This will delete data older than the retention period and optimize the database. This may take several minutes. Continue?')) {
        return;
    }
    
    showToast('info', 'Optimizing...', 'This may take a few minutes for large databases');
    
    fetch('/api/database/cleanup', {
        method: 'POST'
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const message = `
Deleted ${formatNumber(data.samples_deleted)} old samples
Database: ${data.size_before_mb.toFixed(2)} MB → ${data.size_after_mb.toFixed(2)} MB
Reclaimed: ${data.space_reclaimed_mb.toFixed(2)} MB`;
            showToast('success', 'Optimization Complete', message);
            loadDatabaseStats();
        } else {
            showToast('error', 'Error', data.message);
        }
    })
    .catch(err => {
        showToast('error', 'Error', 'Failed to optimize database');
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
                
                // Show success toast
                showToast('success', 'Stats Refreshed', 'Database statistics updated successfully');
            } else {
                showToast('error', 'Error', data.message || 'Failed to load stats');
            }
        })
        .catch(err => {
            console.error('Error loading database stats:', err);
            showToast('error', 'Connection Error', 'Failed to fetch database statistics');
        });
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
    // Create a human-readable display of JSON data
    const result = [];
    result.push('<div class="response-formatted">');
    
    // Special handling for ESP32 responses
    if (obj.raw_response && typeof obj.raw_response === 'string') {
        try {
            const parsed = JSON.parse(obj.raw_response);
            obj = parsed;
        } catch (e) {
            // If parsing fails, display as-is
        }
    }
    
    function formatKey(key) {
        // Convert snake_case or camelCase to Title Case
        return key.replace(/_/g, ' ')
                  .replace(/([A-Z])/g, ' $1')
                  .replace(/^./, str => str.toUpperCase())
                  .trim();
    }
    
    function renderValue(key, value, isNested = false) {
        const formattedKey = formatKey(key);
        
        if (value === null || value === undefined) {
            return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-null">Not set</span></div>`;
        } else if (typeof value === 'boolean') {
            return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-boolean">${value ? '✓ Yes' : '✗ No'}</span></div>`;
        } else if (typeof value === 'number') {
            return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-number">${value.toLocaleString()}</span></div>`;
        } else if (typeof value === 'string') {
            return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-string">${escapeHtml(value)}</span></div>`;
        } else if (Array.isArray(value)) {
            if (value.length === 0) {
                return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-empty">None</span></div>`;
            }
            let html = `<div class="response-section"><strong>${formattedKey}:</strong></div>`;
            value.forEach((item, i) => {
                if (typeof item === 'object') {
                    html += `<div class="response-subsection">Item ${i + 1}:</div>`;
                    Object.keys(item).forEach(k => {
                        html += renderValue(k, item[k], true);
                    });
                } else {
                    html += `<div class="response-line nested">• ${escapeHtml(String(item))}</div>`;
                }
            });
            return html;
        } else if (typeof value === 'object') {
            const keys = Object.keys(value);
            if (keys.length === 0) {
                return `<div class="response-line ${isNested ? 'nested' : ''}"><strong>${formattedKey}:</strong> <span class="value-empty">None</span></div>`;
            }
            let html = `<div class="response-section"><strong>${formattedKey}:</strong></div>`;
            keys.forEach(k => {
                html += renderValue(k, value[k], true);
            });
            return html;
        }
        return '';
    }
    
    // Render top-level object
    const keys = Object.keys(obj);
    keys.forEach(key => {
        result.push(renderValue(key, obj[key], false));
    });
    
    result.push('</div>');
    return result.join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Run diagnostics to investigate database size
function runDiagnostics() {
    showToast('Running diagnostics...', 'info');
    
    fetch('/api/database/diagnostics')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const section = document.getElementById('diagnostics-section');
                const output = document.getElementById('diagnostics-output');
                
                // Format diagnostics output
                let text = '=== DATABASE DIAGNOSTICS ===\n\n';
                
                text += '📊 SAMPLE DATA:\n';
                text += `  Total Samples: ${data.total_samples.toLocaleString()}\n`;
                text += `  Time Span: ${data.time_span.span_seconds.toFixed(2)}s (${data.time_span.span_hours}h)\n`;
                text += `  Average Rate: ${data.sample_rate.average_hz.toLocaleString()} Hz\n`;
                text += `  Expected Rate: ${data.sample_rate.expected_hz.toLocaleString()} Hz\n\n`;
                
                text += '🔍 DUPLICATE CHECK:\n';
                text += `  Duplicate sample_ids: ${data.duplicate_sample_ids}\n`;
                if (data.duplicate_examples.length > 0) {
                    text += '  Examples:\n';
                    data.duplicate_examples.forEach(d => {
                        text += `    sample_id ${d.sample_id}: ${d.count} copies\n`;
                    });
                } else {
                    text += '  ✓ No duplicates found\n';
                }
                text += '\n';
                
                text += '💾 FILE SIZES:\n';
                text += `  Main DB: ${data.file_sizes.db_mb.toFixed(2)} MB\n`;
                text += `  WAL file: ${data.file_sizes.wal_mb.toFixed(2)} MB\n`;
                text += `  SHM file: ${data.file_sizes.shm_mb.toFixed(2)} MB\n`;
                text += `  TOTAL: ${data.file_sizes.total_mb.toFixed(2)} MB\n\n`;
                
                text += '📐 SIZE ANALYSIS:\n';
                text += `  Expected (raw): ${data.size_analysis.expected_raw_mb.toFixed(2)} MB\n`;
                text += `  Actual: ${data.size_analysis.actual_mb.toFixed(2)} MB\n`;
                text += `  Overhead Factor: ${data.size_analysis.overhead_factor}x\n\n`;
                
                text += '🗄️ SQLITE INTERNALS:\n';
                text += `  Page Count: ${data.sqlite_internals.page_count.toLocaleString()}\n`;
                text += `  Page Size: ${data.sqlite_internals.page_size} bytes\n`;
                text += `  Calculated Size: ${data.sqlite_internals.calculated_size_mb.toFixed(2)} MB\n\n`;
                
                text += '📑 TABLES:\n';
                data.tables.forEach(t => {
                    text += `  - ${t.name}\n`;
                });
                text += '\n';
                
                text += '🔑 INDEXES:\n';
                data.indexes.forEach(idx => {
                    text += `  - ${idx.name}\n`;
                });
                
                output.textContent = text;
                section.style.display = 'block';
                
                // Scroll to diagnostics
                section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                
                showToast('Diagnostics complete', 'success');
            } else {
                showToast(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to run diagnostics', 'error');
        });
}

window.runDiagnostics = runDiagnostics;