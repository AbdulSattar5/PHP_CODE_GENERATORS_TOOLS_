// static/js/code-generation.js

/**
 * Code Generation Controller
 * Manages the code generation workflow
 */

let currentProject = null;
let currentCodebase = null;
let generatedCode = {};
let currentLanguage = 'complete_php';
let isGenerating = false; // 🆕 ISSUE #6 FIX: Prevent concurrent requests
let isCodeCanvasCollapsed = false;

/**
 * Initialize page
 */
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Page initialized, loading projects and codebases...');
    await loadProjects();
    await loadCodebases();
    await loadPatternStats(); // Load pattern statistics
    await loadDatabaseConnections(); // Load database connections
    setupEventListeners();
    updateSendButtonState();
    syncCodeCanvasToggleState(false);

    // Check if project ID is in URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const projectId = urlParams.get('project');
    console.log('🔍 URL project parameter:', projectId);

    if (projectId) {
        console.log('🎯 Setting current project from URL:', projectId);
        // Set current project and load its data
        currentProject = projectId;

        // Set the dropdown value
        const projectSelect = document.getElementById('projectSelect');
        if (projectSelect) {
            projectSelect.value = projectId;
            console.log('📋 Set dropdown value to:', projectId);
        } else {
            console.log('❌ Project select dropdown not found');
        }

        // Load conversation history and generated code
        console.log('📞 Loading conversation history for URL project...');
        await loadConversationHistory();

        console.log('✅ Loaded project from URL:', projectId);
    } else {
        console.log('ℹ️ No project ID in URL parameters');
    }
});

/**
 * Load pattern statistics and display count
 */
async function loadPatternStats() {
    try {
        const response = await api.getCodebaseStatistics();

        if (response.success) {
            const stats = response.data;
            const patternsCountEl = document.getElementById('patternsCount');

            if (stats.total_codebases > 0 && stats.pattern_stats.total_patterns > 0) {
                patternsCountEl.textContent = `(${stats.pattern_stats.total_patterns} patterns available)`;
                patternsCountEl.style.color = 'var(--success-color)';
                console.log(`✅ ${stats.pattern_stats.total_patterns} patterns available from ${stats.total_codebases} codebase(s)`);
            } else {
                patternsCountEl.innerHTML = `(<a href="/codebase/" style="color: var(--warning-color);">Upload codebase</a>)`;
                console.log('⚠️ No patterns available. Upload a codebase first.');
            }
        }
    } catch (error) {
        console.warn('Could not load pattern stats:', error);
    }
}

/**
 * Load projects from API
 */
async function loadProjects() {
    console.log('📋 Loading projects...');
    try {
        const response = await api.getProjects();
        console.log('📋 Projects API response:', response);

        if (response.success) {
            const projectSelect = document.getElementById('projectSelect');

            // Clear existing options
            projectSelect.innerHTML = '<option value="">-- Create New Project --</option>';

            // Get projects from response (handle both direct array and paginated response)
            const projects = response.data.results || response.data || [];
            console.log('📋 Found projects:', projects.length);

            // Add projects
            projects.forEach(project => {
                const option = document.createElement('option');
                option.value = project.id;
                option.textContent = project.name;
                projectSelect.appendChild(option);
                console.log('📋 Added project option:', project.id, '-', project.name);
            });

            // Remove existing event listeners to prevent duplicates
            const newSelect = projectSelect.cloneNode(true);
            projectSelect.parentNode.replaceChild(newSelect, projectSelect);

            // Add event listener for project selection
            newSelect.addEventListener('change', async (e) => {
                const selectedValue = e.target.value;
                console.log('📋 Project selected:', selectedValue);

                if (selectedValue) {
                    currentProject = selectedValue;
                    console.log('📋 Current project set to:', currentProject);
                    await loadConversationHistory();
                    showNotification(`Project selected: ${e.target.options[e.target.selectedIndex].text}`, 'success');
                } else {
                    currentProject = null;
                    console.log('📋 No project selected');
                    chatManager.clearMessages();
                }
            });

            console.log(`✅ Loaded ${projects.length} projects`);
        } else {
            console.error('❌ Failed to load projects:', response.error);
            showNotification('Failed to load projects', 'error');
        }
    } catch (error) {
        console.error('❌ Error loading projects:', error);
        showNotification('Error loading projects', 'error');
    }
}

async function loadCodebases() {
    console.log('📦 Loading codebases...');
    try {
        const response = await api.getCodebaseStatistics();
        console.log('📦 Codebases API response:', response);

        if (response.success) {
            const codebaseSelect = document.getElementById('codebaseSelect');
            const stats = response.data;

            // Clear existing options
            codebaseSelect.innerHTML = '<option value="">-- All Codebases --</option>';

            // Get codebases list
            if (stats.codebases && Array.isArray(stats.codebases)) {
                stats.codebases.forEach(codebase => {
                    const option = document.createElement('option');
                    option.value = codebase.id;
                    option.textContent = `${codebase.name} (${codebase.file_count || 0} files)`;
                    codebaseSelect.appendChild(option);
                    console.log('📦 Added codebase option:', codebase.id, '-', codebase.name);
                });
            }

            // Add event listener for codebase selection
            codebaseSelect.addEventListener('change', (e) => {
                const selectedValue = e.target.value;
                console.log('📦 Codebase selected:', selectedValue);
                currentCodebase = selectedValue || null;
            });

            console.log(`✅ Loaded ${stats.total_codebases || 0} codebases`);
        } else {
            console.error('❌ Failed to load codebases:', response.error);
        }
    } catch (error) {
        console.error('❌ Error loading codebases:', error);
    }
}

/**
 * Load conversation history for selected project
 */
async function loadConversationHistory() {
    console.log('🔄 loadConversationHistory called, currentProject:', currentProject);

    if (!currentProject) {
        console.log('❌ No current project set, returning');
        return;
    }

    try {
        // Load conversation history
        console.log('📞 Loading conversation history for project:', currentProject);
        const historyResponse = await api.getConversationHistory(currentProject);
        console.log('📞 History response:', historyResponse);

        if (historyResponse.success && historyResponse.data.length > 0) {
            chatManager.clearMessages();

            historyResponse.data.forEach(msg => {
                if (msg.role === 'user') {
                    chatManager.addUserMessage(msg.content);
                } else {
                    chatManager.addAssistantMessage(msg.content);
                }
            });
        }

        // Load generated codes for this project
        console.log('📞 Loading generated codes for project:', currentProject);
        const codesResponse = await api.getProjectCodes(currentProject);
        console.log('📞 Codes response:', codesResponse);

        if (codesResponse.success && codesResponse.data.length > 0) {
            console.log('✅ Loading generated codes:', codesResponse.data.length, 'files found');

            // Group codes by generation session (timestamp within 2 minutes = same session)
            const codeGenerations = groupCodesByGeneration(codesResponse.data);
            console.log('📦 Grouped into', codeGenerations.length, 'generation sessions');

            // Store all generations globally so viewCodeGeneration() can access them
            allCodeGenerations = codeGenerations;

            // Display all code generations in chat as assistant messages
            codeGenerations.forEach((generation, index) => {
                const generationNumber = codeGenerations.length - index;
                const timestamp = new Date(generation.timestamp).toLocaleString();
                const fileCount = generation.codes.length;
                const types = generation.codes.map(c => c.code_type.toUpperCase()).join(', ');

                // Build a summary message for this generation
                chatManager.addAssistantMessage(
                    `✅ Code Generation #${generationNumber} (${timestamp})\nGenerated ${fileCount} file(s): ${types}`,
                    {
                        actions: [
                            {
                                icon: 'fas fa-eye',
                                text: `View Code #${generationNumber}`,
                                onClick: `viewCodeGeneration(${index})`
                            }
                        ]
                    }
                );
            });

            // Set the most recent generation as the active one in code panel
            const latestGeneration = codeGenerations[0];
            const latestCodes = {};
            latestGeneration.codes.forEach(codeFile => {
                latestCodes[codeFile.code_type] = codeFile.code_content;
            });

            // If we have generated code, display it
            if (Object.keys(latestCodes).length > 0) {
                console.log('🎯 Setting generatedCode and displaying...');
                generatedCode = latestCodes;

                // Display the code
                const mockData = {
                    generated_files: latestCodes
                };
                console.log('🎨 Calling displayGeneratedCode with:', Object.keys(latestCodes));
                displayGeneratedCode(mockData);

                // Show download and copy buttons
                const downloadBtn = document.getElementById('downloadBtn');
                if (downloadBtn) {
                    downloadBtn.style.display = 'inline-flex';
                    console.log('👆 Download button shown');
                } else {
                    console.log('❌ Download button not found');
                }

                console.log('✅ Loaded generated code:', Object.keys(latestCodes));
                showNotification('Previous generated code loaded', 'info');
            } else {
                console.log('❌ No code files to display');
            }
        } else {
            console.log('❌ No generated codes found or API failed');
            if (!codesResponse.success) {
                console.log('❌ API Error:', codesResponse.error);
            }
        }

    } catch (error) {
        console.error('❌ Error loading conversation history or codes:', error);
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // User input state listeners (Enter/Shift+Enter handled by ChatManager)
    const userInput = document.getElementById('userInput');
    const composerForm = document.getElementById('composerForm');

    if (composerForm) {
        composerForm.addEventListener('submit', handleComposerSubmit);
    }

    if (userInput) {
        userInput.addEventListener('input', () => {
            updateSendButtonState();
        });
        userInput.addEventListener('composer:input-state', () => {
            updateSendButtonState();
        });
        // Fallback: if ChatManager key handler misses, still allow Enter to submit.
        userInput.addEventListener('keydown', (e) => {
            if (e.defaultPrevented) return;
            const isEnter = e.key === 'Enter' || e.code === 'Enter' || e.code === 'NumpadEnter';
            if (isEnter && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                handleComposerSubmit();
            }
        });
    }

    // Handle window resize for tab visibility
    window.addEventListener('resize', debounceTabResize);
    window.addEventListener('resize', debounceCodeCanvasResize);

    document.addEventListener('click', handleComposerOptionsOutsideClick);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeComposerOptions();
        }
    });
}

/**
 * Debounced function to handle tab visibility on resize
 */
const debounceTabResize = debounce(() => {
    // Ensure active tab is visible after resize
    const activeTab = document.querySelector('.tab-btn.active');
    if (activeTab) {
        activeTab.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest',
            inline: 'center'
        });
    }
}, 250);

const debounceCodeCanvasResize = debounce(() => {
    syncCodeCanvasToggleState(isCodeCanvasCollapsed);
}, 250);

/**
 * Debounce utility function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Main code generation function
 */
async function generateCode() {
    // 🆕 ISSUE #6 FIX: Prevent concurrent requests
    if (isGenerating) {
        console.warn('⚠️ Generation already in progress, ignoring duplicate request');
        showNotification('Code generation already in progress...', 'info');
        return;
    }

    const userInputEl = document.getElementById('userInput');
    const userInput = userInputEl?.value.trim() || '';

    console.log('=== CODE GENERATION DEBUG ===');
    console.log('User input:', userInput);
    console.log('Current project:', currentProject);

    if (!userInput) {
        showNotification('Please enter a description', 'warning');
        return;
    }

    // Check if project is selected
    if (!currentProject) {
        showNotification('Please select or create a project first', 'warning');
        showNewProjectModal();
        return;
    }

    // 🆕 ISSUE #6 FIX: Set lock flag
    isGenerating = true;

    // Get options
    const usePatterns = document.getElementById('usePatterns').checked;
    const useStandards = document.getElementById('useStandards').checked;
    const databaseConnectionId = document.getElementById('databaseConnection').value;
    const autoExecuteSQL = document.getElementById('autoExecuteSQL').checked;

    console.log('Options:', { usePatterns, useStandards, databaseConnectionId, autoExecuteSQL });

    // Add user message and clear composer immediately on submit (ChatGPT-like).
    chatManager.addUserMessage(userInput);
    if (window.chatManager && typeof window.chatManager.resetComposer === 'function') {
        window.chatManager.resetComposer();
    } else if (userInputEl) {
        userInputEl.value = '';
        userInputEl.style.height = '';
        userInputEl.style.overflowY = 'hidden';
    }
    updateSendButtonState();

    // Check if user has uploaded codebases
    if (usePatterns) {
        try {
            const statsResponse = await api.getCodebaseStatistics();
            if (statsResponse.success) {
                const stats = statsResponse.data;
                if (stats.total_codebases === 0) {
                    showNotification('No codebases uploaded yet. Upload your company code to use patterns!', 'warning');
                } else {
                    console.log(`Using patterns from ${stats.total_codebases} codebase(s) with ${stats.pattern_stats.total_patterns} patterns`);
                }
            }
        } catch (e) {
            console.warn('Could not check codebase stats:', e);
        }
    }

    // Disable send button
    const sendBtn = document.getElementById('sendBtn');
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.classList.add('is-loading');
        sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    // Show typing indicator
    chatManager.showTypingIndicator();

    // Show loading overlay on code panel
    showLoadingOverlay();

    try {
        console.log('Sending API request...');
        const response = await api.generateCode({
            user_request: userInput,
            project_id: currentProject,
            codebase_id: currentCodebase,
            use_company_patterns: usePatterns,
            use_standards: useStandards,
            database_connection_id: databaseConnectionId || null,
            auto_execute_sql: autoExecuteSQL
        });

        console.log('API response:', response);

        // Hide typing indicator
        chatManager.hideTypingIndicator();
        hideLoadingOverlay();

        if (response.success) {
            // Store generated code
            generatedCode = response.data.generated_files || {};
            console.log('Generated files:', Object.keys(generatedCode));
            const apiStatus = String(response?.data?.status || '').toLowerCase();
            const hasGeneratedFiles = Object.keys(generatedCode).length > 0;
            const validationMode = String(response?.data?.validation_result?.mode || '').toLowerCase();
            const metadataType = String(response?.data?.metadata?.generation_type || '').toLowerCase();
            const inlineMeta = response?.data?.metadata?.inline_generation_metadata || {};
            const attemptsMade = Number(response?.data?.metadata?.attempts_made || inlineMeta.attempts_made || 0);
            const maxAttempts = Number(response?.data?.metadata?.max_attempts || inlineMeta.max_attempts || 0);
            const refusalCount = Number(response?.data?.metadata?.refusal_count || inlineMeta.refusal_count || 0);
            const llmCallFailures = Number(response?.data?.metadata?.llm_call_failures || inlineMeta.llm_call_failures || 0);
            const fallbackUsed = Boolean(
                response?.data?.fallback_used ||
                validationMode.includes('fallback') ||
                metadataType.includes('fallback') ||
                String(response?.data?.message || '').toLowerCase().includes('fallback')
            );

            if (hasGeneratedFiles) {
                if (apiStatus === 'error') {
                    chatManager.addAssistantMessage(
                        'Code was returned in degraded mode (fallback). Please review before production use.'
                    );
                    showNotification('Generated with fallback mode', 'warning');
                } else if (fallbackUsed) {
                    chatManager.addAssistantMessage(
                        'Code was generated using fallback safety mode. Review patterns carefully before deployment.'
                    );
                    showNotification('Fallback output generated', 'warning');
                } else {
                    // Show success message for non-fallback runs
                    chatManager.addSuccessMessage(response.data);
                    showNotification('Code generated successfully!', 'success');
                }

                if (attemptsMade > 1) {
                    const attemptText = maxAttempts > 0 ? `${attemptsMade}/${maxAttempts}` : `${attemptsMade}`;
                    chatManager.addAssistantMessage(`Backend retry summary: completed in ${attemptText} attempts.`);
                }
                if (refusalCount > 0 || llmCallFailures > 0) {
                    chatManager.addAssistantMessage(
                        `Generation health: refusals=${refusalCount}, provider_failures=${llmCallFailures}.`
                    );
                }

                // Display code for both normal and fallback outputs
                displayGeneratedCode(response.data);

                // Show validation panel
                if (response.data.validation_result) {
                    showValidationPanel(response.data.validation_result, response.data.validation_score);
                }

                // Enable download button
                document.getElementById('downloadBtn').style.display = 'inline-flex';
            } else {
                console.log('No code files generated');
                const responseMessage = response?.data?.message || 'No code was generated. Please try again with a more specific request.';
                chatManager.addErrorMessage(responseMessage);
                showNotification('No code generated', 'warning');
            }

        } else {
            console.error('Code generation failed:', response.error);
            const statusCode = Number(response?.status || 0);
            const baseMessage = String(response?.error || '').trim();
            const effectiveMessage = baseMessage || (statusCode === 422
                ? 'Request validation failed. Please check required prompt fields.'
                : 'Code generation failed');

            chatManager.addErrorMessage(effectiveMessage);
            if (statusCode === 422) {
                showNotification(`Prompt validation failed (422): ${effectiveMessage}`, 'warning');
            } else {
                showNotification('Code generation failed: ' + effectiveMessage, 'error');
            }
        }

    } catch (error) {
        console.error('Generation error:', error);
        chatManager.hideTypingIndicator();
        hideLoadingOverlay();

        const errorName = String(error?.name || '');
        const errorMessage = String(error?.message || '');
        const loweredMessage = errorMessage.toLowerCase();
        const isTimeout = (
            errorName === 'AbortError' ||
            errorName === 'TimeoutError' ||
            loweredMessage.includes('timeout') ||
            loweredMessage.includes('timed out') ||
            loweredMessage.includes('signal timed out')
        );

        if (isTimeout) {
            chatManager.addErrorMessage('Request timed out. Code generation can take 2-3 minutes for complex requests. Please try again or simplify your request.');
            showNotification('Request timed out - try a simpler request', 'warning');
        } else {
            chatManager.addErrorMessage('An unexpected error occurred: ' + errorMessage);
            showNotification('An error occurred: ' + errorMessage, 'error');
        }
    } finally {
        // Re-enable send button
        if (sendBtn) {
            sendBtn.classList.remove('is-loading');
            sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
        }

        // Composer is cleared on submit (above), not on completion.

        // 🆕 ISSUE #6 FIX: Release lock flag
        isGenerating = false;
        updateSendButtonState();
    }
}

/**
 * Display generated code in the code panel
 * SIMPLIFIED: Only handles complete_php now
 */
function displayGeneratedCode(data) {
    // Get generated code - should only be complete_php
    const generatedFiles = data.generated_files || {};

    if (!generatedFiles.complete_php) {
        console.error('No complete_php code found in response');
        showNotification('No code generated', 'warning');
        return;
    }

    generatedCode.complete_php = generatedFiles.complete_php;

    // Set current language to complete_php
    currentLanguage = 'complete_php';

    createCodeTabs(['complete_php']);
    syncCodeCanvasToggleState(false);

    // Display the complete PHP code
    switchCodeTab('complete_php');
}

/**
 * Create code tabs dynamically based on available languages
 * SIMPLIFIED: Only creates Complete PHP tab now
 */
function createCodeTabs(languages) {
    const tabsContainer = document.getElementById('codeTabs');

    // Clear existing tabs
    tabsContainer.innerHTML = '';

    // Create only Complete PHP tab
    const tabButton = document.createElement('button');
    tabButton.className = 'tab-btn active';
    tabButton.setAttribute('data-lang', 'complete_php');
    tabButton.onclick = () => switchCodeTab('complete_php');

    tabButton.innerHTML = `
        <i class="fas fa-file-code"></i> Complete PHP
        <span class="tab-copy-btn" onclick="event.stopPropagation(); copySpecificCode('complete_php')" title="Copy Complete PHP" aria-label="Copy Complete PHP" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();copySpecificCode('complete_php');}">
            <i class="fas fa-copy"></i>
        </span>
    `;

    tabsContainer.appendChild(tabButton);
}

/**
 * Switch code tab
 * SIMPLIFIED: Only handles complete_php now
 */
function switchCodeTab(language) {
    currentLanguage = 'complete_php'; // Always complete_php

    // Update active tab
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.lang === 'complete_php') {
            btn.classList.add('active');
        }
    });

    // Display code
    const codeContent = document.getElementById('codeContent');
    if (!codeContent) return;

    const code = generatedCode['complete_php'] || 'No code generated';

    // Create highlighted code block
    codeContent.innerHTML = `
        <div class="code-block-container cgpt-code-block-container">
            <div class="code-block-header cgpt-code-block-header">
                <span class="code-language">Complete PHP</span>
                <div class="code-block-actions">
                    <button class="btn btn-sm btn-copy" onclick="copyIndividualCode('complete_php')" title="Copy Complete PHP code">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
            </div>
            <pre class="cgpt-code-pre"><code class="language-php">${escapeHtml(code)}</code></pre>
        </div>
    `;

    // Apply syntax highlighting
    const codeNode = codeContent.querySelector('code');
    if (codeNode && window.hljs) {
        hljs.highlightElement(codeNode);
    }
}

/**
 * Update the copy all button
 * SIMPLIFIED: No longer needed since we only have one file type
 */
function updateCopyAllButton() {
    // No-op: Button text is static now ("Copy Code")
}



/**
 * Copy all generated code
 * SIMPLIFIED: Only copies complete_php now
 */
async function copyAllCode() {
    // Just copy the complete PHP code
    return copyCurrentCode();
}

/**
 * Copy current active tab code to clipboard
 * SIMPLIFIED: Only copies complete_php now
 */
async function copyCurrentCode() {
    const code = generatedCode['complete_php'];

    if (!code) {
        showNotification('No code to copy', 'warning');
        return;
    }

    try {
        await navigator.clipboard.writeText(code);

        // Update button text temporarily
        const copyBtn = document.getElementById('copyBtn');
        const originalHTML = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';

        setTimeout(() => {
            copyBtn.innerHTML = originalHTML;
        }, 2000);

        showNotification('Complete PHP code copied to clipboard', 'success');
    } catch (error) {
        console.error('Copy failed:', error);
        showNotification('Failed to copy code', 'error');
    }
}

/**
 * Copy specific language code to clipboard
 * SIMPLIFIED: Only handles complete_php now
 */
async function copySpecificCode(language) {
    // Always copy complete_php
    return copyCurrentCode();
}

/**
 * Copy code to clipboard (main copy button functionality)
 * SIMPLIFIED: Only copies complete_php now
 */
async function copyCode() {
    return copyCurrentCode();
}

/**
 * Copy individual code block
 * SIMPLIFIED: Only handles complete_php now
 */
async function copyIndividualCode(language) {
    return copyCurrentCode();
}

/**
 * REMOVED: Old duplicate copyAllCode function
 */
async function _oldCopyAllCode_removed() {
    // This function was causing issues - removed
    if (!generatedCode || Object.keys(generatedCode).length === 0) {
        showNotification('No code to copy', 'warning');
        return;
    }

    try {
        let allCode = '';
        const fileExtensions = {
            'sql': 'sql',
            'complete_php': 'php',
            'php': 'php',
            'html': 'html',
            'css': 'css',
            'js': 'js'
        };

        for (const [language, code] of Object.entries(generatedCode)) {
            if (code && code.trim()) {
                const extension = fileExtensions[language] || 'txt';
                const filename = `${language}.${extension}`;
                allCode += `\n\n// ==================== ${filename.toUpperCase()} ====================\n\n${code}`;
            }
        }

        if (allCode) {
            await navigator.clipboard.writeText(allCode.trim());

            // Update button text temporarily
            const copyAllBtn = document.getElementById('copyAllBtn');
            const originalHTML = copyAllBtn.innerHTML;
            copyAllBtn.innerHTML = '<i class="fas fa-check"></i> All Copied!';

            setTimeout(() => {
                copyAllBtn.innerHTML = originalHTML;
            }, 2000);

            showNotification('All code files copied to clipboard', 'success');
        } else {
            showNotification('No code to copy', 'warning');
        }
    } catch (error) {
        console.error('Copy all failed:', error);
        showNotification('Failed to copy code', 'error');
    }
}

/**
 * Download generated code as single PHP file
 * SIMPLIFIED: Only downloads complete_php now
 */
async function downloadCode() {
    if (!currentProject) {
        showNotification('No project selected', 'warning');
        return;
    }

    const code = generatedCode['complete_php'];

    if (!code || !code.trim()) {
        showNotification('No code to download', 'warning');
        return;
    }

    try {
        // Download as single PHP file
        downloadFile(code, `project_${currentProject}_generated.php`, 'text/plain');
        showNotification('PHP file downloaded successfully', 'success');
    } catch (error) {
        console.error('Download error:', error);
        showNotification('Download failed', 'error');
    }
}

/**
 * Alias for downloadCode
 */
async function downloadAllCode() {
    return downloadCode();
}

/**
 * Show/hide loading overlay
 */
function showLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (!overlay) return;
    overlay.style.display = 'flex';
    overlay.classList.add('is-active');
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (!overlay) return;
    overlay.classList.remove('is-active');
    overlay.style.display = 'none';
}

/**
 * Show validation panel
 */
function showValidationPanel(validationResult, score) {
    const panel = document.getElementById('validationPanel');
    if (!panel) return;
    panel.style.display = 'block';
    panel.classList.add('show');

    // Update score
    const scoreValue = document.getElementById('scoreValue');
    scoreValue.textContent = Math.round(score);

    // Animate score circle
    const scoreCircle = document.getElementById('scoreCircle');
    const degrees = (score / 100) * 360;
    scoreCircle.style.background = `conic-gradient(var(--secondary-color) ${degrees}deg, var(--bg-tertiary) 0deg)`;

    // Update status text
    const statusText = document.getElementById('scoreStatus').querySelector('.status-text');
    if (score >= 90) {
        statusText.textContent = 'Excellent';
        statusText.style.color = 'var(--secondary-color)';
    } else if (score >= 70) {
        statusText.textContent = 'Good';
        statusText.style.color = 'var(--info-color)';
    } else {
        statusText.textContent = 'Needs Improvement';
        statusText.style.color = 'var(--warning-color)';
    }

    // Display validation details
    const detailsContainer = document.getElementById('validationDetails');
    detailsContainer.innerHTML = '';

    if (validationResult && validationResult.all_issues) {
        const issues = validationResult.all_issues;

        // Critical issues
        if (issues.critical && issues.critical.length > 0) {
            issues.critical.forEach(issue => {
                detailsContainer.innerHTML += `
                    <div class="validation-item error">
                        <strong>Critical:</strong> ${issue.issue || issue}
                    </div>
                `;
            });
        }

        // Major issues
        if (issues.major && issues.major.length > 0) {
            issues.major.forEach(issue => {
                detailsContainer.innerHTML += `
                    <div class="validation-item warning">
                        <strong>Major:</strong> ${issue.issue || issue}
                    </div>
                `;
            });
        }

        // Success message if no issues
        if (issues.critical.length === 0 && issues.major.length === 0) {
            detailsContainer.innerHTML = `
                <div class="validation-item success">
                    <i class="fas fa-check-circle"></i> All quality checks passed!
                </div>
            `;
        }
    }
}

function closeValidation() {
    const panel = document.getElementById('validationPanel');
    if (!panel) return;
    panel.style.display = 'none';
    panel.classList.remove('show');
}

function showValidationDetails() {
    document.getElementById('validationPanel').style.display = 'block';
}

/**
 * Clear chat
 */
async function clearChat() {
    if (!currentProject) {
        chatManager.clearMessages();
        // Clear generated code display
        generatedCode = {};
        const codeContent = document.getElementById('codeContent');
        codeContent.innerHTML = `
            <div class="code-placeholder">
                <i class="fas fa-code fa-3x"></i>
                <p>Generated code will appear here</p>
                <p class="placeholder-hint">Run a prompt to preview generated PHP output.</p>
            </div>
        `;
        // Hide buttons
        document.getElementById('downloadBtn').style.display = 'none';
        return;
    }

    if (!confirm('Clear conversation history for this project?')) {
        return;
    }

    const response = await api.clearConversationHistory(currentProject);

    if (response.success) {
        chatManager.clearMessages();

        // Clear generated code display
        generatedCode = {};
        const codeContent = document.getElementById('codeContent');
        codeContent.innerHTML = `
            <div class="code-placeholder">
                <i class="fas fa-code fa-3x"></i>
                <p>Generated code will appear here</p>
                <p class="placeholder-hint">Run a prompt to preview generated PHP output.</p>
            </div>
        `;

        // Hide buttons
        document.getElementById('downloadBtn').style.display = 'none';

        showNotification('Conversation cleared', 'success');
    } else {
        showNotification('Failed to clear conversation', 'error');
    }
}

/**
 * Use example prompt
 */
function useExample(text) {
    const userInput = document.getElementById('userInput');
    if (!userInput) return;
    userInput.value = text;
    userInput.dispatchEvent(new Event('input', { bubbles: true }));
    if (window.chatManager && typeof window.chatManager.autoResizeTextarea === 'function') {
        window.chatManager.autoResizeTextarea();
    }
    userInput.focus();
    updateSendButtonState();
}

/**
 * New Project Modal
 */
function showNewProjectModal() {
    document.getElementById('newProjectModal').classList.add('show');
}

function closeNewProjectModal() {
    document.getElementById('newProjectModal').classList.remove('show');
    document.getElementById('newProjectForm').reset();
}

async function createProject(event) {
    event.preventDefault();

    const name = document.getElementById('projectName').value.trim();
    const description = document.getElementById('projectDescription').value.trim();

    if (!name) {
        showNotification('Please enter project name', 'warning');
        return;
    }

    try {
        const response = await api.createProject({
            name: name,
            description: description
        });

        if (response.success) {
            showNotification('Project created successfully', 'success');
            closeNewProjectModal();

            // Reload projects
            await loadProjects();

            // Automatically select the new project
            const projectSelect = document.getElementById('projectSelect');
            projectSelect.value = response.data.id;
            currentProject = response.data.id;

            // Clear chat for new project
            chatManager.clearMessages();

            showNotification(`Project "${name}" is now selected`, 'success');
        } else {
            showNotification('Failed to create project', 'error');
        }
    } catch (error) {
        console.error('Create project error:', error);
        showNotification('An error occurred', 'error');
    }
}

/**
 * Utility: Escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Utility: Show notification
 */
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.innerHTML = `
        <i class="fas fa-info-circle"></i>
        ${message}
        <button class="close-btn" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;

    // Add to messages container
    let container = document.querySelector('.messages-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'messages-container';
        document.body.appendChild(container);
    }

    container.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}
// NOTE: downloadCode is defined above (line ~636). downloadAllCode is the alias below.

/**
 * Group generated codes by generation session
 * Codes created within 2 minutes of each other are considered the same generation
 */
function groupCodesByGeneration(codes) {
    if (!codes || codes.length === 0) return [];

    // Sort by created_at descending (newest first)
    const sortedCodes = [...codes].sort((a, b) =>
        new Date(b.created_at) - new Date(a.created_at)
    );

    const generations = [];
    let currentGeneration = null;

    sortedCodes.forEach(code => {
        const codeTime = new Date(code.created_at);

        // Since list is newest-first, codeTime is always <= currentGeneration.timestamp
        // So we compute the absolute difference to check the 2-minute window.
        if (!currentGeneration ||
            Math.abs(new Date(currentGeneration.timestamp) - codeTime) > 120000) {
            currentGeneration = {
                timestamp: code.created_at,
                codes: []
            };
            generations.push(currentGeneration);
        }

        currentGeneration.codes.push(code);
    });

    return generations;
}

/**
 * Store all code generations for later viewing
 */
let allCodeGenerations = [];

/**
 * View a specific code generation
 */
function viewCodeGeneration(generationIndex) {
    if (!allCodeGenerations[generationIndex]) {
        console.error('Generation not found:', generationIndex);
        return;
    }

    const generation = allCodeGenerations[generationIndex];
    const codes = {};

    generation.codes.forEach(codeFile => {
        codes[codeFile.code_type] = codeFile.code_content;
    });

    // Update the code panel
    generatedCode = codes;
    displayGeneratedCode({ generated_files: codes });

    // Show notification
    const timestamp = new Date(generation.timestamp).toLocaleString();
    showNotification(`Viewing code generation from ${timestamp}`, 'info');
}


/**
 * Load database connections from API
 */
async function loadDatabaseConnections() {
    console.log('🗄️ Loading database connections...');
    try {
        const response = await fetch('/api/database-connections/', {
            headers: {
                'Authorization': `Bearer ${getAuthToken()}`
            }
        });

        if (!response.ok) {
            console.warn('⚠️ Could not load database connections');
            return;
        }

        const connections = await response.json();
        console.log('🗄️ Found database connections:', connections.length);

        const dbSelect = document.getElementById('databaseConnection');
        if (!dbSelect) {
            console.warn('⚠️ Database connection selector not found');
            return;
        }

        // Clear existing options
        dbSelect.innerHTML = '<option value="">-- No Database Selected --</option>';

        // Add connections
        connections.forEach(conn => {
            const option = document.createElement('option');
            option.value = conn.id;
            option.textContent = `${conn.name} (${conn.db_type.toUpperCase()})`;
            if (!conn.is_connected) {
                option.disabled = true;
                option.textContent += ' [Not Connected]';
            }
            dbSelect.appendChild(option);
        });

        // Set default connection if available
        const defaultConn = connections.find(c => c.is_default);
        if (defaultConn) {
            dbSelect.value = defaultConn.id;
            console.log('🗄️ Set default database connection:', defaultConn.name);
        }

        console.log(`✅ Loaded ${connections.length} database connections`);
    } catch (error) {
        console.warn('⚠️ Error loading database connections:', error);
    }
}

/**
 * Get authentication token
 */
function getAuthToken() {
    return localStorage.getItem('auth_token') || getCookie('auth_token') || '';
}

/**
 * Get cookie value
 */
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

function updateSendButtonState() {
    const sendBtn = document.getElementById('sendBtn');
    const userInput = document.getElementById('userInput');
    if (!sendBtn || !userInput) return;

    const hasText = userInput.value.trim().length > 0;
    sendBtn.disabled = isGenerating || !hasText;
    sendBtn.classList.toggle('is-ready', hasText && !isGenerating);
}

function handleComposerSubmit(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!isGenerating) {
        generateCode();
    }
}

function toggleComposerOptions(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    const panel = document.getElementById('composerOptionsPopover');
    const btn = document.getElementById('composerOptionsBtn');
    if (!panel || !btn) return;

    const willOpen = panel.hidden || !panel.classList.contains('show');
    if (willOpen) {
        panel.hidden = false;
        panel.setAttribute('aria-hidden', 'false');
        requestAnimationFrame(() => {
            panel.classList.add('show');
        });
    } else {
        closeComposerOptions();
    }
    btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    btn.classList.toggle('is-open', willOpen);
}

function closeComposerOptions() {
    const panel = document.getElementById('composerOptionsPopover');
    const btn = document.getElementById('composerOptionsBtn');
    if (!panel || !btn) return;

    if (!panel.classList.contains('show') && panel.hidden) {
        btn.setAttribute('aria-expanded', 'false');
        panel.setAttribute('aria-hidden', 'true');
        return;
    }

    panel.classList.remove('show');
    panel.setAttribute('aria-hidden', 'true');
    setTimeout(() => {
        if (!panel.classList.contains('show')) {
            panel.hidden = true;
        }
    }, 180);
    btn.setAttribute('aria-expanded', 'false');
    if (btn) btn.classList.remove('is-open');
}

function handleComposerOptionsOutsideClick(event) {
    const panel = document.getElementById('composerOptionsPopover');
    const btn = document.getElementById('composerOptionsBtn');
    if (!panel || !btn || panel.hidden) return;

    if (panel.contains(event.target) || btn.contains(event.target)) {
        return;
    }
    closeComposerOptions();
}

function isDesktopCodeCanvas() {
    return window.innerWidth > 1280;
}

function syncCodeCanvasToggleState(shouldCollapse) {
    const page = document.querySelector('.cgpt-generation-page');
    const toggleBtn = document.getElementById('codeCanvasToggleBtn');
    const expandBtn = document.getElementById('codeCanvasExpandBtn');
    if (!page || !toggleBtn || !expandBtn) return;

    if (!isDesktopCodeCanvas()) {
        isCodeCanvasCollapsed = false;
        page.classList.remove('canvas-collapsed');
        toggleBtn.style.display = 'none';
        expandBtn.style.display = 'none';
        return;
    }

    toggleBtn.style.display = 'inline-flex';
    isCodeCanvasCollapsed = Boolean(shouldCollapse);
    page.classList.toggle('canvas-collapsed', isCodeCanvasCollapsed);
    expandBtn.style.display = isCodeCanvasCollapsed ? 'inline-flex' : 'none';

    const icon = toggleBtn.querySelector('i');
    const label = toggleBtn.querySelector('span');
    if (icon) {
        icon.className = isCodeCanvasCollapsed ? 'fas fa-chevron-left' : 'fas fa-chevron-right';
    }
    if (label) {
        label.textContent = isCodeCanvasCollapsed ? 'Expand' : 'Collapse';
    }
}

function toggleCodeCanvas(forceOpen = false) {
    if (!isDesktopCodeCanvas()) return;
    if (forceOpen === true) {
        syncCodeCanvasToggleState(false);
        return;
    }
    syncCodeCanvasToggleState(!isCodeCanvasCollapsed);
}
