// KAOT WebUI - 前端交互

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '-';
    if (seconds < 60) return seconds.toFixed(1) + 's';
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return minutes + 'm ' + secs + 's';
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString('zh-CN');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function parseANSI(text) {
    const ansiColors = {
        '30': '#4a4a4a', '31': '#ff4757', '32': '#00ff88', '33': '#ffaa00',
        '34': '#00d4ff', '35': '#ff6b9d', '36': '#00e5cc', '37': '#e0e6ed',
        '90': '#6b7280', '91': '#ff6b6b', '92': '#51cf66', '93': '#fcc419',
        '94': '#339af0', '95': '#cc5de8', '96': '#22d3ee', '97': '#f8f9fa',
        '1': 'bold'
    };
    
    let result = text;
    const ansiRegex = /\x1b\u005b(\d+(?:;\d+)*)m/g;
    
    result = result.replace(ansiRegex, (match, codes) => {
        const codeList = codes.split(';');
        let style = '';
        
        for (const code of codeList) {
            if (ansiColors[code]) {
                if (code === '1') {
                    style += 'font-weight:bold;';
                } else {
                    style += `color:${ansiColors[code]};`;
                }
            }
        }
        
        return style ? `<span style="${style}">` : '</span>';
    });
    
    return result;
}

function parseLogColors(text) {
    let result = text;
    
    result = parseANSI(result);
    
    const lines = result.split('\n');
    const colorRules = [
        { class: 'log-success', keywords: ['SUCCESS', '成功', '完成', 'installed', 'done', '✔', '✓', 'OK', 'ok', 'ENABLE', 'enable', '启用'] },
        { class: 'log-error', keywords: ['ERROR', 'FAILED', '失败', '错误', 'fatal', 'Fatal', '✗', '✖', 'ERR', 'DISABLE', 'disable'] },
        { class: 'log-warning', keywords: ['WARNING', 'WARN', '警告', '注意', 'WARNI', '需要重启', 'reboot required'] },
        { class: 'log-info', keywords: ['INFO', '===', '---', '开始', '结束', 'Starting', 'Finished', 'TASK', 'PLAY', '执行', '生成'] },
        { class: 'log-command', keywords: ['Command:', '$ ', 'bash', 'python', 'kaot.py', 'EXECUTING', 'Running'] },
    ];
    
    return lines.map(line => {
        if (line.includes('<span')) {
            return line;
        }
        
        const escapedLine = escapeHtml(line);
        
        for (const rule of colorRules) {
            for (const keyword of rule.keywords) {
                if (line.toUpperCase().includes(keyword.toUpperCase())) {
                    return `<span class="${rule.class}">${escapedLine}</span>`;
                }
            }
        }
        
        return escapedLine;
    }).join('\n');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#00d9ff' : '#533483'};
        color: #fff;
        border-radius: 4px;
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

class LogPoller {
    constructor(taskId, logElement, statusElement) {
        this.taskId = taskId;
        this.logElement = logElement;
        this.statusElement = statusElement;
        this.pos = 0;
        this.timer = null;
        this.stopped = false;
    }
    
    start() {
        this.poll();
    }
    
    stop() {
        this.stopped = true;
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }
    
    async poll() {
        if (this.stopped) return;
        
        try {
            const response = await fetch(`/api/logs/${this.taskId}?pos=${this.pos}`);
            const data = await response.json();
            
            if (data.content) {
                const coloredContent = parseLogColors(data.content);
                this.logElement.innerHTML += coloredContent;
                this.pos = data.pos;
                this.logElement.scrollTop = this.logElement.scrollHeight;
            }
            
            if (data.status === 'running') {
                this.timer = setTimeout(() => this.poll(), 500);
            } else {
                this.onComplete(data.status);
            }
        } catch (error) {
            console.error('日志获取失败:', error);
            this.timer = setTimeout(() => this.poll(), 1000);
        }
    }
    
    onComplete(status) {
        if (this.statusElement) {
            this.statusElement.textContent = status === 'success' ? '执行成功 ✓' : '执行失败 ✗';
            this.statusElement.className = `status-${status}`;
        }
        showToast(`任务执行${status === 'success' ? '成功' : '失败'}`, status);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
    
    const runningTasks = document.querySelectorAll('.status-running');
    if (runningTasks.length > 0) {
        setInterval(() => {
            location.reload();
        }, 30000);
    }
    
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredInputs = form.querySelectorAll('[required]');
            let valid = true;
            
            requiredInputs.forEach(input => {
                if (!input.value.trim()) {
                    valid = false;
                    input.style.borderColor = '#dc3545';
                    showToast(`${input.previousElementSibling?.textContent || input.name} 是必填项`, 'error');
                } else {
                    input.style.borderColor = '';
                }
            });
            
            if (!valid) {
                e.preventDefault();
            }
        });
    });
});

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { formatDuration, formatTimestamp, escapeHtml, parseLogColors, showToast, LogPoller };
}