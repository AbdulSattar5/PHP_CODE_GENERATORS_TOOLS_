// static/js/api-client.js

/**
 * API Client for GenCode AI
 * Handles all HTTP requests to Django backend
 */

class APIClient {
    constructor() {
        this.baseURL = '/api';
        this.token = this.getAuthToken();
        // Long-running ERP generation needs more than default browser/network timeouts.
        this.requestTimeoutMs = 20 * 60 * 1000; // 20 minutes
    }

    /**
     * Get authentication token from localStorage or cookie
     */
    getAuthToken() {
        // Try localStorage first
        let token = localStorage.getItem('authToken');

        // If not in localStorage, try cookie
        if (!token) {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'authToken') {
                    token = value;
                    break;
                }
            }
        }

        return token;
    }

    /**
     * Get CSRF token from cookie
     */
    getCSRFToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return null;
    }

    /**
     * Build headers for requests
     */
    buildHeaders(includeContentType = true) {
        const headers = {
            'X-CSRFToken': this.getCSRFToken()
        };

        if (this.token) {
            headers['Authorization'] = `Token ${this.token}`;
        }

        if (includeContentType) {
            headers['Content-Type'] = 'application/json';
        }

        return headers;
    }

    /**
     * Generic request method
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;

        const defaultOptions = {
            headers: this.buildHeaders(!(options.body instanceof FormData)),
            credentials: 'same-origin',
            signal: AbortSignal.timeout(this.requestTimeoutMs)
        };

        const config = { ...defaultOptions, ...options };

        try {
            console.log(`Making API request to: ${url}`);
            const response = await fetch(url, config);

            // Handle different response types
            const contentType = response.headers.get('content-type');
            let data;

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                console.error(`API Error ${response.status}:`, data);
                throw {
                    status: response.status,
                    statusText: response.statusText,
                    data: data
                };
            }

            console.log(`API Success:`, data);
            return {
                success: true,
                data: data,
                status: response.status
            };

        } catch (error) {
            console.error('API Error:', error);

            const errorMessage = this.extractErrorMessage(error);

            // Handle timeout specifically (AbortError/TimeoutError/signal timed out variants)
            if (this.isTimeoutError(error, errorMessage)) {
                return {
                    success: false,
                    error: 'Request timed out. Generation is still running or taking too long. Please try again in a moment.',
                    status: 408
                };
            }

            // Extract meaningful error message
            return {
                success: false,
                error: errorMessage,
                status: error.status || 500
            };
        }
    }

    extractErrorMessage(error) {
        if (error?.data) {
            if (typeof error.data === 'string') {
                const raw = error.data.trim();
                if (raw) return raw;
            }

            if (typeof error.data === 'object') {
                const payload = error.data;

                if (typeof payload.error === 'string' && payload.error.trim()) {
                    return payload.error.trim();
                }
                if (typeof payload.message === 'string' && payload.message.trim()) {
                    return payload.message.trim();
                }
                if (typeof payload.detail === 'string' && payload.detail.trim()) {
                    return payload.detail.trim();
                }
                if (typeof payload.validation_reason === 'string' && payload.validation_reason.trim()) {
                    return payload.validation_reason.trim();
                }

                const validationError = this.extractValidationError(payload.validation_result);
                if (validationError) {
                    return validationError;
                }

                if (Array.isArray(payload.errors) && payload.errors.length > 0) {
                    return payload.errors.map((item) => String(item)).join(' | ');
                }

                for (const [key, value] of Object.entries(payload)) {
                    if (Array.isArray(value) && value.length > 0) {
                        return `${key}: ${value.map((item) => String(item)).join(' | ')}`;
                    }
                    if (typeof value === 'string' && value.trim()) {
                        return value.trim();
                    }
                }
            }
        }
        if (typeof error?.message === 'string' && error.message.trim()) {
            return error.message;
        }
        if (error?.status === 422) {
            return 'Request validation failed (422). Please check the prompt contract and required fields.';
        }
        return 'Network error';
    }

    extractValidationError(validationResult) {
        if (!validationResult || typeof validationResult !== 'object') {
            return '';
        }

        const buckets = [
            validationResult.errors,
            validationResult.critical_errors,
            validationResult.warnings
        ];

        for (const bucket of buckets) {
            if (Array.isArray(bucket) && bucket.length > 0) {
                return bucket.map((item) => String(item)).join(' | ');
            }
        }

        if (typeof validationResult.error === 'string' && validationResult.error.trim()) {
            return validationResult.error.trim();
        }

        return '';
    }

    isTimeoutError(error, extractedMessage = '') {
        const timeoutSignals = ['timeout', 'timed out', 'signal timed out', 'abort', 'aborted'];
        const message = String(extractedMessage || '').toLowerCase();
        const name = String(error?.name || '').toLowerCase();

        if (name === 'aborterror' || name === 'timeouterror') {
            return true;
        }
        return timeoutSignals.some(signal => message.includes(signal));
    }

    /**
     * GET request
     */
    async get(endpoint) {
        return this.request(endpoint, {
            method: 'GET'
        });
    }

    /**
     * POST request
     */
    async post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, data) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }

    /**
     * Upload file with progress tracking (multipart/form-data)
     */
    async upload(endpoint, formData, onProgress = null) {
        return new Promise((resolve, reject) => {
            const url = `${this.baseURL}${endpoint}`;
            const xhr = new XMLHttpRequest();

            // Track upload progress
            if (onProgress) {
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = (e.loaded / e.total) * 100;
                        onProgress(percentComplete);
                    }
                });
            }

            // Handle completion
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        resolve({
                            success: true,
                            data: data,
                            status: xhr.status
                        });
                    } catch (e) {
                        resolve({
                            success: true,
                            data: xhr.responseText,
                            status: xhr.status
                        });
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        resolve({
                            success: false,
                            error: error,
                            status: xhr.status
                        });
                    } catch (e) {
                        resolve({
                            success: false,
                            error: xhr.responseText,
                            status: xhr.status
                        });
                    }
                }
            });

            // Handle errors
            xhr.addEventListener('error', () => {
                reject({
                    success: false,
                    error: 'Network error occurred',
                    status: 0
                });
            });

            // Handle timeout
            xhr.addEventListener('timeout', () => {
                reject({
                    success: false,
                    error: 'Upload timed out',
                    status: 408
                });
            });

            // Set timeout (5 minutes for large files)
            xhr.timeout = 300000;

            // Open connection
            xhr.open('POST', url);

            // Set headers
            xhr.setRequestHeader('X-CSRFToken', this.getCSRFToken());
            if (this.token) {
                xhr.setRequestHeader('Authorization', `Token ${this.token}`);
            }

            // Send request
            xhr.send(formData);
        });
    }

    // ==================== 
    // PROJECT ENDPOINTS
    // ==================== 

    async getProjects() {
        return this.get('/projects/');
    }

    async getProject(projectId) {
        return this.get(`/projects/${projectId}/`);
    }

    async createProject(data) {
        return this.post('/projects/', data);
    }

    async updateProject(projectId, data) {
        return this.put(`/projects/${projectId}/`, data);
    }

    async deleteProject(projectId) {
        return this.delete(`/projects/${projectId}/`);
    }

    async getProjectCodes(projectId) {
        console.log('🔗 API: Getting project codes for:', projectId);
        const result = await this.get(`/projects/${projectId}/generated_codes/`);
        console.log('🔗 API: Project codes result:', result);
        return result;
    }

    async getConversationHistory(projectId) {
        return this.get(`/projects/${projectId}/conversation_history/`);
    }

    async clearConversationHistory(projectId) {
        return this.delete(`/projects/${projectId}/clear_history/`);
    }

    async downloadProjectCode(projectId) {
        return this.post(`/projects/${projectId}/download_code/`, {});
    }

    // ==================== 
    // CODE GENERATION ENDPOINTS
    // ==================== 

    async generateCode(data) {
        return this.post('/generate/', data);
    }

    async validateCode(data) {
        return this.post('/validate/', data);
    }

    async regenerateCode(data) {
        return this.post('/regenerate/', data);
    }

    // ==================== 
    // CODEBASE ENDPOINTS
    // ==================== 

    async getCodebases() {
        return this.get('/codebases/');
    }

    async uploadCodebase(formData) {
        return this.upload('/codebases/upload/', formData);
    }

    async deleteCodebase(codebaseId) {
        return this.delete(`/codebases/${codebaseId}/`);
    }

    async getCodebaseStatus(codebaseId) {
        return this.get(`/codebases/${codebaseId}/indexing_status/`);
    }

    async getCodebaseStatistics() {
        return this.get('/codebases/statistics/');
    }

    // ==================== 
    // STANDARDS ENDPOINTS
    // ==================== 

    async getStandards() {
        return this.get('/standards/');
    }

    async getStandard(standardsId) {
        return this.get(`/standards/${standardsId}/`);
    }

    async uploadStandards(formData) {
        return this.upload('/standards/upload/', formData);
    }

    async activateStandards(standardsId) {
        return this.post(`/standards/${standardsId}/activate/`, {});
    }

    async getActiveStandards() {
        return this.get('/standards/active/');
    }

    async deleteStandards(standardsId) {
        return this.delete(`/standards/${standardsId}/`);
    }
}

// Create global instance
const api = new APIClient();
