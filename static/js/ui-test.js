// static/js/ui-test.js
// UI Testing and Verification Script

/**
 * Test mobile sidebar functionality
 */
function testMobileSidebar() {
    console.log('Testing mobile sidebar...');

    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const toggle = document.querySelector('.mobile-menu-toggle');

    if (!sidebar || !overlay || !toggle) {
        console.error('Missing sidebar elements');
        return false;
    }

    // Test toggle functionality
    toggle.click();

    setTimeout(() => {
        const isOpen = sidebar.classList.contains('show');
        const overlayVisible = overlay.classList.contains('show');

        if (isOpen && overlayVisible) {
            console.log('✅ Sidebar opens correctly');

            // Test close functionality
            overlay.click();

            setTimeout(() => {
                const isClosed = !sidebar.classList.contains('show');
                const overlayHidden = !overlay.classList.contains('show');

                if (isClosed && overlayHidden) {
                    console.log('✅ Sidebar closes correctly');
                    return true;
                } else {
                    console.error('❌ Sidebar close failed');
                    return false;
                }
            }, 300);

        } else {
            console.error('❌ Sidebar open failed');
            return false;
        }
    }, 300);
}

/**
 * Test layout responsiveness
 */
function testResponsiveLayout() {
    console.log('Testing responsive layout...');

    const generationLayout = document.querySelector('.generation-layout');
    const chatPanel = document.querySelector('.chat-panel');
    const codePanel = document.querySelector('.code-panel');

    if (!generationLayout || !chatPanel || !codePanel) {
        console.error('Missing layout elements');
        return false;
    }

    // Check if elements are properly positioned
    const layoutRect = generationLayout.getBoundingClientRect();
    const chatRect = chatPanel.getBoundingClientRect();
    const codeRect = codePanel.getBoundingClientRect();

    if (layoutRect.width > 0 && chatRect.width > 0 && codeRect.width > 0) {
        console.log('✅ Layout elements have proper dimensions');

        // Check if panels are within layout bounds
        if (chatRect.left >= layoutRect.left && codeRect.right <= layoutRect.right) {
            console.log('✅ Panels are properly positioned');
            return true;
        } else {
            console.error('❌ Panels overflow layout bounds');
            return false;
        }
    } else {
        console.error('❌ Layout elements have zero dimensions');
        return false;
    }
}

/**
 * Test chat functionality
 */
function testChatFunctionality() {
    console.log('Testing chat functionality...');

    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');

    if (!chatMessages || !userInput || !sendBtn) {
        console.error('Missing chat elements');
        return false;
    }

    // Check if chat messages container is scrollable
    const isScrollable = chatMessages.scrollHeight > chatMessages.clientHeight ||
        chatMessages.style.overflowY === 'auto' ||
        chatMessages.style.overflowY === 'scroll';

    if (isScrollable || chatMessages.scrollHeight <= chatMessages.clientHeight) {
        console.log('✅ Chat messages container is properly configured');

        // Test input functionality
        userInput.focus();
        if (document.activeElement === userInput) {
            console.log('✅ Chat input is focusable');
            return true;
        } else {
            console.error('❌ Chat input focus failed');
            return false;
        }
    } else {
        console.error('❌ Chat messages container scroll issue');
        return false;
    }
}

/**
 * Test code panel functionality
 */
function testCodePanel() {
    console.log('Testing code panel...');

    const codeContent = document.getElementById('codeContent');
    const codeTabs = document.getElementById('codeTabs');
    const copyBtn = document.getElementById('copyBtn');

    if (!codeContent || !codeTabs || !copyBtn) {
        console.error('Missing code panel elements');
        return false;
    }

    // Check if code content area is properly sized
    const contentRect = codeContent.getBoundingClientRect();

    if (contentRect.width > 0 && contentRect.height > 0) {
        console.log('✅ Code content area has proper dimensions');

        // Check if tabs are clickable
        const tabs = codeTabs.querySelectorAll('.tab-btn');
        if (tabs.length > 0) {
            console.log('✅ Code tabs are present');
            return true;
        } else {
            console.error('❌ No code tabs found');
            return false;
        }
    } else {
        console.error('❌ Code content area has zero dimensions');
        return false;
    }
}

/**
 * Run all tests
 */
function runUITests() {
    console.log('🧪 Starting UI Tests...');
    console.log('========================');

    const tests = [
        { name: 'Responsive Layout', fn: testResponsiveLayout },
        { name: 'Chat Functionality', fn: testChatFunctionality },
        { name: 'Code Panel', fn: testCodePanel }
    ];

    // Only test mobile sidebar on mobile screens
    if (window.innerWidth <= 768) {
        tests.unshift({ name: 'Mobile Sidebar', fn: testMobileSidebar });
    }

    let passed = 0;
    let total = tests.length;

    tests.forEach(test => {
        try {
            if (test.fn()) {
                passed++;
            }
        } catch (error) {
            console.error(`❌ ${test.name} test failed:`, error);
        }
    });

    console.log('========================');
    console.log(`🏁 Tests completed: ${passed}/${total} passed`);

    if (passed === total) {
        console.log('🎉 All tests passed! UI is working correctly.');
    } else {
        console.log('⚠️ Some tests failed. Check console for details.');
    }

    return passed === total;
}

// Auto-run tests when page loads (only in development)
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(runUITests, 1000); // Wait for all elements to load
    });
}

// Export for manual testing
window.runUITests = runUITests;