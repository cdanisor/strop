// Cron Expression Builder Component
class CronBuilder {
    constructor(containerId, builderId) {
        this.containerId = containerId;
        this.builderId = builderId;
        this.cronExpression = '';
        this.cronParts = {
            minute: '*',
            hour: '*',
            dayOfWeek: '*'
        };
        this.init();
    }

    init() {
        this.render();
        this.bindEvents();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error('Container not found:', this.containerId);
            return;
        }

        // Generate unique IDs for all elements to avoid conflicts
        const uniquePrefix = `cron-builder-${this.builderId}-`;
        
        container.innerHTML = `
            <div class="cron-builder-container" id="${uniquePrefix}container">
                <div class="cron-builder-header">
                    <h5>Cron Expression Builder</h5>
                </div>
                <div class="cron-builder-body">
                    <div class="cron-builder-row">
                        <div class="cron-builder-group">
                            <label>Minute</label>
                            <input type="text" class="form-control" id="${uniquePrefix}minute-input" placeholder="e.g., 0, 15, 30, 45, */5, 0-59">
                        </div>
                        <div class="cron-builder-group">
                            <label>Hour</label>
                            <input type="text" class="form-control" id="${uniquePrefix}hour-input" placeholder="e.g., 0, 6, 12, 18, */2, 0-23">
                        </div>
                    </div>
                    <div class="cron-builder-row">
                        <div class="cron-builder-group">
                            <label>Day of Week</label>
                            <select class="form-control" id="${uniquePrefix}day-of-week-select" multiple>
                                <option value="0">Sunday</option>
                                <option value="1">Monday</option>
                                <option value="2">Tuesday</option>
                                <option value="3">Wednesday</option>
                                <option value="4">Thursday</option>
                                <option value="5">Friday</option>
                                <option value="6">Saturday</option>
                            </select>
                        </div>
                        <div class="cron-builder-group">
                            <label>Expression</label>
                            <input type="text" class="form-control" id="${uniquePrefix}expression" placeholder="Cron expression will appear here" readonly>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    bindEvents() {
        // Bind all input change events with unique IDs
        const container = document.getElementById(this.containerId);
        const uniquePrefix = `cron-builder-${this.builderId}-`;
        
        const minuteInput = container.querySelector(`#${uniquePrefix}minute-input`);
        if (minuteInput) {
            minuteInput.addEventListener('input', (e) => {
                this.cronParts.minute = e.target.value;
                this.updateExpression();
            });
        }
        
        const hourInput = container.querySelector(`#${uniquePrefix}hour-input`);
        if (hourInput) {
            hourInput.addEventListener('input', (e) => {
                this.cronParts.hour = e.target.value;
                this.updateExpression();
            });
        }
        
        const dayOfWeekSelect = container.querySelector(`#${uniquePrefix}day-of-week-select`);
        if (dayOfWeekSelect) {
            dayOfWeekSelect.addEventListener('change', (e) => {
                // For multiple select, we need to collect all selected values
                const selected = Array.from(e.target.selectedOptions).map(option => option.value);
                this.cronParts.dayOfWeek = selected.length > 0 ? selected.join(',') : '*';
                this.updateExpression();
            });
        }
    }

    updateExpression() {
        const expression = `${this.cronParts.minute} ${this.cronParts.hour} * * ${this.cronParts.dayOfWeek}`;
        const uniquePrefix = `cron-builder-${this.builderId}-`;
        const expressionInput = document.getElementById(`${uniquePrefix}expression`);
        if (expressionInput) {
            expressionInput.value = expression;
        }
        this.cronExpression = expression;
        console.log('Updated expression to:', expression);
    }

    showPreview() {
        const uniquePrefix = `cron-builder-${this.builderId}-`;
        const preview = document.getElementById(`${uniquePrefix}preview`);
        const previewContent = document.getElementById(`${uniquePrefix}preview-content`);
        
        if (preview.style.display === 'none') {
            preview.style.display = 'block';
            previewContent.innerHTML = `
                <div class="alert alert-info">
                    <strong>Preview:</strong> This cron expression will run according to the selected schedule.
                    <br><strong>Expression:</strong> ${this.cronExpression}
                    <br><strong>Explanation:</strong>
                    <ul>
                        <li>Minute: ${this.getReadableValue(this.cronParts.minute, 'minute')}</li>
                        <li>Hour: ${this.getReadableValue(this.cronParts.hour, 'hour')}</li>
                        <li>Day of Month: Every day (fixed to *)</li>
                        <li>Month: Every month (fixed to *)</li>
                        <li>Day of Week: ${this.getReadableValue(this.cronParts.dayOfWeek, 'day of week')}</li>
                    </ul>
                </div>
            `;
        } else {
            preview.style.display = 'none';
        }
    }

    getReadableValue(value, type) {
        if (value === '*') return 'Every ' + type;
        if (value.includes('-')) return 'Range: ' + value;
        if (value.includes('/')) return 'Every ' + value.split('/')[1] + ' ' + type;
        if (value.includes(',')) return 'Specific: ' + value;
        return value;
    }

    applyExpression() {
        // This would be called from the parent component to apply the expression
        console.log('Apply expression called:', this.cronExpression);
        return this.cronExpression;
    }

    reset() {
        // Reset all inputs to default values
        const container = document.getElementById(this.containerId);
        const uniquePrefix = `cron-builder-${this.builderId}-`;
        
        const minuteInput = container.querySelector(`#${uniquePrefix}minute-input`);
        if (minuteInput) minuteInput.value = '';
        
        const hourInput = container.querySelector(`#${uniquePrefix}hour-input`);
        if (hourInput) hourInput.value = '';
        
        const dayOfWeekSelect = container.querySelector(`#${uniquePrefix}day-of-week-select`);
        if (dayOfWeekSelect) dayOfWeekSelect.value = '*';
        
        // Reset expression
        this.cronParts = {
            minute: '*',
            hour: '*',
            dayOfWeek: '*'
        };
        this.updateExpression();
        console.log('CronBuilder reset');
    }

    // Method to set expression from outside
    setExpression(expression) {
        if (!expression) {
            // Reset to default values when expression is empty
            this.cronParts = {
                minute: '*',
                hour: '*',
                dayOfWeek: '*'
            };
            this.updateExpression();
            return;
        }
        
        const parts = expression.split(' ');
        if (parts.length >= 5) {
            this.cronParts.minute = parts[0];
            this.cronParts.hour = parts[1];
            // Skip dayOfMonth and month (they are fixed to *)
            this.cronParts.dayOfWeek = parts[4];
            
            // Update the UI
            const container = document.getElementById(this.containerId);
            const uniquePrefix = `cron-builder-${this.builderId}-`;
            
            const minuteInput = container.querySelector(`#${uniquePrefix}minute-input`);
            if (minuteInput) minuteInput.value = this.cronParts.minute;
            
            const hourInput = container.querySelector(`#${uniquePrefix}hour-input`);
            if (hourInput) hourInput.value = this.cronParts.hour;
            
            const dayOfWeekSelect = container.querySelector(`#${uniquePrefix}day-of-week-select`);
            if (dayOfWeekSelect) {
                if (this.cronParts.dayOfWeek === '*') {
                    dayOfWeekSelect.value = '*';
                } else {
                    // For multiple select, we need to set the selected values
                    const selectedValues = this.cronParts.dayOfWeek.split(',');
                    Array.from(dayOfWeekSelect.options).forEach(option => {
                        option.selected = selectedValues.includes(option.value);
                    });
                }
            }
            
            this.cronExpression = expression;
            console.log('Set expression to:', expression);
            this.updateExpression(); // Make sure the expression is updated in the preview field
        } else {
            // If expression is invalid, reset to defaults
            this.cronParts = {
                minute: '*',
                hour: '*',
                dayOfWeek: '*'
            };
            this.updateExpression();
        }
    }

    // Method to get the current expression
    getExpression() {
        return this.cronExpression;
    }
    
    // Method to update the hidden input field (for API compatibility)
    updateHiddenInput(valveId) {
        if (valveId) {
            const hiddenInput = document.getElementById(`cron${valveId}`);
            if (hiddenInput) {
                hiddenInput.value = this.cronExpression;
            }
        }
    }
}

// Make the class globally available
if (typeof window !== 'undefined') {
    window.CronBuilder = CronBuilder;
}