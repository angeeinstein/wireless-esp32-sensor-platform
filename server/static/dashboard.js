// Initialize Socket.IO connection
const socket = io();

// Initialize Chart.js
let accelChart = null;
const CHART_WINDOW_SECONDS = 2;  // Show 2 seconds of data for smooth display

function initChart() {
    const ctx = document.getElementById('accelChart').getContext('2d');
    accelChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'X-Axis',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1
                },
                {
                    label: 'Y-Axis',
                    data: [],
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1
                },
                {
                    label: 'Z-Axis',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,  // Disable animations for faster updates
            scales: {
                x: {
                    type: 'linear',
                    title: {
                        display: true,
                        text: 'Time (seconds)'
                    },
                    ticks: {
                        callback: function(value) {
                            return value.toFixed(3);
                        }
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Acceleration (g)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    enabled: false
                },
                decimation: {
                    enabled: true,
                    algorithm: 'lttb'
                }
            }
        }
    });
}

function updateChart() {
    // Fetch full resolution data from server
    fetch('/api/samples/recent?seconds=' + CHART_WINDOW_SECONDS)
        .then(r => r.json())
        .then(result => {
            if (result.samples && result.samples.length > 0) {
                const samples = result.samples;
                
                // Get relative time from oldest sample
                const startTime = samples[0].timestamp;
                
                // Update chart datasets with all available data
                accelChart.data.datasets[0].data = samples.map(s => ({
                    x: s.timestamp - startTime,
                    y: s.ax_g
                }));
                accelChart.data.datasets[1].data = samples.map(s => ({
                    x: s.timestamp - startTime,
                    y: s.ay_g
                }));
                accelChart.data.datasets[2].data = samples.map(s => ({
                    x: s.timestamp - startTime,
                    y: s.az_g
                }));
                
                // Update chart without animation for smooth display
                accelChart.update('none');
            }
        })
        .catch(error => {
            console.error('Error updating chart:', error);
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

// WebSocket event handlers
socket.on('connect', () => {
    console.log('WebSocket connected');
    document.getElementById('loading').style.display = 'none';
    document.getElementById('content').style.display = 'block';
});

socket.on('disconnect', () => {
    console.log('WebSocket disconnected');
    const status = document.getElementById('status');
    const indicator = document.getElementById('statusIndicator');
    status.className = 'status-bar disconnected';
    indicator.className = 'status-indicator inactive';
    document.getElementById('statusText').textContent = 
        '❌ Connection lost - Reconnecting...';
});
    
        // Periodically refresh bulk data for smooth display
        refreshChartData();
    
// Real-time sample updates - now also updates chart at 30 Hz
socket.on('sample_update', (sample) => {
    if (sample) {
        document.getElementById('accel_x').textContent = sample.ax_g.toFixed(3);
        document.getElementById('accel_y').textContent = sample.ay_g.toFixed(3);
        document.getElementById('accel_z').textContent = sample.az_g.toFixed(3);
        document.getElementById('sample_id').textContent = formatNumber(sample.sample_id);
        
        // Calculate magnitude
        const mag = Math.sqrt(
            sample.ax_g * sample.ax_g + 
            sample.ay_g * sample.ay_g + 
            sample.az_g * sample.az_g
        );
        document.getElementById('accel_norm').textContent = mag.toFixed(3);
        
        // Update chart in real-time at 30 Hz
        updateChartWithSample(sample);
    }
});

// Real-time stats updates
socket.on('stats_update', (stats) => {
    if (stats) {
        document.getElementById('sample_rate').textContent = 
            formatNumber(stats.samples_per_sec, 0);
        document.getElementById('data_rate').textContent = 
            stats.mbit_per_sec.toFixed(2);
        document.getElementById('total_samples').textContent = 
            formatNumber(stats.total_samples);
        document.getElementById('total_drops').textContent = 
            formatNumber(stats.total_drops);
        document.getElementById('buffer_size').textContent = 
            formatNumber(stats.buffer_size);
        document.getElementById('uptime').textContent = 
            formatNumber(stats.uptime_sec, 1);
        
        // Update status
        const status = document.getElementById('status');
        const indicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');
        
        if (stats.is_receiving) {
            status.className = 'status-bar connected';
            indicator.className = 'status-indicator active';
            statusText.textContent = '✅ Connected - Receiving data';
        } else {
            status.className = 'status-bar disconnected';
            indicator.className = 'status-indicator inactive';
            statusText.textContent = '⏳ Waiting for data stream...';
        }
        
        document.getElementById('lastUpdate').textContent = 
            'Last update: ' + new Date().toLocaleTimeString();
    }
});

// Initialize chart on page load
initChart();

// Update chart every 100ms for high time resolution (10 Hz refresh with full data)
updateChart();
setInterval(updateChart, 100);
