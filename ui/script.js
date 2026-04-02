// jQuery script for Valve Control System UI
$(document).ready(function() {
    // API base URL - will be injected by the server
    if (typeof API_BASE_URL === 'undefined') {
        API_BASE_URL = 'http://localhost:5000/api';
    }
    
    // Initialize dark mode based on localStorage or system preference
    function initializeDarkMode() {
        const savedMode = localStorage.getItem('darkMode');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        
        if (savedMode !== null) {
            // Use saved preference
            if (savedMode === 'true') {
                enableDarkMode();
            } else {
                disableDarkMode();
            }
        } else if (prefersDark) {
            // Use system preference
            enableDarkMode();
        }
    }
    
    // Enable dark mode
    function enableDarkMode() {
        $('body').addClass('dark-mode');
        localStorage.setItem('darkMode', 'true');
        updateDarkModeIcon();
    }
    
    // Disable dark mode
    function disableDarkMode() {
        $('body').removeClass('dark-mode');
        localStorage.setItem('darkMode', 'false');
        updateDarkModeIcon();
    }
    
    // Update the dark mode toggle icon
    function updateDarkModeIcon() {
        const isDarkMode = $('body').hasClass('dark-mode');
        if (isDarkMode) {
            $('.dark-mode-icon').show();
            $('.light-mode-icon').hide();
        } else {
            $('.light-mode-icon').show();
            $('.dark-mode-icon').hide();
        }
    }
    
    // Toggle dark mode
    $('#dark-mode-toggle').on('click', function() {
        if ($('body').hasClass('dark-mode')) {
            disableDarkMode();
        } else {
            enableDarkMode();
        }
    });
    
    // Initialize dark mode on page load
    initializeDarkMode();
    
    // Update icon when dark mode changes
    updateDarkModeIcon();
    
    // Store previous statuses to detect changes
    let previousStatuses = {};
    
    // Function to update valve status display
    function updateValveStatus(valveId, status) {
        const valveElement = $(`#valve${valveId}`);
        const headerCard = $(`#header${valveId}`);
        const toggleBtn = $(`.btn-toggle[data-valve="${valveId}"]`);
        const durationInput = $(`#duration${valveId}`);
        const statusBadge = $(`#status-badge-${valveId}`);
        
        if (status) {
            valveElement.addClass('active');
            headerCard.removeClass('inactive').addClass('active');
            toggleBtn.removeClass('btn-success').addClass('btn-danger');
            toggleBtn.text('Deactivate');
            // Disable duration input when valve is active
            durationInput.prop('disabled', true);
            statusBadge.removeClass('bg-secondary').addClass('bg-success').text('Active');
        } else {
            valveElement.removeClass('active');
            headerCard.removeClass('active').addClass('inactive');
            toggleBtn.removeClass('btn-danger').addClass('btn-success');
            toggleBtn.text('Activate');
            // Enable duration input when valve is inactive
            durationInput.prop('disabled', false);
            statusBadge.removeClass('bg-success').addClass('bg-secondary').text('Inactive');
        }
    }
    
    // Function to update system status summary
    function updateSystemStatus() {
        let activeCount = 0;
        let inactiveCount = 0;
        
        for (let valveId = 1; valveId <= 2; valveId++) {
            if (previousStatuses[valveId]) {
                activeCount++;
            } else {
                inactiveCount++;
            }
        }
        
        $('#active-valves-count').text(activeCount);
        $('#inactive-valves-count').text(inactiveCount);
    }
    
    // Function to show message with better UX
    function showMessage(message, type = 'success') {
        const messageArea = $('#message-area');
        messageArea.text(message);
        messageArea.removeClass('success error');
        messageArea.addClass(type);
        messageArea.show();
        
        // Hide message after 5 seconds or when user clicks on it
        setTimeout(() => {
            messageArea.fadeOut();
        }, 5000);
        
        // Allow manual dismissal by clicking on the message
        messageArea.off('click').on('click', function() {
            $(this).fadeOut();
        });
    }
    
    // Function to get all valve statuses with better error handling
    function getAllValveStatus() {
        $.ajax({
            url: `${API_BASE_URL}/valves/status`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                if (data && data.valves) {
                    let statusChanged = false;
                    $.each(data.valves, function(valveId, status) {
                        updateValveStatus(valveId, status);
                        // Check if status changed from previous value
                        if (previousStatuses[valveId] !== status) {
                            statusChanged = true;
                        }
                        previousStatuses[valveId] = status;
                    });
                    // If status changed, refresh history as well
                    if (statusChanged) {
                        getAllValveHistories();
                        // Update usage when status changes
                        getValveUsage();
                    }
                }
            },
            error: function(xhr, status, error) {
                // Only show error if it's not a connection error (which might be expected if server is not running)
                if (xhr.status !== 0) {
                    showMessage('Error fetching valve statuses: ' + (error || 'Network error'), 'error');
                }
            }
        });
    }
    
    // Function to get individual valve status with better error handling
    function getValveStatus(valveId) {
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/status`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                updateValveStatus(valveId, data.status);
                // Check if status changed from previous value and refresh history if needed
                if (previousStatuses[valveId] !== data.status) {
                    previousStatuses[valveId] = data.status;
                    getAllValveHistories();
                    // Update usage when status changes
                    getValveUsage();
                } else {
                    previousStatuses[valveId] = data.status;
                }
                // Update system status summary
                updateSystemStatus();
            },
            error: function(xhr, status, error) {
                showMessage(`Error fetching status for valve ${valveId}: ` + (error || 'Network error'), 'error');
            }
        });
    }
    
    // Function to activate valve with better validation and error handling
    function activateValve(valveId, duration = null) {
        const durationInput = $(`#duration${valveId}`);
        const durationValue = duration || parseInt(durationInput.val()) || 1;
        const toggleBtn = $(`.btn-toggle[data-valve="${valveId}"]`);
        const originalButtonText = toggleBtn.text();
        const originalButtonClass = toggleBtn.attr('class');
        
        // Show loading state on button
        toggleBtn.prop('disabled', true).text('Processing...').addClass('btn-secondary');
        
        // Validate duration if provided
        if (durationValue !== null && (isNaN(durationValue) || durationValue < 0)) {
            showMessage('Please enter a valid duration in minutes (non-negative number)', 'error');
            toggleBtn.prop('disabled', false).text(originalButtonText).removeClass('btn-secondary').addClass(originalButtonClass);
            return;
        }
        
        // Convert minutes to seconds before sending to API
        const durationInSeconds = durationValue * 60;
        // Limit duration to 60 minutes (3600 seconds) as per API restrictions
        const limitedDuration = Math.min(durationInSeconds, 3600);
        const payload = { duration: limitedDuration };
        
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/activate`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload),
            timeout: 10000, // 10 second timeout
            success: function(data) {
                // Show message with original minutes value for user clarity
                const displayDuration = `${Math.ceil(limitedDuration/60)} minutes`;
                showMessage(data.message + ` (${displayDuration})`, 'success');
                getValveStatus(valveId);
            },
            error: function(xhr, status, error) {
                const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : error || 'Unknown error';
                showMessage('Error activating valve ' + valveId + ': ' + errorMessage, 'error');
            },
            complete: function() {
                // Restore button state
                toggleBtn.prop('disabled', false).text(originalButtonText).removeClass('btn-secondary').addClass(originalButtonClass);
            }
        });
    }
    
    // Function to deactivate valve with better error handling
    function deactivateValve(valveId) {
        const toggleBtn = $(`.btn-toggle[data-valve="${valveId}"]`);
        const originalButtonText = toggleBtn.text();
        const originalButtonClass = toggleBtn.attr('class');
        const durationInput = $(`#duration${valveId}`);
        
        // Show loading state on button
        toggleBtn.prop('disabled', true).text('Processing...').addClass('btn-secondary');
        // Disable duration input during operation
        durationInput.prop('disabled', true);
        
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/deactivate`,
            method: 'POST',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                showMessage(data.message, 'success');
                getValveStatus(valveId);
            },
            error: function(xhr, status, error) {
                const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : error || 'Unknown error';
                showMessage('Error deactivating valve ' + valveId + ': ' + errorMessage, 'error');
            },
            complete: function() {
                // Restore button state
                toggleBtn.prop('disabled', false).text(originalButtonText).removeClass('btn-secondary').addClass(originalButtonClass);
                // Re-enable duration input
                durationInput.prop('disabled', false);
            }
        });
    }
    
    // Event handlers for control buttons with better error handling
    $('.btn-toggle').on('click', function() {
        const valveId = parseInt($(this).data('valve'));
        
        // Prevent rapid clicking
        const valveElement = $(`#valve${valveId}`);
        if (valveElement.hasClass('processing')) return;
        valveElement.addClass('processing');
        
        // Get the current status to determine what action to take
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/status`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                if (data.status) {
                    // Valve is active, so deactivate it
                    deactivateValve(valveId);
                } else {
                    // Valve is inactive, so activate it
                    activateValve(valveId);
                }
            },
            error: function(xhr, status, error) {
                showMessage(`Error checking valve status: ` + (error || 'Network error'), 'error');
            },
            complete: function() {
                valveElement.removeClass('processing'); // Remove processing class
            }
        });
    });
    
    // Handle duration input for activation with better UX
    $('.duration-input').on('keypress', function(e) {
        if (e.which === 13) { // Enter key
            const valveId = parseInt($(this).attr('id').replace('duration', '')); 
            activateValve(valveId);
        }
    });
    
    // Handle duration input blur for validation
    $('.duration-input').on('blur', function() {
        const valveId = parseInt($(this).attr('id').replace('duration', '')); 
        const durationValue = parseInt($(this).val());
        const durationInput = $(this);
        
        // Validate and format the input value
        if (isNaN(durationValue) || durationValue < 0) {
            showMessage('Please enter a valid duration in minutes (non-negative number)', 'error');
            durationInput.val(''); // Clear invalid input
        } else if (durationValue > 60) {
            showMessage('Duration cannot exceed 60 minutes', 'error');
            durationInput.val('60'); // Set to maximum allowed
        }
    });
    
    // Initialize the UI with current statuses
    getAllValveStatus();
    
    // Set up auto-refresh every 10 seconds (only status refresh)
    setInterval(getAllValveStatus, 10000);
    
    // Initialize valve histories
    getAllValveHistories();
    
    // Set initial button states with better error handling
    for (let valveId = 1; valveId <= 2; valveId++) {
        // Get initial status to set button text properly
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/status`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                updateValveStatus(valveId, data.status);
                previousStatuses[valveId] = data.status;
            },
            error: function(xhr, status, error) {
                // If we can't get status, default to inactive
                updateValveStatus(valveId, false);
                previousStatuses[valveId] = false;
            }
        });
    }
    
    // Initialize cron schedule UI
    initializeCronScheduleUI();
    
    // Function to initialize cron schedule UI
    function initializeCronScheduleUI() {
        // Initialize cron builder components for both valves
        initializeCronBuilder(1);
        initializeCronBuilder(2);
        
        // Load existing cron schedules when UI is initialized
        for (let valveId = 1; valveId <= 2; valveId++) {
            loadValveCronSchedule(valveId);
        }
        
        // Add event handlers for save buttons
        $('#save-cron1').on('click', function() {
            saveValveCronSchedule(1);
        });
        
        $('#save-cron2').on('click', function() {
            saveValveCronSchedule(2);
        });
        
        // Add event handlers for clear buttons
        $('#clear-cron1').on('click', function() {
            clearValveCronSchedule(1);
        });
        
        $('#clear-cron2').on('click', function() {
            clearValveCronSchedule(2);
        });
    }
    
    // Function to load valve cron schedule
    function loadValveCronSchedule(valveId) {
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/cron`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                console.log(`Data returned for valve ${valveId}:`, data); // Debug log
                if (data && data.cron) {
                    const cron = data.cron;
                    console.log(`Cron data for valve ${valveId}:`, cron); // Debug log
                    // Set the cron expression in the builder
                    if (window.cronBuilder && window.cronBuilder[valveId]) {
                        window.cronBuilder[valveId].setExpression(cron.cron_expression || '');
                    }
                    // Convert seconds back to minutes for display
                    const durationMinutes = Math.floor((cron.duration || 60) / 60);
                    $(`#cron-duration${valveId}`).val(durationMinutes);
                    $(`#enabled${valveId}`).prop('checked', cron.enabled || false);
                }
            },
            error: function(xhr, status, error) {
                console.log(`Error loading cron schedule for valve ${valveId}:`, error);
                // If there's an error, we should still try to initialize the cron builder
                if (window.cronBuilder && window.cronBuilder[valveId]) {
                    window.cronBuilder[valveId].setExpression('');
                }
            }
        });
    }
    
    // Function to save valve cron schedule
    function saveValveCronSchedule(valveId) {
        // Get the cron expression from the builder if it exists
        let cronExpression = '';
        if (window.cronBuilder && window.cronBuilder[valveId]) {
            cronExpression = window.cronBuilder[valveId].getExpression();
        } else {
            // Fallback to the original input field (should not happen with proper initialization)
            cronExpression = $(`#cron${valveId}`).val();
        }
        
        const durationMinutes = parseInt($(`#cron-duration${valveId}`).val()) || 1;
        const enabled = $(`#enabled${valveId}`).is(':checked');
        
        if (!cronExpression) {
            showMessage('Please enter a cron expression', 'error');
            return;
        }
        
        // Convert minutes to seconds for API
        const durationSeconds = durationMinutes * 60;
        
        const payload = {
            cron_expression: cronExpression,
            duration: durationSeconds,
            enabled: enabled
        };
        
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/cron`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload),
            timeout: 10000, // 10 second timeout
            success: function(data) {
                showMessage(data.message || `Cron schedule saved for valve ${valveId}`, 'success');
                // Reload the schedule to show updated values
                loadValveCronSchedule(valveId);
            },
            error: function(xhr, status, error) {
                const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : error || 'Unknown error';
                showMessage('Error saving cron schedule: ' + errorMessage, 'error');
            }
        });
    }
    
    // Function to clear valve cron schedule
    function clearValveCronSchedule(valveId) {
        // Clear the cron builder (if it exists)
        if (window.cronBuilder && window.cronBuilder[valveId]) {
            window.cronBuilder[valveId].reset();
        }
        
        // Clear the duration input
        $(`#cron-duration${valveId}`).val(1);  // Default to 1 minute
        $(`#enabled${valveId}`).prop('checked', false);
        
        // Show status message
        $(`#cron${valveId}-status`).html('<p class="text-muted">Schedule cleared</p>');
    }
    
    // Function to display valve history with better UX
    function displayValveHistory(valveId, history) {
        const historyContainer = $(`#history${valveId}`);
        
        if (!history || history.length === 0) {
            historyContainer.html('<p class="text-muted">No operation history available</p>');
            return;
        }
        
        let historyHtml = '<ul class="list-group list-group-flush">';
        
        // Show only the most recent 5 operations
        const recentHistory = history.slice(0, 5);
        
        recentHistory.forEach(log => {
            const timestamp = new Date(log.timestamp);
            const formattedTime = timestamp.toLocaleString();
            
            let durationText = '';
            if (log.duration !== null && log.duration !== undefined && log.status != 'Opened') {
                const minutes = Math.floor(log.duration / 60);
                durationText = ` ${minutes} minutes`;
            } else if (log.duration === 0 && log.status === 'Opened') {
                // If duration is 0, it means the valve was opened but not yet closed
                durationText = ' (still open)';
            } else if (log.duration === null || log.duration === undefined) {
                // If duration is not set, don't show anything
                durationText = '';
            }
            
            const operationClass = log.status === 'Opened' ? 'text-success' : 'text-danger';
            const operationText = log.status;
            
            // If it's an open event, show the start time in the required format
            let startTimeText = '';
            if (log.start_time) {
                const startTime = new Date(log.start_time);
                // Format as: "Tuesday 23 December at 19:50"
                const options = { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' };
                startTimeText = startTime.toLocaleString('en-US', options);
            }
            
            historyHtml += `
                <li class="list-group-item">
                    <div class="d-flex justify-content-between">
                        <span class="${operationClass}">${operationText}</span>
                        <small class="text-muted">${startTimeText}</small>
                    </div>
                    <small class="text-muted">${durationText}</small>
                </li>
            `;
        });
        
        historyHtml += '</ul>';
        historyContainer.html(historyHtml);
    }
    
    // Function to get valve history with better error handling
    function getValveHistory(valveId) {
        $.ajax({
            url: `${API_BASE_URL}/valves/${valveId}/history`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                displayValveHistory(valveId, data.history);
            },
            error: function(xhr, status, error) {
                const historyContainer = $(`#history${valveId}`);
                historyContainer.html('<p class="text-danger">Error loading history</p>');
                console.error(`Error fetching history for valve ${valveId}:`, error);
            }
        });
    }
    
    // Function to get all valve histories with better error handling
    function getAllValveHistories() {
        for (let valveId = 1; valveId <= 2; valveId++) {
            getValveHistory(valveId);
        }
    }
    
    // Initialize valve histories
    getAllValveHistories();
    
    // Function to get and display valve usage statistics
    function getValveUsage() {
        $.ajax({
            url: `${API_BASE_URL}/valves/usage`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                if (data && data.valves) {
                    // Display usage stats for each valve
                    for (let valveId = 1; valveId <= 2; valveId++) {
                        const usageData = data.valves[valveId];
                        const usageElement = $(`#valve${valveId}-usage`);
                        
                        if (usageData && Object.keys(usageData).length > 0) {
                            // Get the most recent date (today or most recent day)
                            const dates = Object.keys(usageData).sort().reverse();
                            const mostRecentDate = dates[0];
                            const minutes = usageData[mostRecentDate];
                            
                            usageElement.html(`<div class="valve-usage-text">Valve ${valveId}: ${minutes} min</div>`);
                        } else {
                            usageElement.html(`<div class="valve-usage-text">Valve ${valveId}: 0 min</div>`);
                        }
                    }
                }
            },
            error: function(xhr, status, error) {
                console.error('Error fetching valve usage data:', error);
                // Display default text if error occurs
                for (let valveId = 1; valveId <= 2; valveId++) {
                    const usageElement = $(`#valve${valveId}-usage`);
                    usageElement.html(`<div class="valve-usage-text">Valve ${valveId}: 0 min</div>`);
                }
            }
        });
    }
    
    // Call the function to get initial usage data
    getValveUsage();
    
    // Debug: Log when valve usage is initialized
    console.log("Valve usage initialization complete");
    
    // Remove auto-refresh for histories (no longer needed as it's triggered by status changes)
    // Previously: setInterval(getAllValveHistories, 30000);
    
    // Debug: Log when buttons are initialized
    console.log("Button event handlers initialized");
    
    // Function to get and display weather forecast with better error handling
    function getWeatherForecast() {
        // First get valve usage data to ensure it's available
        getValveUsageForWeather().done(function() {
            // Then get next run times for valves
            $.ajax({
                url: `${API_BASE_URL}/valves/next_run`,
                method: 'GET',
                timeout: 10000, // 10 second timeout
                success: function(nextRunData) {
                    // Store next run data for later use in weather cards
                    window.nextRunData = nextRunData.next_runs || [];
                    // Then get weather data and display
                    $.ajax({
                        url: `${API_BASE_URL}/weather/daily`,
                        method: 'GET',
                        timeout: 10000, // 10 second timeout
                        success: function(data) {
                            if (data && data.daily) {
                                displayWeatherForecast(data.daily);
                            } else {
                                console.error('Invalid daily forecast data received');
                                // Display a message that weather data is not available
                                $('#weather-cards').html('<div class="col-12"><p class="text-center text-muted">Weather data not available</p></div>');
                            }
                        },
                        error: function(xhr, status, error) {
                            console.error('Error fetching weather daily forecast:', error);
                            // Display a message that weather data is not available
                            $('#weather-cards').html('<div class="col-12"><p class="text-center text-muted">Weather data not available</p></div>');
                        }
                    });
                },
                error: function(xhr, status, error) {
                    console.error('Error fetching valve next run times:', error);
                    // Proceed with weather data even if next run times are not available
                    $.ajax({
                        url: `${API_BASE_URL}/weather/daily`,
                        method: 'GET',
                        timeout: 10000, // 10 second timeout
                        success: function(data) {
                            if (data && data.daily) {
                                displayWeatherForecast(data.daily);
                            } else {
                                console.error('Invalid daily forecast data received');
                                // Display a message that weather data is not available
                                $('#weather-cards').html('<div class="col-12"><p class="text-center text-muted">Weather data not available</p></div>');
                            }
                        },
                        error: function(xhr, status, error) {
                            console.error('Error fetching weather daily forecast:', error);
                            // Display a message that weather data is not available
                            $('#weather-cards').html('<div class="col-12"><p class="text-center text-muted">Weather data not available</p></div>');
                        }
                    });
                }
            });
        });
    }
    
    // Function to get valve usage data for weather cards
    function getValveUsageForWeather() {
        return $.ajax({
            url: `${API_BASE_URL}/valves/usage`,
            method: 'GET',
            timeout: 10000, // 10 second timeout
            success: function(data) {
                if (data && data.valves) {
                    // Store the usage data for later use in weather cards
                    window.weatherValveUsage = data.valves;
                } else {
                    window.weatherValveUsage = {};
                }
            },
            error: function(xhr, status, error) {
                console.error('Error fetching valve usage data for weather:', error);
                window.weatherValveUsage = {};
            }
        });
    }
    
    // Function to display weather forecast cards with better UX
    function displayWeatherForecast(forecastList) {
        const weatherCardsContainer = $('#weather-cards');
        weatherCardsContainer.empty();
        
        // Get today's date for comparison (using UTC to avoid timezone issues)
        const today = new Date();
        today.setUTCHours(0, 0, 0, 0);
        
        // Create 12 cards: 6 for past, 1 for current, 5 for future
        const cards = [];
        
        // Add 6 past days (including today)
        for (let i = 6; i >= 0; i--) {
            const date = new Date(today);
            date.setUTCDate(today.getUTCDate() - i);
            cards.push({ date: date, index: i, type: 'past' });
        }
        
        // Add 5 future days
        for (let i = 1; i <= 5; i++) {
            const date = new Date(today);
            date.setUTCDate(today.getUTCDate() + i);
            cards.push({ date: date, index: i, type: 'future' });
        }
        
        // Process each card
        cards.forEach(card => {
            const date = card.date;
            const dateString = date.toISOString().split('T')[0];
            const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
            const monthName = date.toLocaleDateString('en-US', { month: 'short' });
            const dayNumber = date.getDate();
    
            // Find matching forecast data for this date (we'll match by date string)
            let forecastData = null;
            let hasData = false;
    
            // Look for data that matches this date (we'll match by date string)
            for (let i = 0; i < forecastList.length; i++) {
                const item = forecastList[i];
                // Compare dates as strings (YYYY-MM-DD format)
                if (item.date === dateString) {
                    forecastData = item;
                    hasData = true;
                    break;
                }
            }
    
            // Create card HTML
            let cardHtml = `
                <div class="col-md-5 mb-3">
                    <div class="card weather-card`;
            // Highlight current day
            if (card.type === 'past' && card.index === 0) {
                cardHtml += ` current-day`;
            }
        
            cardHtml += `">
                        <div class="card-body text-center">
                            <h5 class="card-title">${dayName}</h5>
                            <p class="card-text">${monthName} ${dayNumber}</p>
            `;
       
            if (hasData && forecastData) {
                // Use the actual database fields from the forecast data
                const temp_min = Math.round(forecastData.temperature_minimum);
                const temp_max = Math.round(forecastData.temperature_maximum);
                const humidity = forecastData.average_humidity;
                const description = forecastData.description;
                const icon = getWeatherIcon(description);
                const total_rain = forecastData.total_rain;
    
                // Show min and max temperatures for the day
                cardHtml += `
                    <div class="weather-icon">${icon}</div>
                    <p class="card-text min-temp">${temp_min}°C</p>
                    <p class="card-text max-temp">${temp_max}°C</p>
                    <p class="card-text">${humidity}% humidity</p>
                `;
    
                // Add rain information if available - positioned in top-left corner
                if (total_rain !== undefined) {
                    cardHtml += `
                        <p class="rain-info">Rain: ${total_rain.toFixed(2)} mm</p>
                    `;
                }
       
                // Add valve usage data in top-left corner (if available)
                if (window.weatherValveUsage) {
                    // Create a container for valve usage badges
                    let valveUsageContainer = '<div class="valve-usage-in-weather-card">';
                    // Check for each valve (1 and 2)
                    for (let valveId = 1; valveId <= 2; valveId++) {
                        if (window.weatherValveUsage[valveId] && window.weatherValveUsage[valveId][dateString]) {
                            const usageMinutes = window.weatherValveUsage[valveId][dateString];
                            if (usageMinutes > 0) {
                                valveUsageContainer += `
                                    <span class="valve-usage-badge" data-valve="${valveId}">
                                            Valve ${valveId}: ${usageMinutes} min
                                        </span>
                                    `;
                            }
                        }
                    }
                    valveUsageContainer += '</div>';
                    if (valveUsageContainer !== '<div class="valve-usage-in-weather-card"></div>') {
                        cardHtml += valveUsageContainer;
                    }
                }
           
                // Add next run information if available
                if (window.nextRunData && window.nextRunData.length > 0) {
                    let nextRunContainer = '<div class="next-run-in-weather-card">';
                    window.nextRunData.forEach(nextRun => {
                        if (nextRun.valve_id === 1 || nextRun.valve_id === 2) {
                            // The API returns next_runs as an array of 5 dates
                            // We need to iterate through all 5 dates for this valve
                            if (nextRun.next_runs && nextRun.next_runs.length > 0) {
                                nextRun.next_runs.forEach((nextRunDateStr, index) => {
                                    // Parse the next run date to check if it's for this day
                                    const nextRunDate = new Date(nextRunDateStr);
                                    const nextRunDateString = nextRunDate.toISOString().split('T')[0];
                                    if (nextRunDateString === dateString) {
                                        // Format the time for display
                                        const hours = nextRunDate.getHours().toString().padStart(2, '0');
                                        const minutes = nextRunDate.getMinutes().toString().padStart(2, '0');
                                        const formattedTime = `${hours}:${minutes}`;
      
                                        nextRunContainer += `
                                            <div class="next-run-badge" data-valve="${nextRun.valve_id}">
                                                Valve ${nextRun.valve_id}: ${formattedTime}
                                            </div>
                                        `;
                                    }
                                });
                            }
                        }
                    });
                    nextRunContainer += '</div>';
                    if (nextRunContainer !== '<div class="next-run-in-weather-card"></div>') {
                        cardHtml += nextRunContainer;
                    }
                }
                
                // Remove next run information from weather cards as per requirements
                // This section has been removed as per the task requirements
            } else {
                // Empty card with placeholder
                cardHtml += `
                    <div class="weather-icon">-</div>
                    <p class="card-text text-muted">No data</p>
                `;
            }
       
            cardHtml += `
                        </div>
                    </div>
                </div>
            `;
       
            weatherCardsContainer.append(cardHtml);
        });
    }
    
    // Function to get weather icon based on description with better error handling
    function getWeatherIcon(description) {
        if (!description) return '🌤️'; // Default icon if no description
        description = description.toLowerCase();
        
        if (description.includes('clear')) {
            return '☀️';
        } else if (description.includes('cloud')) {
            return '☁️';
        } else if (description.includes('rain')) {
            return '🌧️';
        } else if (description.includes('snow')) {
            return '❄️';
        } else if (description.includes('thunderstorm')) {
            return '⛈️';
        } else if (description.includes('fog') || description.includes('mist')) {
            return '🌫️';
        } else {
            return '🌤️'; // Default icon
        }
    }
    
    // Initialize weather forecast display
    getWeatherForecast();
    
    // Set up auto-refresh for weather every 30 minutes
    setInterval(getWeatherForecast, 1800000);
    
    // Initialize valve usage data
    getValveUsageForWeather();

    // Initialize cron builder components
    function initializeCronBuilder(valveId) {
        // Check if the container exists
        const container = document.getElementById(`cron${valveId}-builder`);
        if (!container) {
            console.error(`Container for cron builder ${valveId} not found`);
            return;
        }
    
        // Create new cron builder instance with unique builder ID
        window.cronBuilder = window.cronBuilder || {};
        try {
            window.cronBuilder[valveId] = new CronBuilder(`cron${valveId}-builder`, valveId);
            console.log(`Cron builder ${valveId} initialized successfully`);
        } catch (e) {
            console.error(`Failed to initialize cron builder ${valveId}:`, e);
            return;
        }
    
        if (window.cronBuilder[valveId]) {
            console.log(`Cron builder ${valveId} initialized successfully`);
        } else {
            console.error(`Failed to initialize cron builder ${valveId}`);
        }
    
        // When cron expression is applied, update the hidden input field
        // This is needed to maintain compatibility with existing API calls
        const cronExpressionInput = $(`#cron${valveId}`);
        const cronBuilderInstance = window.cronBuilder[valveId];
    
        // Set the initial value if it exists
        if (cronExpressionInput.val()) {
            cronBuilderInstance.setExpression(cronExpressionInput.val());
        }
    
        // Add event listener to update the hidden input when expression changes
        // This is a bit tricky since we don't have direct access to the builder's internal methods
        // But we can make sure the hidden input is updated when needed
    }

    // Initialize cron builder for both valves after page load
    $(document).ready(function() {
        // Make sure the cron builder is initialized properly
        if (typeof window.CronBuilder !== 'undefined') {
            initializeCronBuilder(1);
            initializeCronBuilder(2);
        } else {
            console.error('CronBuilder class is not available');
        }
    });

    // Ensure tabs are properly initialized after everything is loaded
    $(window).on('load', function() {
        // Make sure the first tab is active by default
        $('.nav-tabs .nav-link').first().addClass('active');
        $('.tab-pane').first().addClass('show');
    });

    // Initialize tab functionality after document ready
    $(document).ready(function() {
        // Ensure the first tab is active by default
        $('.nav-tabs .nav-link').first().addClass('active');
        $('.tab-pane').first().addClass('show');
    
        // Handle tab switching properly
        $('.nav-tabs a').on('click', function(e) {
            e.preventDefault();
            $(this).tab('show');
        });
    });

});