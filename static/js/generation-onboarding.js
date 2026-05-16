(function () {
    const setupState = {
        openai_api_key_configured: false,
        codebase_uploaded: false,
        codebase_indexed: false,
        codebase_failed: false,
        standards_available: false,
        project_selected: false
    };

    function readInitialState() {
        const node = document.getElementById('generation-setup-data');
        if (!node) return;

        try {
            Object.assign(setupState, JSON.parse(node.textContent));
        } catch (error) {
            console.warn('Could not parse generation setup data:', error);
        }
    }

    function selectedProject() {
        const projectSelect = document.getElementById('projectSelect');
        return (projectSelect?.value || '').trim();
    }

    function generationOptions() {
        return {
            usePatterns: document.getElementById('usePatterns')?.checked ?? true,
            useStandards: document.getElementById('useStandards')?.checked ?? true
        };
    }

    function buildBlockingMessage() {
        const options = generationOptions();

        if (!setupState.openai_api_key_configured) {
            return 'Please configure your own OpenAI API key before generating code.';
        }

        if (!setupState.project_selected) {
            return 'Please select or create a project first.';
        }

        if (options.usePatterns && !setupState.codebase_uploaded) {
            return 'Please upload your own company codebase first.';
        }

        if (options.usePatterns && setupState.codebase_failed) {
            return 'Codebase indexing failed. Please check your ZIP file and upload again.';
        }

        if (options.usePatterns && !setupState.codebase_indexed) {
            return 'Please upload and index your own codebase before using company-pattern generation.';
        }

        if (options.useStandards && !setupState.standards_available) {
            return 'Please add your own coding standards or continue without standards.';
        }

        return '';
    }

    function renderBadges() {
        setupState.project_selected = Boolean(selectedProject());

        const badgeMap = {
            openai_api_key_configured: 'setupStatusApi',
            codebase_indexed: 'setupStatusCodebase',
            standards_available: 'setupStatusStandards',
            project_selected: 'setupStatusProject'
        };

        Object.entries(badgeMap).forEach(([key, elementId]) => {
            const badge = document.getElementById(elementId);
            const row = document.querySelector(`.setup-checklist-item[data-setup-key="${key}"]`);
            if (!badge || !row) return;

            const passed = Boolean(setupState[key]);
            badge.textContent = passed ? 'Yes' : 'No';
            badge.classList.toggle('is-ready', passed);
            badge.classList.toggle('is-missing', !passed);
            row.classList.toggle('is-ready', passed);
            row.classList.toggle('is-missing', !passed);
        });
    }

    function renderAlerts() {
        const alerts = document.getElementById('setupChecklistAlerts');
        if (!alerts) return;

        const options = generationOptions();
        const messages = [];

        if (!setupState.openai_api_key_configured) {
            messages.push({ text: 'Please configure your own OpenAI API key before generating code.', level: 'warning' });
        }

        if (options.usePatterns) {
            if (!setupState.codebase_uploaded) {
                messages.push({ text: 'Please upload your own company codebase first.', level: 'muted' });
            } else if (setupState.codebase_failed) {
                messages.push({ text: 'Codebase indexing failed. Please check your ZIP file and upload again.', level: 'warning' });
            } else if (!setupState.codebase_indexed) {
                messages.push({ text: 'Please upload and index your own codebase before using company-pattern generation.', level: 'muted' });
            }
        }

        if (options.useStandards && !setupState.standards_available) {
            messages.push({ text: 'Please add your own coding standards or continue without standards.', level: 'muted' });
        }

        alerts.innerHTML = messages
            .map((item) => `<p class="setup-alert setup-alert-${item.level}">${item.text}</p>`)
            .join('');
    }

    function renderSetupChecklist() {
        renderBadges();
        renderAlerts();
    }

    async function syncRemoteSetupState() {
        if (typeof api === 'undefined') return;

        try {
            const codebaseResponse = await api.getCodebaseStatistics();
            if (codebaseResponse.success) {
                const data = codebaseResponse.data || {};
                const codebases = Array.isArray(data.codebases) ? data.codebases : [];
                setupState.codebase_uploaded = (data.total_codebases || 0) > 0;
                setupState.codebase_indexed = Boolean(
                    data.has_indexed_codebase ||
                    codebases.some((item) => item.is_indexed)
                );
                setupState.codebase_failed = Boolean(
                    data.has_failed_codebase ||
                    codebases.some((item) => item.index_status === 'failed')
                );
            }
        } catch (error) {
            console.warn('Could not refresh codebase setup state:', error);
        }

        try {
            const standardsResponse = await api.getStandards();
            if (standardsResponse.success) {
                const standards = standardsResponse.data?.results || standardsResponse.data || [];
                setupState.standards_available = Array.isArray(standards) && standards.length > 0;
            }
        } catch (error) {
            console.warn('Could not refresh standards setup state:', error);
        }

        renderSetupChecklist();
    }

    function installGenerationGuard() {
        if (typeof generateCode !== 'function') return;

        const originalGenerateCode = generateCode;
        const wrappedGenerateCode = async function (...args) {
            setupState.project_selected = Boolean(selectedProject());
            const blockingMessage = buildBlockingMessage();
            renderSetupChecklist();

            if (blockingMessage) {
                if (typeof showNotification === 'function') {
                    showNotification(blockingMessage, 'warning');
                }
                return;
            }

            return originalGenerateCode.apply(this, args);
        };

        generateCode = wrappedGenerateCode;
        window.generateCode = wrappedGenerateCode;
    }

    document.addEventListener('DOMContentLoaded', () => {
        readInitialState();
        renderSetupChecklist();
        installGenerationGuard();
        syncRemoteSetupState();
    });

    document.addEventListener('change', (event) => {
        if (
            event.target.id === 'projectSelect' ||
            event.target.id === 'usePatterns' ||
            event.target.id === 'useStandards'
        ) {
            renderSetupChecklist();
        }
    });
})();
